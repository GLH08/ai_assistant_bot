from aiogram import Router, types
from aiogram.filters import CommandStart, Command
from src.database import add_user, create_session, get_user
from src.utils import is_user_allowed
import os

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    if not is_user_allowed(user_id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
    
    username = message.from_user.username or message.from_user.first_name
    await add_user(user_id, username)
    
    user = await get_user(user_id)
    if not user['current_session_id']:
        default_model = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")
        await create_session(user_id, default_model)

    await message.answer(
        "👋 欢迎使用 AI 助手！\n\n"
        "常用命令：\n"
        "/new - 开始新对话\n"
        "/history - 查看历史对话\n"
        "/model - 切换模型\n"
        "/rename <标题> - 重命名当前对话\n\n"
        "💡 直接发送文字或图片即可开始对话。"
    )

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_user_allowed(message.from_user.id):
        await message.answer("⛔ 抱歉，您没有使用此机器人的权限。")
        return
        
    await message.answer(
        "📚 帮助文档：\n\n"
        "/start - 初始化\n"
        "/new - 清空上下文，开始新的话题\n"
        "/history - 列出最近的 10 个对话记录，点击可恢复\n"
        "/model [模型名] - 查看当前模型或切换模型\n"
        "/rename <新标题> - 修改当前会话的标题\n\n"
        "💡 提示：\n"
        "• 发送图片可进行图像识别（需多模态模型）\n"
        "• 切换到生图模型后直接发送描述即可生成图片"
    )
