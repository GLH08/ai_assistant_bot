"""聊天处理模块"""
import asyncio
import base64
import logging
import re
from typing import List, Tuple

from aiogram import Router, types, F
from aiogram.enums import ContentType

from src.config import config
from src.database import (
    get_user, get_session, get_session_messages,
    add_message, create_session, add_user
)
from src.utils import (
    get_client, auto_title_task, is_user_allowed,
    split_long_message, retry_handler
)

router = Router()
logger = logging.getLogger(__name__)

# 图片URL正则
IMAGE_URL_PATTERN = re.compile(
    r'https?://[^\s\)\]]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s\)\]]*)?', 
    re.IGNORECASE
)
MARKDOWN_IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\((https?://[^\s\)]+)\)')


def extract_image_urls(text: str) -> List[str]:
    """从文本中提取图片URL"""
    urls = []
    for match in MARKDOWN_IMAGE_PATTERN.finditer(text):
        urls.append(match.group(2))
    for match in IMAGE_URL_PATTERN.finditer(text):
        url = match.group(0)
        if url not in urls:
            urls.append(url)
    return urls


def remove_image_markdown(text: str) -> str:
    """移除文本中的 markdown 图片语法"""
    text = MARKDOWN_IMAGE_PATTERN.sub('', text)
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if IMAGE_URL_PATTERN.fullmatch(stripped):
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()


async def ensure_session(user_id: int, username: str) -> Tuple[int, str]:
    """确保用户有活跃会话"""
    user = await get_user(user_id)
    if not user or not user['current_session_id']:
        if not user:
            await add_user(user_id, username)
        session_id = await create_session(user_id, config.default_model)
        return session_id, config.default_model
    session = await get_session(user['current_session_id'])
    return user['current_session_id'], session['model']


def format_reply(text: str) -> str:
    """格式化回复，将Markdown标题转为粗体"""
    return re.sub(r'^(#+)\s+(.+)$', r'**\2**', text, flags=re.MULTILINE)


def sanitize_markdown(text: str) -> str:
    """清理不完整的 Markdown 语法，防止 Telegram 解析失败"""
    # 统计未闭合的粗体标记
    bold_count = text.count('**')
    if bold_count % 2 != 0:
        # 找到最后一个 ** 并移除
        last_pos = text.rfind('**')
        text = text[:last_pos] + text[last_pos+2:]
    
    # 统计未闭合的斜体标记（单个 *，但不是 **）
    # 先临时替换 ** 再统计
    temp = text.replace('**', '\x00\x00')
    italic_count = temp.count('*')
    if italic_count % 2 != 0:
        # 移除最后一个单独的 *
        last_pos = temp.rfind('*')
        temp = temp[:last_pos] + temp[last_pos+1:]
    text = temp.replace('\x00\x00', '**')
    
    # 统计未闭合的代码标记
    code_count = text.count('`')
    # 排除 ``` 代码块
    code_block_count = text.count('```')
    single_code = code_count - code_block_count * 3
    if single_code % 2 != 0:
        last_pos = text.rfind('`')
        # 确保不是 ``` 的一部分
        if last_pos >= 2 and text[last_pos-2:last_pos+1] == '```':
            pass  # 跳过
        elif last_pos >= 1 and text[last_pos-1:last_pos+1] == '``':
            pass
        else:
            text = text[:last_pos] + text[last_pos+1:]
    
    # 检查 ``` 代码块是否闭合
    if code_block_count % 2 != 0:
        text += '\n```'
    
    return text


async def safe_send_message(
    message: types.Message,
    text: str,
    parse_mode: str = "Markdown"
):
    """安全发送消息，Markdown 解析失败时回退到纯文本"""
    try:
        await message.answer(text, parse_mode=parse_mode)
    except Exception as e:
        if "can't parse entities" in str(e):
            # Markdown 解析失败，发送纯文本
            await message.answer(text, parse_mode=None)
        else:
            raise


async def safe_edit_message(
    msg: types.Message,
    text: str,
    parse_mode: str = "Markdown"
):
    """安全编辑消息，Markdown 解析失败时回退到纯文本"""
    try:
        await msg.edit_text(text, parse_mode=parse_mode)
    except Exception as e:
        if "can't parse entities" in str(e):
            await msg.edit_text(text, parse_mode=None)
        else:
            raise


async def send_response(
    message: types.Message, 
    processing_msg: types.Message,
    reply_content: str,
    model: str
):
    """发送响应，处理图片和长消息"""
    image_urls = extract_image_urls(reply_content)
    
    if image_urls:
        # 有图片：发送图片
        await processing_msg.delete()
        
        for url in image_urls[:3]:
            try:
                caption = f"🔗 {url}\n\n🤖 Model: `{model}`"
                await message.answer_photo(url, caption=caption, parse_mode="Markdown")
            except Exception as img_err:
                logger.warning(f"Failed to send image: {img_err}")
                await message.answer(
                    f"🖼 图片链接: {url}\n🤖 Model: {model}", 
                    parse_mode=None
                )
        
        # 发送剩余文本
        remaining_text = remove_image_markdown(reply_content)
        if remaining_text:
            formatted = format_reply(remaining_text)
            formatted = sanitize_markdown(formatted)
            parts = split_long_message(formatted)
            for part in parts:
                await safe_send_message(message, part)
    else:
        # 无图片：发送文本
        formatted_reply = format_reply(reply_content)
        formatted_reply = sanitize_markdown(formatted_reply)
        parts = split_long_message(formatted_reply)
        
        if len(parts) == 1:
            await safe_edit_message(processing_msg, parts[0])
        else:
            await processing_msg.delete()
            for part in parts:
                await safe_send_message(message, part)


async def call_api_with_retry(model: str, messages: List[dict]) -> str:
    """调用 API 并支持重试"""
    async def _call():
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content
    
    return await retry_handler.execute(_call)


@router.message(F.content_type.in_({ContentType.PHOTO}))
async def photo_handler(message: types.Message):
    """处理图片消息（多模态支持）"""
    user_id = message.from_user.id

    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return

    username = message.from_user.username or message.from_user.first_name
    session_id, model = await ensure_session(user_id, username)

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    
    # 安全处理：下载图片并转 base64，避免暴露 bot token
    try:
        file_io = await message.bot.download_file(file.file_path)
        file_bytes = file_io.read()
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        # 根据文件扩展名确定 MIME 类型
        ext = file.file_path.split('.')[-1].lower()
        mime_type = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }.get(ext, 'image/jpeg')
        
        image_url = f"data:{mime_type};base64,{base64_image}"
    except Exception as e:
        logger.error(f"Failed to process image: {e}")
        await message.answer("❌ 图片处理失败，请重试。")
        return

    caption = message.caption or "请描述这张图片"

    user_content = [
        {"type": "text", "text": caption},
        {"type": "image_url", "image_url": {"url": image_url}}
    ]

    await add_message(session_id, "user", f"[图片] {caption}")

    # 获取历史消息（限制上下文长度）
    db_messages = await get_session_messages(
        session_id, 
        limit=config.max_context_messages
    )
    messages = []
    for m in db_messages[:-1]:
        messages.append({"role": m['role'], "content": m['content']})
    messages.append({"role": "user", "content": user_content})

    logger.info(f"Session {session_id} | Model: {model} | User sent image")

    processing_msg = await message.answer("🔄 正在分析图片...")

    try:
        reply_content = await call_api_with_retry(model, messages)
        await add_message(session_id, "assistant", reply_content)

        logger.info(f"Session {session_id} | Reply: {reply_content[:50]}...")

        await send_response(message, processing_msg, reply_content, model)

        if len(db_messages) == 1:
            asyncio.create_task(auto_title_task(
                session_id, f"[图片] {caption}", reply_content
            ))

    except Exception as e:
        logger.error(f"Vision request failed: {e}")
        try:
            await processing_msg.edit_text(
                f"❌ 请求失败: {str(e)[:200]}\n\n模型 {model} 可能不支持图像识别。",
                parse_mode=None
            )
        except Exception:
            pass


@router.message(F.text)
async def chat_handler(message: types.Message):
    """处理文本消息"""
    if message.text.startswith('/'):
        logger.info(f"Chat handler ignored command: {message.text}")
        return

    user_id = message.from_user.id

    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return

    username = message.from_user.username or message.from_user.first_name
    session_id, model = await ensure_session(user_id, username)

    await add_message(session_id, "user", message.text)

    # 获取历史消息（限制上下文长度）
    db_messages = await get_session_messages(
        session_id, 
        limit=config.max_context_messages
    )
    messages = [{"role": m['role'], "content": m['content']} for m in db_messages]

    logger.info(f"Session {session_id} | Model: {model} | User: {message.text[:50]}...")

    processing_msg = await message.answer("🔄 正在思考中...")

    try:
        reply_content = await call_api_with_retry(model, messages)
        await add_message(session_id, "assistant", reply_content)

        logger.info(f"Session {session_id} | Reply: {reply_content[:50]}...")

        await send_response(message, processing_msg, reply_content, model)

        # 自动标题
        if len(db_messages) == 1:
            asyncio.create_task(auto_title_task(
                session_id, message.text, reply_content
            ))

    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        try:
            await processing_msg.edit_text(
                f"❌ 请求失败: {str(e)[:200]}\n\n可能是模型 {model} 配置有误或额度不足。",
                parse_mode=None
            )
        except Exception:
            pass
