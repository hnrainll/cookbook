"""
System routes.
系统状态与基础查询路由。
"""

from fastapi import APIRouter
from loguru import logger

from app.core.config import settings
from app.services.storage.db import DatabaseManager

router = APIRouter(tags=["system"])


@router.get("/")
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
            "mastodon": settings.mastodon_enabled,
            "threads": settings.threads_enabled,
            "bluesky": settings.bluesky_enabled,
            "database": settings.database_enabled,
        },
    }


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/stats")
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


@router.get("/messages")
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
