"""数据库管理模块 - 使用连接池模式"""
import aiosqlite
import logging
import os
from datetime import datetime
from typing import Optional, List, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

DB_PATH = "data/bot.db"


class DatabasePool:
    """数据库连接池管理"""
    _instance: Optional['DatabasePool'] = None
    _connection: Optional[aiosqlite.Connection] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_connection(self) -> aiosqlite.Connection:
        """获取数据库连接"""
        if self._connection is None:
            os.makedirs("data", exist_ok=True)
            self._connection = await aiosqlite.connect(DB_PATH)
            self._connection.row_factory = aiosqlite.Row
        return self._connection
    
    async def close(self):
        """关闭连接"""
        if self._connection:
            await self._connection.close()
            self._connection = None


# 全局连接池实例
db_pool = DatabasePool()


@asynccontextmanager
async def get_db():
    """获取数据库连接的上下文管理器"""
    conn = await db_pool.get_connection()
    try:
        yield conn
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise


async def init_db():
    """初始化数据库表"""
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                current_session_id INTEGER,
                created_at TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                model TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                role TEXT,
                content TEXT,
                type TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        """)
        # 添加索引提升查询性能
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session 
            ON messages(session_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_user 
            ON sessions(user_id)
        """)
        await db.commit()


async def add_user(user_id: int, username: str):
    async with get_db() as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (id, username, created_at)
            VALUES (?, ?, ?)
        """, (user_id, username, datetime.now()))
        await db.execute(
            "UPDATE users SET username = ? WHERE id = ?", 
            (username, user_id)
        )
        await db.commit()


async def get_user(user_id: int) -> Optional[aiosqlite.Row]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone()


async def create_session(user_id: int, model: str, title: str = "New Chat") -> int:
    async with get_db() as db:
        cursor = await db.execute("""
            INSERT INTO sessions (user_id, title, model, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, title, model, datetime.now()))
        session_id = cursor.lastrowid
        await db.execute(
            "UPDATE users SET current_session_id = ? WHERE id = ?", 
            (session_id, user_id)
        )
        await db.commit()
        return session_id


async def get_session(session_id: int) -> Optional[aiosqlite.Row]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ) as cursor:
            return await cursor.fetchone()


async def update_session_curr(user_id: int, session_id: int):
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET current_session_id = ? WHERE id = ?", 
            (session_id, user_id)
        )
        await db.commit()


async def update_session_title(session_id: int, title: str):
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET title = ? WHERE id = ?", 
            (title, session_id)
        )
        await db.commit()


async def update_session_model(session_id: int, model: str):
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET model = ? WHERE id = ?", 
            (model, session_id)
        )
        await db.commit()


async def get_user_sessions(user_id: int, limit: int = 10) -> List[aiosqlite.Row]:
    async with get_db() as db:
        async with db.execute("""
            SELECT * FROM sessions 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """, (user_id, limit)) as cursor:
            return await cursor.fetchall()


async def add_message(session_id: int, role: str, content: str, msg_type: str = "text"):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO messages (session_id, role, content, type, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, role, content, msg_type, datetime.now()))
        await db.commit()


async def get_session_messages(
    session_id: int, 
    limit: Optional[int] = None
) -> List[aiosqlite.Row]:
    """获取会话消息，支持限制数量"""
    async with get_db() as db:
        if limit:
            # 获取最近的 N 条消息
            async with db.execute("""
                SELECT * FROM (
                    SELECT * FROM messages 
                    WHERE session_id = ? 
                    ORDER BY id DESC 
                    LIMIT ?
                ) ORDER BY id ASC
            """, (session_id, limit)) as cursor:
                return await cursor.fetchall()
        else:
            async with db.execute("""
                SELECT * FROM messages 
                WHERE session_id = ? 
                ORDER BY id ASC
            """, (session_id,)) as cursor:
                return await cursor.fetchall()


async def update_session_last_active(session_id: int):
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET created_at = ? WHERE id = ?", 
            (datetime.now(), session_id)
        )
        await db.commit()


async def close_db():
    """关闭数据库连接"""
    await db_pool.close()
