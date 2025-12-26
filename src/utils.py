"""工具函数模块"""
import base64
import logging
import time
from typing import List, Optional, AsyncGenerator
from openai import AsyncOpenAI

from src.config import config
from src.database import update_session_title

logger = logging.getLogger(__name__)

# OpenAI 客户端单例
_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    """获取 OpenAI 客户端单例"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.api_base_url
        )
    return _client


def is_user_allowed(user_id: int) -> bool:
    """检查用户是否被允许使用"""
    return config.is_user_allowed(user_id)


# 模型缓存
_model_cache = {"models": [], "timestamp": 0}


async def fetch_models_cached() -> List[str]:
    """获取模型列表（带缓存）"""
    global _model_cache
    
    now = time.time()
    if now - _model_cache["timestamp"] < config.model_cache_ttl and _model_cache["models"]:
        return _model_cache["models"]
    
    try:
        client = get_client()
        response = await client.models.list()
        models = sorted([m.id for m in response.data])
        _model_cache.update({"models": models, "timestamp": now})
        return models
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        # 返回缓存的旧数据（如果有）
        return _model_cache["models"]


async def auto_title_task(session_id: int, first_question: str, first_answer: str):
    """自动生成会话标题"""
    try:
        client = get_client()
        prompt = (
            f"User: {first_question}\n"
            f"AI: {first_answer}\n\n"
            "请用不超过20个中文字符总结上述对话的主题，直接返回标题，不要加引号。"
        )
        
        response = await client.chat.completions.create(
            model=config.default_model, 
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30
        )
        title = response.choices[0].message.content.strip()
        await update_session_title(session_id, title)
        logger.info(f"Session {session_id} auto-titled: {title}")
    except Exception as e:
        logger.error(f"Auto title failed: {e}")


def split_long_message(text: str, max_length: int = None) -> List[str]:
    """将长消息分割为多个部分"""
    if max_length is None:
        max_length = config.max_message_length
    
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current = ""
    
    # 按行分割，尽量保持完整性
    lines = text.split('\n')
    for line in lines:
        if len(current) + len(line) + 1 <= max_length:
            current += line + '\n'
        else:
            if current:
                parts.append(current.rstrip())
            # 如果单行超长，强制分割
            while len(line) > max_length:
                parts.append(line[:max_length])
                line = line[max_length:]
            current = line + '\n'
    
    if current.strip():
        parts.append(current.rstrip())
    
    return parts


async def stream_chat_response(
    model: str, 
    messages: List[dict],
    update_interval: int = None
) -> AsyncGenerator[str, None]:
    """流式获取聊天响应"""
    if update_interval is None:
        update_interval = config.stream_update_interval
    
    client = get_client()
    
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True
    )
    
    buffer = ""
    token_count = 0
    
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            buffer += content
            token_count += 1
            
            # 每隔一定数量的 token 返回一次
            if token_count >= update_interval:
                yield buffer
                token_count = 0
    
    # 返回最终内容
    if buffer:
        yield buffer


async def download_image_as_base64(bot, file_path: str) -> str:
    """下载图片并转换为 base64"""
    try:
        file = await bot.download_file(file_path)
        file_bytes = file.read()
        return base64.b64encode(file_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        raise


class RetryHandler:
    """重试处理器"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    async def execute(self, func, *args, **kwargs):
        """执行函数，失败时重试"""
        import asyncio
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
        
        raise last_error


# 全局重试处理器
retry_handler = RetryHandler()
