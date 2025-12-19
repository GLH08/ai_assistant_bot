import os
import logging
from openai import AsyncOpenAI
from src.database import update_session_title

logger = logging.getLogger(__name__)

def get_client():
    return AsyncOpenAI(
        api_key=os.getenv("API_KEY"),
        base_url=os.getenv("API_BASE_URL")
    )

def get_allowed_users() -> set:
    """获取允许使用的用户ID列表，为空则不限制"""
    allowed = os.getenv("ALLOWED_USERS", "")
    if not allowed.strip():
        return set()
    return set(int(uid.strip()) for uid in allowed.split(",") if uid.strip().isdigit())

def is_user_allowed(user_id: int) -> bool:
    """检查用户是否被允许使用"""
    allowed_users = get_allowed_users()
    if not allowed_users:  # 未配置则允许所有人
        return True
    return user_id in allowed_users

async def auto_title_task(session_id: int, first_question: str, first_answer: str):
    try:
        client = get_client()
        prompt = f"User: {first_question}\nAI: {first_answer}\n\n请用不超过20个中文字符总结上述对话的主题，直接返回标题，不要加引号。"
        
        titling_model = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")
        
        response = await client.chat.completions.create(
            model=titling_model, 
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30
        )
        title = response.choices[0].message.content.strip()
        await update_session_title(session_id, title)
        logger.info(f"Session {session_id} auto-titled: {title}")
    except Exception as e:
        logger.error(f"Auto title failed: {e}")
