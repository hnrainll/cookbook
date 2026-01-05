"""
FastAPI Main Application Entry Point
FastAPI 主程序入口 - 整合所有组件

这是整个系统的入口，负责：
1. 使用 Lifespan 管理应用生命周期
2. 按正确顺序启动/停止所有组件
3. 注册路由和中间件
4. 初始化日志系统
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from loguru import logger

from app.core.config import settings
from app.services.storage.db import init_database


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
    
    使用 FastAPI 的 Lifespan 机制管理资源：
    - 启动时：初始化所有组件
    - 关闭时：优雅地停止所有组件
    
    启动顺序很重要：
    1. 数据库（最基础）
    2. 消费者（Fanfou, DB）注册到事件总线
    3. 生产者（Feishu, Telegram）启动
    
    Args:
        app: FastAPI 应用实例
    
    Yields:
        控制权交给 FastAPI
    """
    logger.info("=" * 60)
    logger.info("Starting Message Sync Gateway...")
    logger.info("=" * 60)
    
    # ===== 启动阶段 =====
    try:
        # Step 1: 初始化并启动数据库
        if settings.database_enabled:
            logger.info("Initializing database...")
            db_manager = init_database()
            await db_manager.start()
        else:
            logger.info("Database disabled in config")
            db_manager = None
        
        # Step 2: 初始化并启动 Fanfou 客户端
        fanfou_client = None
        if settings.fanfou_enabled:
            logger.info("Initializing Fanfou client...")
            from app.services.platforms.fanfou.client import init_fanfou
            fanfou_client = init_fanfou()
            await fanfou_client.start()
        else:
            logger.info("Fanfou disabled in config")
        
        # Step 3: 初始化并启动 Telegram 客户端
        telegram_client = None
        if settings.telegram_enabled:
            logger.info("Initializing Telegram client...")
            from app.services.platforms.telegram.client import init_telegram
            telegram_client = init_telegram()
            await telegram_client.start()
        else:
            logger.info("Telegram disabled in config")
        
        # Step 4: 初始化并启动飞书客户端（独立线程）
        feishu_manager = None
        if settings.feishu_enabled:
            logger.info("Initializing Feishu client...")
            from app.services.platforms.feishu.client import init_feishu
            
            # 获取当前事件循环
            main_loop = asyncio.get_event_loop()
            feishu_manager = init_feishu(main_loop)
            feishu_manager.start()
        else:
            logger.info("Feishu disabled in config")
        
        # 打印事件总线状态
        from app.core.bus import bus
        handler_count = bus.get_handler_count()
        logger.info(f"Event bus initialized with {handler_count} handlers")
        
        logger.info("=" * 60)
        logger.info("✅ All components started successfully!")
        logger.info("=" * 60)
        
        # 让出控制权给 FastAPI
        yield
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}", exc_info=True)
        raise
    
    # ===== 关闭阶段 =====
    finally:
        logger.info("=" * 60)
        logger.info("Shutting down Message Sync Gateway...")
        logger.info("=" * 60)
        
        # 按相反顺序关闭组件
        
        # Step 1: 停止 Telegram 客户端
        if telegram_client:
            logger.info("Stopping Telegram client...")
            try:
                await telegram_client.stop()
            except Exception as e:
                logger.error(f"Error stopping Telegram client: {e}")
        
        # Step 2: 停止飞书客户端（daemon 线程会自动退出）
        if feishu_manager:
            logger.info("Stopping Feishu client...")
            try:
                feishu_manager.stop()
            except Exception as e:
                logger.error(f"Error stopping Feishu client: {e}")
        
        # Step 3: 停止 Fanfou 客户端
        if fanfou_client:
            logger.info("Stopping Fanfou client...")
            try:
                await fanfou_client.stop()
            except Exception as e:
                logger.error(f"Error stopping Fanfou client: {e}")
        
        # Step 4: 停止数据库
        if db_manager:
            logger.info("Stopping database...")
            try:
                await db_manager.stop()
            except Exception as e:
                logger.error(f"Error stopping database: {e}")
        
        logger.info("=" * 60)
        logger.info("✅ Shutdown complete!")
        logger.info("=" * 60)


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="Multi-platform message synchronization gateway",
    version="1.0.0",
    lifespan=lifespan
)


# ===== 路由注册 =====

@app.get("/")
async def root():
    """健康检查端点"""
    from app.core.bus import bus
    
    return {
        "status": "running",
        "app": settings.app_name,
        "handlers": bus.get_handler_count(),
        "platforms": {
            "telegram": settings.telegram_enabled,
            "feishu": settings.feishu_enabled,
            "fanfou": settings.fanfou_enabled,
            "database": settings.database_enabled
        }
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


@app.get("/stats")
async def stats():
    """统计信息"""
    from app.core.bus import bus
    from app.services.storage.db import db_manager
    
    message_count = 0
    if db_manager:
        try:
            message_count = await db_manager.get_message_count()
        except Exception as e:
            logger.error(f"Error getting message count: {e}")
    
    return {
        "handlers": bus.get_handler_count(),
        "total_messages": message_count
    }


@app.get("/messages")
async def get_messages(limit: int = 10):
    """获取最近的消息"""
    from app.services.storage.db import db_manager
    
    if not db_manager:
        return {"error": "Database not enabled"}
    
    try:
        messages = await db_manager.get_recent_messages(limit)
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return {"error": str(e)}


# 注册飞书 Webhook 路由
if settings.feishu_enabled:
    from app.services.platforms.feishu.handler import router as feishu_router
    app.include_router(feishu_router)


# ===== 主函数 =====

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server at {settings.host}:{settings.port}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
