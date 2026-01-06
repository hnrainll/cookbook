"""
SQLite Storage Sink
SQLite 存储消费者 - 将消息持久化到本地数据库

这是一个 Sink（消费者），职责：
1. 监听事件总线的消息
2. 异步写入 SQLite 数据库
3. 提供消息查询接口（可选）
"""
import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Optional

import aiosqlite
from loguru import logger

from app.core.bus import bus
from app.core.config import settings
from app.schemas.event import UnifiedMessage


class DatabaseManager:
    """
    数据库管理器
    
    使用 aiosqlite 实现异步数据库操作
    存储所有经过系统的消息，用于：
    - 审计和追溯
    - 消息归档
    - 统计分析
    """
    
    _instance: ClassVar[Optional["DatabaseManager"]] = None
    
    def __init__(self):
        """初始化数据库管理器"""
        self.db_path = settings.database_path
        self.conn: Optional[aiosqlite.Connection] = None
        
        logger.info(f"DatabaseManager initialized with path: {self.db_path}")
    
    async def start(self) -> None:
        """启动数据库连接"""
        if self.conn:
            logger.warning("Database already connected")
            return
        
        # 确保数据库目录存在
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # 连接数据库（如果文件不存在会自动创建）
        self.conn = await aiosqlite.connect(self.db_path)
        
        # 创建表结构
        await self._create_tables()
        
        logger.info(f"Database connected: {self.db_path}")
    
    async def stop(self) -> None:
        """停止数据库连接"""
        if not self.conn:
            logger.warning("Database not connected")
            return
        
        await self.conn.close()
        self.conn = None
        logger.info("Database connection closed")
    
    async def _create_tables(self) -> None:
        """
        创建数据库表结构
        
        messages 表字段：
        - id: 主键，自增
        - event_id: 消息唯一标识（UUID）
        - source: 消息来源平台
        - content: 消息文本内容
        - sender_id: 发送者 ID
        - sender_name: 发送者名称
        - chat_id: 会话 ID
        - raw_data: 原始数据（JSON 格式）
        - timestamp: 消息时间戳
        - created_at: 入库时间
        """
        if not self.conn:
            raise RuntimeError("Database not connected")
        
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                sender_name TEXT,
                chat_id TEXT,
                raw_data TEXT,
                timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引，提高查询性能
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_id ON messages(event_id)
        """)
        
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_source ON messages(source)
        """)
        
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sender_id ON messages(sender_id)
        """)
        
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)
        """)
        
        await self.conn.commit()
        
        logger.info("Database tables created/verified")
    
    async def save_message(self, message: UnifiedMessage) -> bool:
        """
        保存消息到数据库
        
        Args:
            message: 统一消息对象
        
        Returns:
            是否成功
        """
        if not self.conn:
            logger.error("Database not connected")
            return False
        
        try:
            # 将 raw_data 转换为 JSON 字符串
            import json
            raw_data_json = json.dumps(message.raw_data)
            
            # 插入数据
            await self.conn.execute("""
                INSERT INTO messages (
                    event_id, source, content, sender_id, sender_name,
                    chat_id, raw_data, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(message.event_id),
                message.source,
                message.content,
                message.sender_id,
                message.sender_name,
                message.chat_id,
                raw_data_json,
                message.timestamp.isoformat()
            ))
            
            await self.conn.commit()
            
            logger.debug(f"Message {message.event_id} saved to database")
            return True
            
        except aiosqlite.IntegrityError:
            # event_id 重复，消息已存在
            logger.warning(f"Message {message.event_id} already exists in database")
            return False
            
        except Exception as e:
            logger.error(f"Failed to save message {message.event_id}: {e}", exc_info=True)
            return False
    
    async def handle_message(self, message: UnifiedMessage) -> None:
        """
        处理消息事件（事件总线回调）
        
        这个方法会被事件总线调用，当有新消息时
        
        Args:
            message: 统一消息对象
        """
        try:
            logger.info(
                f"Database handler processing message {message.event_id} "
                f"from {message.source}"
            )
            
            # 保存到数据库
            success = await self.save_message(message)
            
            if success:
                logger.info(f"Successfully saved message {message.event_id} to database")
            else:
                logger.warning(f"Failed to save message {message.event_id} to database")
        
        except Exception as e:
            logger.error(
                f"Error handling message {message.event_id} in database: {e}",
                exc_info=True
            )
            raise
    
    async def get_message_count(self) -> int:
        """
        获取消息总数
        
        Returns:
            消息总数
        """
        if not self.conn:
            return 0
        
        cursor = await self.conn.execute("SELECT COUNT(*) FROM messages")
        row = await cursor.fetchone()
        return row[0] if row else 0
    
    async def get_recent_messages(self, limit: int = 10) -> list:
        """
        获取最近的消息
        
        Args:
            limit: 返回数量
        
        Returns:
            消息列表
        """
        if not self.conn:
            return []
        
        cursor = await self.conn.execute("""
            SELECT event_id, source, content, sender_name, timestamp
            FROM messages
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        rows = await cursor.fetchall()
        
        return [
            {
                "event_id": row[0],
                "source": row[1],
                "content": row[2],
                "sender_name": row[3],
                "timestamp": row[4]
            }
            for row in rows
        ]
    
    @classmethod
    def get_instance(cls) -> Optional["DatabaseManager"]:
        """获取单例实例（可能为 None）"""
        return cls._instance
    
    @classmethod
    def create_instance(cls) -> "DatabaseManager":
        """
        创建单例实例并注册到事件总线
        
        Returns:
            DatabaseManager 实例
        
        Raises:
            RuntimeError: 如果实例已存在
        """
        if cls._instance is not None:
            raise RuntimeError("DatabaseManager instance already exists")
        cls._instance = cls()
        
        # 注册到事件总线
        bus.register(cls._instance.handle_message)
        
        logger.info("Database manager registered to event bus")
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        cls._instance = None
