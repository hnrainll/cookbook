# Cookbook - 多平台消息同步网关

## 架构概述

Event Bus 架构：多 Source（飞书/Telegram）→ EventBus → 多 Sink（Fanfou/Telegram 频道/SQLite）

### 核心组件
- `app/core/bus.py` — 异步 EventBus，publish/subscribe 模式
- `app/core/config.py` — Pydantic Settings 配置管理
- `app/core/auth.py` — AuthService 多平台 OAuth 管理
- `app/core/reply.py` — ReplyService 回复路由

### 消息流
1. Source (Feishu/Telegram) 接收消息 → 转换为 `UnifiedMessage`
2. `bus.publish(message)` → 并发分发给所有 handler
3. Sink (FanfouClient/TelegramClient/DatabaseManager) 处理消息

### 平台角色
| 平台 | Source | Sink | 说明 |
|------|--------|------|------|
| 飞书 | ✅ | - | WebSocket 长连接接收消息 |
| Telegram | ✅ | ✅ | Bot polling 接收消息 + 转发到频道 |
| Fanfou | - | ✅ | OAuth 1.0a 发送文本/图片 |
| SQLite | - | ✅ | 持久化所有消息和发送结果 |

### 关键设计决策
- 飞书 SDK 是同步阻塞的，运行在独立线程 + Monkey Patch 修复 event loop
- 使用 `lark.ws.Client` WebSocket 长连接（非 EventManager）
- Fanfou SDK 同步调用用 `run_in_executor` 包装
- Token 存储在 SQLite（auth_tokens/auth_requests 表），单用户模式，授权一次所有 Source 共享
- Telegram Bot 通过 aiogram + aiohttp-socks 支持代理访问
- Telegram polling 使用 `handle_signals=False` 避免与 uvicorn 信号处理冲突

## 开发约定
- Python >=3.12, 包管理用 `uv`
- `make dev` — 开发模式启动（热重载）
- `make run` — 生产模式启动
- `make test` — 运行测试
- `make install` — 安装依赖
- 日志: loguru
- 异步数据库: aiosqlite

## 目录结构
```
app/
├── core/          # 核心组件 (bus, config, auth, reply)
├── schemas/       # 数据模型 (UnifiedMessage)
├── utils/         # 工具函数 (image, feishu)
└── services/
    ├── platforms/
    │   ├── feishu/    # 飞书 Source
    │   ├── telegram/  # Telegram Source + Sink（频道转发）
    │   └── fanfou/    # Fanfou Sink
    └── storage/       # SQLite Sink
```
