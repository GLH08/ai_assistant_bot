from aiogram import Router, types, F
from aiogram.enums import ContentType
from src.database import (
    get_user, get_session, get_session_messages,
    add_message, create_session
)
import os
import re
import asyncio
import logging
from src.utils import get_client, auto_title_task, is_user_allowed

router = Router()
logger = logging.getLogger(__name__)

# 图片URL正则
IMAGE_URL_PATTERN = re.compile(r'https?://[^\s\)\]]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s\)\]]*)?', re.IGNORECASE)
MARKDOWN_IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\((https?://[^\s\)]+)\)')


def extract_image_urls(text: str) -> list:
    """从文本中提取图片URL"""
    urls = []
    # 优先匹配 markdown 图片格式
    for match in MARKDOWN_IMAGE_PATTERN.finditer(text):
        urls.append(match.group(2))
    # 匹配直接的图片链接
    for match in IMAGE_URL_PATTERN.finditer(text):
        url = match.group(0)
        if url not in urls:
            urls.append(url)
    return urls


def remove_image_markdown(text: str) -> str:
    """移除文本中的 markdown 图片语法"""
    # 移除 ![alt](url) 格式
    text = MARKDOWN_IMAGE_PATTERN.sub('', text)
    # 移除独立的图片URL行
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # 如果整行只是一个图片URL，跳过
        if IMAGE_URL_PATTERN.fullmatch(stripped):
            continue
        cleaned_lines.append(line)
    return '\n'.join(cleaned_lines).strip()


async def ensure_session(user_id: int, username: str):
    """确保用户有活跃会话"""
    user = await get_user(user_id)
    if not user or not user['current_session_id']:
        default_model = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")
        if not user:
            from src.database import add_user
            await add_user(user_id, username)
        session_id = await create_session(user_id, default_model)
        return session_id, default_model
    session = await get_session(user['current_session_id'])
    return user['current_session_id'], session['model']


def format_reply(text: str) -> str:
    """格式化回复，将Markdown标题转为粗体"""
    return re.sub(r'^(#+)\s+(.+)$', r'**\2**', text, flags=re.MULTILINE)


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
    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"

    caption = message.caption or "请描述这张图片"

    user_content = [
        {"type": "text", "text": caption},
        {"type": "image_url", "image_url": {"url": file_url}}
    ]

    await add_message(session_id, "user", f"[图片] {caption}")

    db_messages = await get_session_messages(session_id)
    messages = []
    for m in db_messages[:-1]:
        messages.append({"role": m['role'], "content": m['content']})
    messages.append({"role": "user", "content": user_content})

    logger.info(f"Session {session_id} | Model: {model} | User sent image with caption: {caption[:50]}...")

    processing_msg = await message.answer("🔄 正在分析图片...")

    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=messages
        )

        reply_content = response.choices[0].message.content
        await add_message(session_id, "assistant", reply_content)

        logger.info(f"Session {session_id} | Reply: {reply_content[:50]}...")

        formatted_reply = format_reply(reply_content)
        await processing_msg.edit_text(formatted_reply, parse_mode="Markdown")

        if len(db_messages) == 1:
            asyncio.create_task(auto_title_task(session_id, f"[图片] {caption}", reply_content))

    except Exception as e:
        logger.error(f"Vision request failed: {e}")
        await processing_msg.edit_text(f"❌ 请求失败: {str(e)}\n\n模型 `{model}` 可能不支持图像识别。")


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

    db_messages = await get_session_messages(session_id)
    messages = [{"role": m['role'], "content": m['content']} for m in db_messages]

    logger.info(f"Session {session_id} | Model: {model} | User: {message.text[:50]}...")

    processing_msg = await message.answer("🔄 正在思考中...")

    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=messages
        )

        reply_content = response.choices[0].message.content
        await add_message(session_id, "assistant", reply_content)

        logger.info(f"Session {session_id} | Reply: {reply_content[:50]}...")

        # 检测回复中的图片URL
        image_urls = extract_image_urls(reply_content)

        if image_urls:
            # 有图片：发送图片并附带信息
            await processing_msg.delete()
            
            for i, url in enumerate(image_urls[:3]):
                try:
                    caption = f"🔗 {url}\n\n🤖 Model: `{model}`"
                    await message.answer_photo(url, caption=caption, parse_mode="Markdown")
                except Exception as img_err:
                    logger.warning(f"Failed to send image: {img_err}")
                    # 发送图片失败，发送链接
                    await message.answer(f"🖼 图片链接: {url}\n🤖 Model: `{model}`", parse_mode="Markdown")
            
            # 如果还有其他文本内容，也发送出来
            remaining_text = remove_image_markdown(reply_content)
            if remaining_text:
                formatted = format_reply(remaining_text)
                await message.answer(formatted, parse_mode="Markdown")
        else:
            # 无图片：正常发送文本
            formatted_reply = format_reply(reply_content)
            await processing_msg.edit_text(formatted_reply, parse_mode="Markdown")

        # 自动标题
        if len(db_messages) == 1:
            asyncio.create_task(auto_title_task(session_id, message.text, reply_content))

    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        await processing_msg.edit_text(f"❌ 请求失败: {str(e)}\n\n可能是模型 `{model}` 配置有误或额度不足。")
