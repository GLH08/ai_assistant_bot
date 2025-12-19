from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from openai import AsyncOpenAI
from src.utils import is_user_allowed
import os
import logging
import asyncio

router = Router()
logger = logging.getLogger(__name__)

logger.info("GenImage module loaded. Router initialized.")

@router.message(Command("image"))
async def cmd_image(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
    
    prompt = command.args
    if not prompt:
        await message.answer("🎨 请输入提示词，例如：`/image 一只在太空游泳的猫`")
        return
    logger.info(f"User {user_id} requested image generation. Prompt: {prompt}")

    # Determine model: User's session model (if image capable theoretically) or default to dall-e-3
    # Logic: If user specifically set a model in current session that looks like an image model, use it?
    # Or strict behavior: if they say "switch model to midjourney" then we use it.
    
    from src.database import get_user, get_session
    user = await get_user(user_id)
    image_model = "dall-e-3" # Default
    
    if user and user['current_session_id']:
        session = await get_session(user['current_session_id'])
        if session and session['model']:
             # Trust user's choice. If they picked 'gpt-4' and try /image, it might fail if upstream doesn't handle.
             # But user requirement says: "I switched model... then used /image". 
             # So we MUST use the session model.
             image_model = session['model']

    logger.info(f"Using Image Model: {image_model}")
    msg = await message.answer(f"🎨 正在使用 `{image_model}` 绘制中，请稍候...")
    
    # Save User Prompt to History
    from src.database import add_message, get_session_messages
    from src.utils import auto_title_task
    
    # We need session_id. We looked it up earlier.
    session_id = user['current_session_id'] if user else None
    
    # If no session, create one? (Like chat.py)
    # Chat handler creates session if none. Image handler relies on existing check?
    # Logic at line 29: if user and user['current_session_id'].
    # If session is None, we currently use default dall-e-3 but NO session ID?
    # If no session ID, we can't save to DB.
    # We should probably ensure session exists.
    
    if not session_id:
        from src.database import create_session, add_user
        default_model = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")
        if not user:
             username = message.from_user.username or message.from_user.first_name
             await add_user(user_id, username)
        session_id = await create_session(user_id, default_model) # Use default model for session meta
    
    await add_message(session_id, "user", f"/image {prompt}")

    try:
        from src.utils import get_client
        client = get_client()
        
        # Use chat completions for image generation
        response = await client.chat.completions.create(
            model=image_model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content
        logger.info(f"Image generation response content: {content[:100]}...")

        # Save AI Response to History
        await add_message(session_id, "assistant", content)

        # Auto Title Check
        db_messages = await get_session_messages(session_id)
        if len(db_messages) <= 2: # 1 user prompt + 1 AI response (image)
             # Use the prompt as the "question" for titling
             asyncio.create_task(auto_title_task(session_id, f"绘制图片: {prompt}", "图片已生成"))

        # Extract URL logic...
        import re
        url_match = re.search(r'\((http[s]?://.+?)\)', content)
        if not url_match:
            url_match = re.search(r'(http[s]?://[^\s]+)', content)
            
        if url_match:
            image_url = url_match.group(1)
            caption = f"🔗 **图片链接**: {image_url}\nModel: `{image_model}`"
            await message.answer_photo(image_url, caption=caption, parse_mode="Markdown")
        else:
            await message.answer(f"🎨 **生成结果**:\n{content}", parse_mode="Markdown")

        await msg.delete()
        
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        await msg.edit_text(f"❌ 绘图失败: {str(e)}")
