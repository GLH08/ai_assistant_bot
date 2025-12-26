"""会话管理处理"""
import logging
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.config import config
from src.database import (
    create_session, get_user, get_user_sessions, 
    update_session_curr, update_session_model, 
    update_session_title, get_session, update_session_last_active,
    get_session_messages
)
from src.utils import is_user_allowed, fetch_models_cached

router = Router()
logger = logging.getLogger(__name__)

MODELS_PER_PAGE = 5


@router.message(Command("new"))
async def cmd_new_session(message: types.Message):
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
    
    session_id = await create_session(user_id, config.default_model)
    logger.info(f"User {user_id} started new session {session_id}")
    
    await message.answer(f"🆕 已通过模型 `{config.default_model}` 开启新对话。", parse_mode="Markdown")


@router.message(Command("history"))
async def cmd_history(message: types.Message):
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
    
    sessions = await get_user_sessions(user_id)
    
    if not sessions:
        await message.answer("📭 暂无历史记录。")
        return

    buttons = []
    for s in sessions:
        title = s['title'] if s['title'] else f"Session {s['id']}"
        model = s['model']
        buttons.append([InlineKeyboardButton(
            text=f"{title} ({model})", 
            callback_data=f"sess:{s['id']}"
        )])
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "📜 **历史对话记录** (点击切换)：", 
        reply_markup=keyboard, 
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("sess:"))
async def session_callback(callback: types.CallbackQuery):
    session_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    await update_session_curr(user_id, session_id)
    session = await get_session(session_id)
    title = session['title']
    await update_session_last_active(session_id)
    
    # 回放历史
    await send_history_replay(callback.message.bot, callback.message.chat.id, session_id)
    
    await callback.message.edit_text(
        f"✅ 已切换回对话：**{title}**", 
        parse_mode="Markdown"
    )
    await callback.answer()


async def send_history_replay(bot: Bot, chat_id: int, session_id: int):
    """发送历史记录回放"""
    messages = await get_session_messages(session_id, limit=10)
    if not messages:
        return

    text_lines = ["📜 **历史记录回放 (最后 10 条)**:"]
    for m in messages:
        role = "👤 User" if m['role'] == 'user' else "🤖 AI"
        content = m['content'][:200] + "..." if len(m['content']) > 200 else m['content']
        text_lines.append(f"\n**{role}**: {content}")
    
    summary = "\n".join(text_lines)
    
    # 处理长消息
    from src.utils import split_long_message
    parts = split_long_message(summary)
    for part in parts:
        await bot.send_message(chat_id, part, parse_mode="Markdown")


@router.message(Command("model"))
async def cmd_model(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
    
    user = await get_user(user_id)
    curr_session_id = user['current_session_id']
    
    if not curr_session_id:
        await message.answer("⚠️ 请先开始一个对话 (/start 或 /new)。")
        return
        
    target_model = command.args
    
    # 直接指定模型
    if target_model:
        await update_session_model(curr_session_id, target_model)
        await message.delete()
        await message.answer(f"🔄 模型已切换为：`{target_model}`", parse_mode="Markdown")
        return

    # 显示模型列表
    models = await fetch_models_cached()
    if not models:
        session = await get_session(curr_session_id)
        current_model = session['model']
        await message.answer(
            f"当前模型: `{current_model}`\n(无法获取模型列表，请手动输入)",
            parse_mode="Markdown"
        )
        return

    await show_model_page(message, models, 0)


async def show_model_page(message_or_call, models: list, page: int):
    """显示模型选择页面"""
    total_pages = (len(models) + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE
    start = page * MODELS_PER_PAGE
    end = start + MODELS_PER_PAGE
    current_page_models = models[start:end]
    
    buttons = []
    for m in current_page_models:
        buttons.append([InlineKeyboardButton(
            text=m, 
            callback_data=f"model_sel:{m}"
        )])
        
    # 导航按钮
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(
            text="< 上一页", 
            callback_data=f"model_page:{page-1}"
        ))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(
            text="下一页 >", 
            callback_data=f"model_page:{page+1}"
        ))
        
    if nav_buttons:
        buttons.append(nav_buttons)
        
    buttons.append([InlineKeyboardButton(text="❌ 关闭", callback_data="model_close")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = f"🤖 **请选择模型** (第 {page+1}/{total_pages} 页):"
    
    if isinstance(message_or_call, types.Message):
        await message_or_call.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await message_or_call.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")


@router.callback_query(F.data.startswith("model_"))
async def model_callback(callback: types.CallbackQuery):
    action = callback.data.split(":")[0]
    
    if action == "model_close":
        await callback.message.delete()
        await callback.answer()
        return
        
    if action == "model_page":
        page = int(callback.data.split(":")[1])
        models = await fetch_models_cached()
        await show_model_page(callback, models, page)
        await callback.answer()
        return
        
    if action == "model_sel":
        model_name = callback.data.split(":")[1]
        user_id = callback.from_user.id
        user = await get_user(user_id)
        curr_session_id = user['current_session_id']
        
        if curr_session_id:
            await update_session_model(curr_session_id, model_name)
            await callback.message.delete()
            await callback.message.answer(
                f"✅ 已切换至模型: `{model_name}`", 
                parse_mode="Markdown"
            )
            
        await callback.answer()


@router.message(Command("rename"))
async def cmd_rename(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
    
    user = await get_user(user_id)
    curr_session_id = user['current_session_id']
    
    if not curr_session_id:
        await message.answer("⚠️ 没有活跃的对话。")
        return
        
    new_title = command.args
    if not new_title:
        await message.answer("⚠️ 请输入新标题，例如：`/rename 翻译助手`", parse_mode="Markdown")
        return
        
    await update_session_title(curr_session_id, new_title)
    await message.answer(f"✍️ 标题已修改为：**{new_title}**", parse_mode="Markdown")
