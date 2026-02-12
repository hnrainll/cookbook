# Cookbook - 多平台消息同步网关

通过飞书/Telegram 机器人向饭否发送消息，基于 Event Bus 架构实现多 Source → 多 Sink 的消息流转。

## 架构

```
Sources                    Core                        Sinks
┌──────────┐         ┌──────────────┐           ┌──────────────┐
│ Feishu   │────┐    │  EventBus    │     ┌────▶│ Fanfou       │
│ (WebSocket)   ├───▶│  publish()   │─────┤     └──────────────┘
└──────────┘    │    └──────────────┘     │     ┌──────────────┐
┌──────────┐    │                         └────▶│ SQLite       │
│ Telegram │────┘                               └──────────────┘
│ (Polling)│
└──────────┘
```

## 功能

- 飞书：文本、图片、富文本消息转发到饭否
- Telegram：文本消息转发到饭否
- 图片自动压缩（≤2MB）
- 多平台 OAuth 授权管理（`/login fanfou`、`/logout fanfou`）
- 消息持久化到 SQLite
- 消息去重、140 字符限制检查

## 快速开始

```bash
# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env，填写各平台的认证信息

# 本地开发
uv run uvicorn app.main:app --host 0.0.0.0 --port 8009 --reload

# 生产部署
./start.sh

# 停止服务
./stop.sh
```

## 测试

```bash
uv run pytest tests/ -v
```

## 目录结构

```
app/
├── core/           # 核心组件
│   ├── bus.py      # 异步 EventBus
│   ├── config.py   # Pydantic Settings 配置
│   ├── auth.py     # AuthService 多平台 OAuth 管理
│   └── reply.py    # ReplyService 回复路由
├── schemas/
│   └── event.py    # UnifiedMessage 统一消息模型
├── utils/
│   ├── image.py    # 图片压缩
│   └── feishu.py   # 飞书富文本解析
├── services/
│   ├── platforms/
│   │   ├── feishu/     # 飞书 Source (lark.ws.Client WebSocket)
│   │   ├── telegram/   # Telegram Source (aiogram polling)
│   │   └── fanfou/     # 饭否 Sink (httpx 异步)
│   └── storage/
│       └── db.py       # SQLite Sink (aiosqlite)
└── main.py         # FastAPI 入口
```

## 感谢

- [fanfou-sdk-python](https://github.com/LitoMore/fanfou-sdk-python)
- [nofan](https://github.com/fanfoujs/nofan)
