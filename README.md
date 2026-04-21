# Cookbook - 多平台消息同步网关

通过飞书/Telegram 机器人向饭否、Mastodon、Threads、Bluesky 和 Telegram 频道同步消息，基于 Event Bus 架构实现多 Source → 多 Sink 的消息流转。

## 架构

```
Sources                    Core                        Sinks
┌──────────┐         ┌──────────────┐           ┌──────────────┐
│ Feishu   │────┐    │  EventBus    │     ┌────▶│ Fanfou       │
│ (WebSocket)   ├───▶│  publish()   │─────┤     └──────────────┘
└──────────┘    │    └──────────────┘     │     ┌──────────────┐
┌──────────┐    │                         ├────▶│ Telegram 频道 │
│ Telegram │────┘                         │     └──────────────┘
│ (Polling)│                              │     ┌──────────────┐
└──────────┘                              ├────▶│ Mastodon     │
                                          │     └──────────────┘
                                          │     ┌──────────────┐
                                          ├────▶│ Threads      │
                                          │     └──────────────┘
                                          │     ┌──────────────┐
                                          ├────▶│ Bluesky      │
                                          │     └──────────────┘
                                          │     ┌──────────────┐
                                          └────▶│ SQLite       │
                                                └──────────────┘
```

## 功能

- 飞书：文本、图片、富文本消息同步到饭否和 Telegram 频道
- Telegram：文本消息同步到饭否和 Telegram 频道
- Mastodon：文本、图片消息同步到 `mastodon.social` 或其他实例
- Threads：文本、图片消息同步到 Threads（图片需要配置公网 HTTPS 可访问的 `PUBLIC_BASE_URL`）
- Bluesky：文本、图片消息同步到 Bluesky
- Telegram 频道转发：支持文本和图片，支持 `@username` 和数字 ID 两种频道配置
- 图片自动压缩（≤2MB）
- OAuth 授权管理（`/login fanfou`、`/login threads`、`/logout fanfou`、`/logout threads`），单用户模式，授权一次所有 Source 共享
- 消息持久化到 SQLite，发送结果记录到 sink_results 表
- 消息去重、按平台做字符限制检查
- 支持代理访问 Telegram API
- Threads 长期 token 自动刷新
- Threads 图片发布通过 `/cookbook/media/{filename}` 暴露本地图片，需保证 `PUBLIC_BASE_URL` 可被 Threads 访问；发布前会等待图片容器处理完成
- OAuth 回调建议显式带平台参数，例如 `/auth?platform=fanfou`、`/auth?platform=threads`
- Threads 管理回调使用 `/callback/threads?type=uninstall` 或 `/callback/threads?type=delete`

## 快速开始

```bash
# 安装依赖
make install

# 启用 git hooks（提交前自动执行 make check）
make install-hooks

# 代码格式化
make format

# 静态检查
make lint

# 类型检查
make type

# 完整检查（lint + type + test）
make check

# 配置环境变量
cp .env.example .env
# 编辑 .env，填写各平台的认证信息

# 本地开发（热重载）
make dev

# 生产部署
./start.sh

# 停止服务
./stop.sh
```

## 测试

```bash
make test
```

## 代码质量

- `ruff`：代码格式化和 lint
- `ty`：类型检查
- Git pre-commit hook：提交前自动执行 `make check`

## 目录结构

```
app/
├── core/           # 核心组件
│   ├── bus.py      # 异步 EventBus
│   ├── config.py   # Pydantic Settings 配置
│   ├── auth.py     # AuthService 多平台 OAuth 管理
│   └── reply.py    # ReplyService 回复路由
├── routes/
│   └── auth.py     # 通用 OAuth 回调路由
├── schemas/
│   └── event.py    # UnifiedMessage 统一消息模型
├── utils/
│   ├── image.py    # 图片压缩
│   └── feishu.py   # 飞书富文本解析
├── services/
│   ├── platforms/
│   │   ├── feishu/     # 飞书 Source (lark.ws.Client WebSocket)
│   │   ├── telegram/   # Telegram Source + Sink (aiogram polling + 频道转发)
│   │   ├── fanfou/     # 饭否 Sink (httpx 异步)
│   │   ├── mastodon/   # Mastodon Sink (httpx 异步)
│   │   ├── threads/    # Threads Sink + OAuth 2.0 + callback
│   │   └── bluesky/    # Bluesky Sink
│   └── storage/
│       └── db.py       # SQLite Sink (aiosqlite)
└── main.py         # FastAPI 入口
```

## 感谢

- [fanfou-sdk-python](https://github.com/LitoMore/fanfou-sdk-python)
- [nofan](https://github.com/fanfoujs/nofan)
