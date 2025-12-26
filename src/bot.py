"""Bot 入口模块"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ErrorEvent

from src.config import config
from src.database import init_db, close_db
from src.handlers import common, session, chat

logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """启动时执行"""
    await init_db()
    logger.info("Database initialized.")
    
    await bot.set_my_commands([
        types.BotCommand(command="start", description="初始化机器人"),
        types.BotCommand(command="new", description="开启新对话"),
        types.BotCommand(command="history", description="历史记录"),
        types.BotCommand(command="model", description="切换模型"),
        types.BotCommand(command="rename", description="重命名当前对话"),
        types.BotCommand(command="help", description="帮助文档"),
    ])
    logger.info("Bot commands registered.")


async def on_shutdown(bot: Bot):
    """关闭时执行"""
    await close_db()
    logger.info("Database connection closed.")


async def global_error_handler(event: ErrorEvent):
    """全局错误处理"""
    logger.exception(f"Unhandled error: {event.exception}")
    
    # 尝试通知用户
    try:
        if event.update and event.update.message:
            await event.update.message.answer(
                "❌ 发生了意外错误，请稍后重试。\n"
                "如果问题持续存在，请联系管理员。"
            )
        elif event.update and event.update.callback_query:
            await event.update.callback_query.answer(
                "发生错误，请重试",
                show_alert=True
            )
    except Exception:
        pass  # 忽略通知失败


async def main():
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # 验证配置
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return
    
    # 初始化 Bot
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()
    
    # 注册生命周期钩子
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # 注册全局错误处理
    dp.errors.register(global_error_handler)
    
    # 注册路由
    dp.include_router(common.router)
    dp.include_router(session.router)
    dp.include_router(chat.router)  # chat 放最后，处理所有消息
    
    # 启动轮询
    logger.info("Bot started polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped!")
