"""
FastAPI Main Application Entry Point
FastAPI 主程序入口 - 整合所有组件
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from loguru import logger

from app.core.config import settings
from app.services.storage.db import DatabaseManager


# 配置日志
logger.add(
    settings.log_file,
    rotation="1 day",
    retention="7 days",
    level=settings.log_level,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    应用生命周期管理

    启动顺序：
    1. 数据库（最基础）
    2. AuthService / ReplyService（核心服务）
    3. Fanfou Sink（注册 AuthHandler + EventBus）
    4. Telegram / Feishu Source（启动后注册 ReplyService）
    """
    logger.info("=" * 60)
    logger.info("Starting Message Sync Gateway...")
    logger.info("=" * 60)

    db_manager = None
    fanfou_client = None
    telegram_client = None
    feishu_manager = None
    auth_service = None
    reply_service = None

    try:
        # Step 1: 数据库
        if settings.database_enabled:
            logger.info("Initializing database...")
            db_manager = DatabaseManager.create_instance()
            await db_manager.start()

        # Step 2: AuthService + ReplyService
        from app.core.auth import AuthService
        from app.core.reply import ReplyService

        auth_service = AuthService.create_instance()
        reply_service = ReplyService.create_instance()

        # Step 3: Fanfou Sink
        if settings.fanfou_enabled:
            logger.info("Initializing Fanfou client...")
            from app.services.platforms.fanfou.client import FanfouClient, FanfouAuthHandler
            fanfou_client = FanfouClient.create_instance()
            await fanfou_client.start()

            # 注册 FanfouAuthHandler 到 AuthService
            fanfou_auth_handler = FanfouAuthHandler()
            auth_service.register("fanfou", fanfou_auth_handler)

        # Step 4: Telegram Source + Sink
        if settings.telegram_enabled:
            logger.info("Initializing Telegram client...")
            from app.services.platforms.telegram.client import TelegramClient
            telegram_client = TelegramClient.create_instance()
            await telegram_client.start()

            # 注册 Telegram 回复方法到 ReplyService
            from app.schemas.event import MessageSource
            reply_service.register(
                MessageSource.TELEGRAM,
                reply_handler=telegram_client.reply_to_message,
                send_handler=telegram_client.send_to_user,
            )

            # 注册 Telegram Sink（转发消息到频道）
            if settings.telegram_channel_id:
                from app.core.bus import bus as event_bus
                event_bus.register(telegram_client.handle_message)
                logger.info(f"Telegram channel sink registered, channel_id={settings.telegram_channel_id}")

        # Step 5: Feishu Source
        if settings.feishu_enabled:
            logger.info("Initializing Feishu client...")
            from app.services.platforms.feishu.client import FeishuManager
            from app.schemas.event import MessageSource

            main_loop = asyncio.get_event_loop()
            feishu_manager = FeishuManager.create_instance(main_loop)
            feishu_manager.start()

            # 注册飞书回复方法到 ReplyService
            reply_service.register(
                MessageSource.FEISHU,
                reply_handler=feishu_manager._reply_for_reply_service,
                send_handler=feishu_manager._send_for_reply_service,
            )

        # 打印状态
        from app.core.bus import bus
        handler_count = bus.get_handler_count()
        logger.info(f"Event bus initialized with {handler_count} handlers")

        logger.info("=" * 60)
        logger.info("All components started successfully!")
        logger.info("=" * 60)

        yield

    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        raise

    finally:
        logger.info("Shutting down Message Sync Gateway...")

        if telegram_client:
            try:
                await telegram_client.stop()
            except Exception as e:
                logger.error(f"Error stopping Telegram: {e}")

        if feishu_manager:
            try:
                feishu_manager.stop()
            except Exception as e:
                logger.error(f"Error stopping Feishu: {e}")

        if fanfou_client:
            try:
                await fanfou_client.stop()
            except Exception as e:
                logger.error(f"Error stopping Fanfou: {e}")

        if db_manager:
            try:
                await db_manager.stop()
            except Exception as e:
                logger.error(f"Error stopping database: {e}")

        # 重置单例以便测试
        from app.core.auth import AuthService
        from app.core.reply import ReplyService
        AuthService.reset_instance()
        ReplyService.reset_instance()

        logger.info("Shutdown complete!")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="Multi-platform message synchronization gateway",
    version="1.0.0",
    lifespan=lifespan,
)


# ===== 路由注册 =====

@app.get("/")
async def root():
    from app.core.bus import bus
    return {
        "status": "running",
        "app": settings.app_name,
        "handlers": bus.get_handler_count(),
        "platforms": {
            "telegram": settings.telegram_enabled,
            "feishu": settings.feishu_enabled,
            "fanfou": settings.fanfou_enabled,
            "database": settings.database_enabled,
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/stats")
async def stats():
    from app.core.bus import bus
    message_count = 0
    db_manager = DatabaseManager.get_instance()
    if db_manager:
        try:
            message_count = await db_manager.get_message_count()
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
    return {"handlers": bus.get_handler_count(), "total_messages": message_count}


@app.get("/messages")
async def get_messages(limit: int = 10):
    db_manager = DatabaseManager.get_instance()
    if not db_manager:
        return {"error": "Database not enabled"}
    try:
        messages = await db_manager.get_recent_messages(limit)
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return {"error": str(e)}


# 注册 Webhook + OAuth 路由
from app.services.platforms.feishu.handler import router as feishu_router
app.include_router(feishu_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
