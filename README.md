# AI Assistant (Telegram Bot)

这是一个功能强大的 Telegram 机器人，专为 AI（OpenAI 兼容接口）设计。它支持多轮对话、智能历史回放、无缝模型切换以及集成的绘图功能。

## ✨ 功能特性

- **多会话管理**：支持无限创建新会话，自动保存所有历史记录。
- **智能历史回放**：切换会话时，自动回放最近 10 条消息，无缝衔接上下文。
- **动态模型切换**：实时获取 API 可用模型列表，支持翻页选择，切换后保留上下文。
- **智能绘图存档**：`/image` 生图记录（提示词与结果）自动存入数据库，支持对话式回顾。
- **自动命名**：无论是对话还是生图，机器人都会自动生成简洁的会话标题。
- **Docker 部署**：一键启动，数据自动持久化。

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
```

### 2. 运行方式

#### 方式 A：本地构建（推荐）

```bash
docker-compose up -d --build
```

#### 方式 B：使用 GitHub 镜像

1.  修改 `docker-compose.yml`，注释 `build: .`，取消注释 `image: ...` 并替换为您的镜像地址。
2.  运行：
    ```bash
    docker-compose up -d
    ```

## 🤖 命令列表

| 命令 | 描述 |
|:---|:---|
| `/start` | 初始化机器人 |
| `/new` | 开始一个新的空白对话（清空上下文） |
| `/history` | 查看最近的 10 个对话记录，点击按钮恢复上下文 |
| `/model` | 查看当前模型，或 `/model gpt-4` 切换模型 |
| `/rename <标题>` | 手动修改当前会话的标题 |
| `/image <提示词>` | 生成图片 |
| `直接发送消息` | 进行对话 |

## 📁 目录结构

- `src/bot.py`: 程序入口
- `src/database.py`: SQLite 数据库管理
- `src/handlers/`: 功能模块
- `data/`: 数据库存储目录 (自动挂载)

