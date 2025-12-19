import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from dotenv import load_dotenv

from src.database import init_db
from src.handlers import common, session, chat

# Load env
load_dotenv()

async def main():
    # Logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Config
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN is not set in .env")
        return

    # Init DB
    await init_db()
    logger.info("Database initialized.")

    # Init Bot
    bot = Bot(token=token)
    dp = Dispatcher()

    # Register Routers
    dp.include_router(common.router)
    dp.include_router(session.router)
    dp.include_router(chat.router)  # Keep chat last as it handles all messages

    # Register Commands
    await bot.set_my_commands([
        types.BotCommand(command="start", description="初始化机器人"),
        types.BotCommand(command="new", description="开启新对话"),
        types.BotCommand(command="history", description="历史记录"),
        types.BotCommand(command="model", description="切换模型"),
        types.BotCommand(command="rename", description="重命名当前对话"),
        types.BotCommand(command="help", description="帮助文档"),
    ])
    logger.info("Bot commands registered.")

    # Start Polling
    logger.info("Bot started polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped!")
