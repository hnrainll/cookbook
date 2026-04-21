"""
Configuration Management Module
配置管理模块 - 使用 Pydantic Settings 从环境变量加载配置
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类
    使用 Pydantic Settings 自动从环境变量或 .env 文件加载配置
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # ===== FastAPI 配置 =====
    debug: bool = Field(default=False, description="调试模式")
    app_name: str = Field(default="Message Sync Gateway", description="应用名称")
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8009, description="服务监听端口")
    public_contact_email: str = Field(
        default="privacy@example.com",
        description="公开页面使用的联系邮箱",
    )
    public_base_url: str = Field(
        default="",
        description="服务公网基础 URL，用于生成第三方平台可访问的媒体链接",
    )

    # ===== 飞书配置 =====
    feishu_enabled: bool = Field(default=False, description="是否启用飞书集成")
    feishu_app_id: str = Field(default="", description="飞书应用 App ID")
    feishu_app_secret: str = Field(default="", description="飞书应用 App Secret")

    # ===== Telegram 配置 =====
    telegram_enabled: bool = Field(default=False, description="是否启用 Telegram 集成")
    telegram_bot_token: str = Field(default="", description="Telegram Bot Token")
    telegram_channel_id: str = Field(default="", description="Telegram 频道/群组 ID，用于消息同步")
    telegram_proxy: str = Field(
        default="", description="Telegram 代理地址，如 http://127.0.0.1:7897"
    )

    # ===== Fanfou 配置 =====
    fanfou_enabled: bool = Field(default=False, description="是否启用 Fanfou 集成")
    fanfou_consumer_key: str = Field(default="", description="Fanfou Consumer Key")
    fanfou_consumer_secret: str = Field(default="", description="Fanfou Consumer Secret")
    fanfou_oauth_callback: str = Field(
        default="http://127.0.0.1:8009/auth?platform=fanfou",
        description="Fanfou OAuth Callback URL",
    )

    # ===== Mastodon 配置 =====
    mastodon_enabled: bool = Field(default=False, description="是否启用 Mastodon 集成")
    mastodon_base_url: str = Field(
        default="https://mastodon.social",
        description="Mastodon 实例地址",
    )
    mastodon_access_token: str = Field(default="", description="Mastodon Access Token")
    mastodon_visibility: str = Field(
        default="public",
        description="Mastodon 发帖可见性: public/unlisted/private/direct",
    )

    # ===== Threads 配置 =====
    threads_enabled: bool = Field(default=False, description="是否启用 Threads 集成")
    threads_app_id: str = Field(default="", description="Threads App ID")
    threads_app_secret: str = Field(default="", description="Threads App Secret")
    threads_redirect_uri: str = Field(
        default="http://127.0.0.1:8009/auth?platform=threads",
        description="Threads OAuth Redirect URI",
    )
    threads_base_url: str = Field(
        default="https://graph.threads.net",
        description="Threads Graph API Base URL",
    )
    threads_refresh_window_days: int = Field(
        default=7,
        description="Threads token 提前刷新窗口（天）",
    )

    # ===== Bluesky 配置 =====
    bluesky_enabled: bool = Field(default=False, description="是否启用 Bluesky 集成")
    bluesky_service_url: str = Field(
        default="https://bsky.social",
        description="Bluesky ATProto 服务地址",
    )
    bluesky_identifier: str = Field(
        default="",
        description="Bluesky 登录标识，通常为 handle 或邮箱",
    )
    bluesky_app_password: str = Field(default="", description="Bluesky app password")

    # ===== 数据库配置 =====
    database_enabled: bool = Field(default=True, description="是否启用数据库存储")
    database_path: str = Field(default="./data/messages.db", description="SQLite 数据库文件路径")

    # ===== 日志配置 =====
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: str = Field(default="./logs/app.log", description="日志文件路径")


# 单例配置对象
# 在整个应用中使用此实例访问配置
settings = Settings()
