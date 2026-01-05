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
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # ===== FastAPI 配置 =====
    app_name: str = Field(default="Message Sync Gateway", description="应用名称")
    debug: bool = Field(default=False, description="调试模式")
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8000, description="服务监听端口")
    
    # ===== 飞书配置 =====
    feishu_app_id: str = Field(default="", description="飞书应用 App ID")
    feishu_app_secret: str = Field(default="", description="飞书应用 App Secret")
    feishu_verification_token: str = Field(default="", description="飞书事件订阅验证 Token")
    feishu_encrypt_key: str = Field(default="", description="飞书事件加密 Key (可选)")
    feishu_enabled: bool = Field(default=False, description="是否启用飞书集成")
    
    # ===== Telegram 配置 =====
    telegram_bot_token: str = Field(default="", description="Telegram Bot Token")
    telegram_enabled: bool = Field(default=False, description="是否启用 Telegram 集成")
    
    # ===== Fanfou 配置 =====
    fanfou_consumer_key: str = Field(default="", description="Fanfou Consumer Key")
    fanfou_consumer_secret: str = Field(default="", description="Fanfou Consumer Secret")
    fanfou_access_token: str = Field(default="", description="Fanfou Access Token")
    fanfou_access_secret: str = Field(default="", description="Fanfou Access Token Secret")
    fanfou_enabled: bool = Field(default=False, description="是否启用 Fanfou 集成")
    
    # ===== 数据库配置 =====
    database_path: str = Field(default="./data/messages.db", description="SQLite 数据库文件路径")
    database_enabled: bool = Field(default=True, description="是否启用数据库存储")
    
    # ===== 日志配置 =====
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: str = Field(default="./logs/app.log", description="日志文件路径")


# 单例配置对象
# 在整个应用中使用此实例访问配置
settings = Settings()
