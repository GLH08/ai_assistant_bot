import os
import logging
import asyncio
from openai import AsyncOpenAI
from src.database import update_session_title

logger = logging.getLogger(__name__)

def get_client():
    return AsyncOpenAI(
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("API_BASE_URL")
    )

async def auto_title_task(session_id: int, first_question: str, first_answer: str):
    try:
        client = get_client()
        # Increased limit for better titles as requested (20 chars)
        prompt = f"User: {first_question}\nAI: {first_answer}\n\n请用不超过20个中文字符总结上述对话的主题，直接返回标题，不要加引号。"
        
        titling_model = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")
        
        response = await client.chat.completions.create(
            model=titling_model, 
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30 # Increased tokens for longer title
        )
        title = response.choices[0].message.content.strip()
        await update_session_title(session_id, title)
        logger.info(f"Session {session_id} auto-titled: {title}")
    except Exception as e:
        logger.error(f"Auto title failed: {e}")
