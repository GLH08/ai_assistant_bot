"""配置管理模块"""
import os
from dataclasses import dataclass, field
from typing import Set
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """应用配置"""
    # API 配置
    api_base_url: str = field(default_factory=lambda: os.getenv("API_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))
    
    # Bot 配置
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    default_model: str = field(default_factory=lambda: os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo"))
    
    # 用户限制
    allowed_users: Set[int] = field(default_factory=set)
    
    # 上下文限制
    max_context_messages: int = 20
    
    # 消息限制
    max_message_length: int = 4000
    
    # 模型缓存 TTL (秒)
    model_cache_ttl: int = 300
    
    # 流式响应配置
    stream_update_interval: int = 15  # 每多少个 token 更新一次
    
    # 数据库路径
    db_path: str = "data/bot.db"
    
    def __post_init__(self):
        # 解析允许的用户
        allowed = os.getenv("ALLOWED_USERS", "")
        if allowed.strip():
            self.allowed_users = set(
                int(uid.strip()) 
                for uid in allowed.split(",") 
                if uid.strip().isdigit()
            )
    
    def is_user_allowed(self, user_id: int) -> bool:
        """检查用户是否被允许使用"""
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users
    
    def validate(self) -> bool:
        """验证必要配置"""
        if not self.bot_token:
            raise ValueError("BOT_TOKEN is required")
        if not self.api_key:
            raise ValueError("API_KEY is required")
        if not self.api_base_url:
            raise ValueError("API_BASE_URL is required")
        return True


# 全局配置实例
config = Config()
