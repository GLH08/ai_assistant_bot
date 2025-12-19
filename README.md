# AI Assistant (Telegram Bot)

一个功能强大的 Telegram AI 助手，支持多轮对话、多模态（图像识别）、智能历史回放和动态模型切换。

## ✨ 功能特性

- **多会话管理**：支持无限创建新会话，自动保存所有历史记录
- **智能历史回放**：切换会话时，自动回放最近 10 条消息，无缝衔接上下文
- **动态模型切换**：实时获取 API 可用模型列表，支持翻页选择
- **多模态支持**：发送图片进行图像识别（需使用支持 vision 的模型）
- **图片生成**：切换到生图模型后，直接发送描述即可生成图片，自动预览
- **自动命名**：机器人自动生成简洁的会话标题
- **用户限制**：可配置允许使用的用户 ID
- **Docker 部署**：一键启动，数据自动持久化

## 🚀 快速启动

### 1. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

```env
API_BASE_URL=https://api.your-ai-provider.com/v1
API_KEY=sk-your-key
BOT_TOKEN=123456:ABC-DEF
DEFAULT_MODEL=gpt-3.5-turbo
ALLOWED_USERS=123456789  # 可选，留空则不限制
```

### 2. 运行方式

#### 方式 A：本地构建

```bash
docker-compose up -d --build
```

#### 方式 B：使用 GitHub 镜像

修改 `docker-compose.yml`，注释 `build: .`，取消注释 `image` 行：

```bash
docker-compose up -d
```

## 🤖 命令列表

| 命令 | 描述 |
|:---|:---|
| `/start` | 初始化机器人 |
| `/new` | 开始新对话（清空上下文） |
| `/history` | 查看历史对话，点击切换 |
| `/model` | 切换模型（支持翻页选择） |
| `/rename <标题>` | 修改当前会话标题 |
| `/help` | 帮助文档 |

## 💡 使用提示

- **文字对话**：直接发送消息即可
- **图像识别**：发送图片（可附带文字说明），需使用支持 vision 的模型
- **图片生成**：切换到生图模型后，发送描述文字即可生成图片

## 📁 目录结构

```
src/
├── bot.py          # 程序入口
├── database.py     # SQLite 数据库管理
├── utils.py        # 工具函数
└── handlers/       # 功能模块
    ├── common.py   # 通用命令
    ├── session.py  # 会话管理
    └── chat.py     # 对话处理
```
