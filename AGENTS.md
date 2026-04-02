# AGENTS.md

本文件用于帮助新的代理会话快速理解并接手本仓库。

如果是新会话，建议先读本文件，再开始分析、修改或运行项目。

## 项目概览

`cookbook` 是一个多平台消息同步网关。

核心目标：
- 从飞书、Telegram 接收消息
- 转换为统一的 `UnifiedMessage`
- 通过异步 `EventBus` 分发给多个下游 sink
- 把结果回传给原始 source 用户

当前主要链路：
- Feishu -> EventBus -> Fanfou / Telegram Channel / Mastodon / Threads / SQLite
- Telegram -> EventBus -> Fanfou / Telegram Channel / Mastodon / Threads / SQLite

## 技术栈

- Python 3.12+
- FastAPI
- uv / pyproject
- aiogram
- lark-oapi
- httpx
- aiosqlite
- pytest
- ruff
- ty

## 启动入口

- HTTP / 生命周期入口: `app/main.py`
- 配置定义: `app/core/config.py`
- 统一消息模型: `app/schemas/event.py`
- 异步事件总线: `app/core/bus.py`
- 通用认证回调路由: `app/routes/auth.py`
- Threads callback 路由: `app/services/platforms/threads/handler.py`

## 核心架构

系统不是以 HTTP API 为中心，而是以“启动多个 connector + 总线分发消息”为中心。

主流程：
1. FastAPI 启动
2. 初始化数据库
3. 初始化 `AuthService` 和 `ReplyService`
4. 按配置启动各平台 client
5. source 平台把消息转成 `UnifiedMessage`
6. `EventBus.publish()` 并发广播给所有 handler
7. sink 平台分别处理并通过 `ReplyService` 回给原 source

## 平台角色

### Feishu

- 角色: Source
- 实现: `app/services/platforms/feishu/client.py`
- 通信方式: WebSocket 长连接
- 特点:
  - 运行在独立线程
  - 对 SDK 的 event loop 问题做了 monkey patch
  - 支持文本、图片、富文本
  - 富文本会提取第一组文本和第一张图
  - 会做消息去重
  - 图片会下载并压缩，然后写入 `data/images/`

### Telegram

- 角色: Source + Sink
- 实现: `app/services/platforms/telegram/client.py`
- Source 方式: aiogram polling
- Sink 方式: 转发到配置的频道或群组
- 当前限制:
  - Telegram source 目前只处理文本消息
  - sink 支持文本和图片

### Fanfou

- 角色: Sink
- 实现: `app/services/platforms/fanfou/client.py`
- 功能:
  - 发送文本
  - 发送图片
  - 处理 `/login` 和 `/logout`
  - 通过 `FanfouAuthHandler` 处理 OAuth 1.0a

### Mastodon

- 角色: Sink
- 实现: `app/services/platforms/mastodon/client.py`
- 功能:
  - Access Token 直连发文本
  - 先上传媒体再发图文状态

### Threads

- 角色: Sink
- 实现: `app/services/platforms/threads/client.py`
- 功能:
  - 发送文本消息到 Threads
  - 处理 Threads OAuth 2.0 授权
  - 提供 `GET /callback/threads?type=...` 管理回调确认接口
  - callback 后立即把短期 token 换成长期 token
  - 发帖前按刷新窗口自动刷新长期 token
- 当前限制:
  - 第一版只支持文本 sink
  - 不支持图片、视频、carousel
  - 图片消息会直接跳过

### SQLite

- 角色: Sink + OAuth Token Store
- 实现: `app/services/storage/db.py`
- 负责:
  - 持久化 `messages`
  - 记录 `sink_results`
  - 保存 OAuth `auth_tokens`
  - 保存 OAuth `auth_requests`

## 关键模块

- `app/core/bus.py`
  - 全局单例 `bus`
  - `publish()` 使用 `asyncio.gather(..., return_exceptions=True)`
  - 单个 sink 失败不会阻断其他 sink

- `app/core/auth.py`
  - 统一管理平台授权处理器
  - 处理 `/login <platform>` 和 `/logout <platform>` 的后续逻辑
  - OAuth 回调建议显式带 `platform` 参数

- `app/routes/auth.py`
  - 提供通用 `/auth` OAuth 回调路由

- `app/services/platforms/threads/handler.py`
  - 提供 `/callback/threads` 轻量确认回调

- `app/core/reply.py`
  - sink 不直接依赖 source
  - 按 `message.source` 路由回复

- `app/schemas/event.py`
  - 所有平台内部都统一成 `UnifiedMessage`

## 运行命令

- 安装依赖: `make install`
- 开发模式: `make dev`
- 普通运行: `make run`
- 测试: `make test`
- 格式化: `make format`
- lint: `make lint`
- 类型检查: `make type`
- 完整检查: `make check`

生产脚本：
- 启动: `./start.sh`
- 停止: `./stop.sh`

## 建议的接手顺序

新会话建议按这个顺序理解项目：

1. 读 `AGENTS.md`
2. 读 `README.md`
3. 读 `app/main.py`
4. 读 `app/core/config.py`
5. 读 `app/core/bus.py`
6. 读 `app/schemas/event.py`
7. 再看具体平台实现
8. 修改前优先读相关测试

## 修改代码前的默认动作

- 先确认这次改动落在哪个模块边界
- 优先阅读相关测试文件
- 检查是否已有单例、总线注册、生命周期处理
- 不要绕过 `UnifiedMessage` 和 `EventBus` 直接耦合平台
- 不要随意改动用户未要求的现有行为

## 测试与校验

当前仓库测试是理解系统行为的重要依据。

重点测试文件：
- `tests/test_integration.py`
- `tests/test_reply_service.py`
- `tests/test_auth_service.py`
- `tests/test_db.py`
- `tests/test_fanfou_client.py`
- `tests/test_feishu_client.py`
- `tests/test_mastodon_client.py`
- `tests/test_threads_client.py`
- `tests/test_telegram_client.py` 不存在，Telegram 逻辑主要分散在其他测试里确认

已知状态：
- 本仓库在最近一次检查时 `uv run pytest tests/ -q` 通过
- 结果为 `68 passed`

## 当前实现约束和风险

- Fanfou OAuth 当前偏单用户模式
- Fanfou token 获取逻辑使用“取最近一个可用 token”，不是严格按 source 用户隔离
- `FanfouAuthHandler` 中 `source_platform` 的保存和删除逻辑偏向 `feishu`
- Threads 第一版也沿用共享 token 模式
- Threads token 采用“长 token 入库 + 发帖前懒刷新”的策略
- 只有刷新失败且鉴权不可恢复时，才需要重新授权
- Telegram source 目前只处理文本，不处理图片输入
- Feishu webhook 路由主要用于 URL 验证，真实消息接收依赖 WebSocket
- 图片二进制只在内存中流转，数据库只保存元信息和路径

## 常见文件定位

- 新增配置: `app/core/config.py`
- 修改启动顺序: `app/main.py`
- 改消息分发: `app/core/bus.py`
- 改统一模型: `app/schemas/event.py`
- 改授权流程: `app/core/auth.py` 或 `app/services/platforms/fanfou/client.py`
- 改回复路由: `app/core/reply.py`
- 改数据库结构或持久化: `app/services/storage/db.py`
- 改飞书消息解析: `app/services/platforms/feishu/client.py`
- 改飞书富文本提取: `app/utils/feishu.py`
- 改图片压缩: `app/utils/image.py`

## 协作约定

- 默认先理解现有实现，再修改
- 默认保持现有架构边界，不做无关重构
- 修改后优先运行最小相关测试；如果改动范围大，再跑 `make test` 或 `uv run pytest tests/ -q`
- 如果新会话没有上下文，先读本文件，不要直接假设业务目标

## 给未来会话的一句话

如果用户只给出很短的任务说明，先读 `AGENTS.md`、`README.md` 和相关测试，再动手。
