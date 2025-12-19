from aiogram import Router, types
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

@router.message()
async def chat_handler(message: types.Message):
    if not message.text or message.text.startswith('/'):
        if message.text and message.text.startswith('/'):
            logger.info(f"Chat handler ignored command: {message.text}")
        return

    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
    user = await get_user(user_id)
    
    # Ensure session
    if not user or not user['current_session_id']:
        default_model = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")
        if not user:
            from src.database import add_user
            username = message.from_user.username or message.from_user.first_name
            await add_user(user_id, username)
        
        session_id = await create_session(user_id, default_model)
    else:
        session_id = user['current_session_id']
    
    session = await get_session(session_id)
    model = session['model']
    
    # Save User Message
    await add_message(session_id, "user", message.text)
    
    # Prepare Context
    db_messages = await get_session_messages(session_id)
    messages = [{"role": m['role'], "content": m['content']} for m in db_messages]
    
    logger.info(f"Session {session_id} | Model: {model} | User: {message.text[:50]}...")

    # Send placeholder message
    processing_msg = await message.answer("🔄 正在思考中...")
    
    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            messages=messages
        )
        
        reply_content = response.choices[0].message.content
        
        # Save Assistant Message
        await add_message(session_id, "assistant", reply_content)
        
        logger.info(f"Session {session_id} | Reply: {reply_content[:50]}...")

        # Fix Markdown Header Issue for Telegram
        formatted_reply = re.sub(r'^(#+)\s+(.+)$', r'**\2**', reply_content, flags=re.MULTILINE)

        # Edit the placeholder message with the real reply
        await processing_msg.edit_text(formatted_reply, parse_mode="Markdown")
        
        # Auto Title Check
        if len(db_messages) == 1:
            asyncio.create_task(auto_title_task(session_id, message.text, reply_content))
            
    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        await processing_msg.edit_text(f"❌ 请求失败: {str(e)}\n\n可能是模型 `{model}` 配置有误或额度不足。")
