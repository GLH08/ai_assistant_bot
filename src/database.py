import aiosqlite
import logging
from datetime import datetime

DB_PATH = "data/bot.db"

async def init_db():
    import os
    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()

async def add_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (id, username, created_at)
            VALUES (?, ?, ?)
        """, (user_id, username, datetime.now()))
        await db.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def create_session(user_id: int, model: str, title: str = "New Chat"):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO sessions (user_id, title, model, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, title, model, datetime.now()))
        session_id = cursor.lastrowid
        await db.execute("UPDATE users SET current_session_id = ? WHERE id = ?", (session_id, user_id))
        await db.commit()
        return session_id

async def get_session(session_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cursor:
            return await cursor.fetchone()

async def update_session_curr(user_id: int, session_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET current_session_id = ? WHERE id = ?", (session_id, user_id))
        await db.commit()

async def update_session_title(session_id: int, title: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        await db.commit()

async def update_session_model(session_id: int, model: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE sessions SET model = ? WHERE id = ?", (model, session_id))
        await db.commit()

async def get_user_sessions(user_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit)) as cursor:
            return await cursor.fetchall()

async def add_message(session_id: int, role: str, content: str, msg_type: str = "text"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO messages (session_id, role, content, type, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (session_id, role, content, msg_type, datetime.now()))
        await db.commit()

async def get_session_messages(session_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC
        """, (session_id,)) as cursor:
            return await cursor.fetchall()

async def update_session_last_active(session_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET created_at = ? WHERE id = ?", 
            (datetime.now(), session_id)
        )
        await db.commit()
