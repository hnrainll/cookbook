# 需求文档：基于 FastAPI 的多平台消息同步网关

## 1. 项目概述
构建一个基于 Python FastAPI 的高并发消息同步服务。核心功能是实现**多对多 (M:N)** 的消息流转：
- **输入源 (Sources)**：Feishu (飞书/Lark), Telegram。
- **输出源 (Sinks)**：Fanfou, SQLite (本地存档)。
- **核心架构**：采用 **异步消息总线 (Event Bus)** 模式解耦生产者与消费者，并解决不同第三方库（阻塞 vs 异步）的兼容性问题。

## 2. 技术栈要求
- **语言**: Python 3.12+
- **Web 框架**: FastAPI + Uvicorn
- **包管理**: uv
- **异步支持**: asyncio
- **第三方库**:
  - `pydantic`, `pydantic-settings` (配置管理)
  - `loguru` (日志)
  - `httpx` (异步 HTTP 请求)
  - `aiogram` (Telegram 异步客户端)
  - `aiosqlite`, `sqlalchemy` (异步数据库)
  - `lark-oapi` (飞书官方 SDK，注意：这是同步/阻塞库，需特殊处理)

## 3. 系统目录结构
请严格遵循以下目录结构生成代码，以确保模块解耦：

```text
app/
├── core/
│   ├── config.py           # Pydantic Settings 配置加载 (.env)
│   └── bus.py              # 核心：异步内存消息总线
├── schemas/
│   └── event.py            # 定义 UnifiedMessage 统一消息模型
├── services/
│   ├── platforms/          # 平台适配器层
│   │   ├── feishu/         # 飞书 (Source)
│   │   │   ├── client.py   # 包含 Threading + Monkey Patch 逻辑
│   │   │   └── handler.py  # 飞书回调处理 -> 转换为 UnifiedMessage
│   │   ├── telegram/       # Telegram (Source)
│   │   │   └── client.py   # aiogram polling 逻辑 -> UnifiedMessage
│   │   └── fanfou/       # Fanfou (Sink)
│   │       └── client.py   # 接收 UnifiedMessage -> 发送 HTTP 请求
│   └── storage/
│       └── db.py           # SQLite (Sink) -> 接收 UnifiedMessage -> 存库
└── main.py                 # FastAPI 入口，负责 Lifespan 管理和总线注册
```

## 4. 详细模块需求

### 4.1. 统一数据模型 (`app/schemas/event.py`)
定义一个标准化的 Pydantic 模型 `UnifiedMessage`，用于在系统内部流转。
- **字段要求**：
  - `event_id`: UUID (自动生成)
  - `source`: Enum (TELEGRAM, FEISHU, SYSTEM)
  - `content`: str (文本内容)
  - `sender_id`: str
  - `raw_data`: dict (保留原始数据)
  - `timestamp`: datetime

### 4.2. 核心消息总线 (`app/core/bus.py`)
实现一个单例的异步事件总线 `EventBus`。
- **功能**：
  - 支持装饰器注册 `@bus.on_event`。
  - 支持 `publish(message)` 方法。
  - **关键要求**：使用 `asyncio.gather(..., return_exceptions=True)` 实现并发分发，确保单个消费者报错不影响其他消费者。

### 4.3. 平台实现：Feishu (`app/services/platforms/feishu/`)
**难点处理**：Feishu SDK 是阻塞的，且内部依赖全局 `loop` 变量。
- **实现方案**：
  - 创建一个 `LarkManager` 类。
  - 使用 `threading.Thread(daemon=True)` 在独立线程中运行 SDK。
  - **必须实现 Monkey Patch**：在子线程启动时，检测 SDK 模块（`lark_oapi` 或其子模块）中的全局 `loop` 变量，并将其强制修改为当前子线程的 `new_loop`。
  - 收到消息后，调用 `bus.publish`（注意：需使用 `asyncio.run_coroutine_threadsafe` 将任务提交回主线程或在当前 Loop 处理）。

### 4.4. 平台实现：Telegram (`app/services/platforms/telegram/`)
- **实现方案**：
  - 使用 `aiogram` 库。
  - 实现 `start_polling` 和 `stop` 方法。
  - 在 Handler 中接收消息，清洗为 `UnifiedMessage`，然后调用 `await bus.publish(msg)`。

### 4.5. 消费者实现 (Sinks)
- **Fanfou** (`app/services/platforms/fanfou/client.py`)：
  - 使用 `httpx.AsyncClient` 调用 Graph API 发送 Feed。
  - 通过 `@bus.on_event` 注册。
- **SQLite** (`app/services/storage/db.py`)：
  - 使用 `aiosqlite` 异步写入简单的 `messages` 表。
  - 通过 `@bus.on_event` 注册。

### 4.6. 程序入口 (`main.py`)
- 使用 FastAPI 的 `lifespan` 机制。
- **启动顺序**：
  1. 初始化 DB。
  2. 注册所有 Bus 消费者 (Fanfou, DB)。
  3. 启动 Feishu 独立线程。
  4. 使用 `asyncio.create_task` 启动 Telegram Polling。
- **关闭顺序**：
  1. 停止 Telegram Bot。
  2. (Feishu 线程随 Daemon 自动退出)。

## 5. 核心代码逻辑提示 (Prompt Hints)

请特别注意以下逻辑的实现：

1.  **Monkey Patch**: 必须演示如何通过 `sys.modules` 或直接导入模块属性的方式，修正 Feishu SDK 的 `loop` 绑定问题。
2.  **解耦**: Telegram 模块**不允许**导入 Fanfou 模块。所有交互必须通过 `bus` 进行。
3.  **配置**: 所有 Token (APP_ID, SECRET) 必须从 `app/core/config.py` 读取。

---

## 6. 输出要求
请生成完整的、可运行的 Python 代码项目，包含上述所有文件。对于 `pyproject.toml` 只需列出依赖即可。代码中需要包含详细的注释，解释“为什么这样做”（特别是 Monkey Patch 和 Event Bus 部分）。