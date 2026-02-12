"""
SQLite Storage Sink + Token Manager
SQLite 存储消费者 + 认证 Token 管理

职责：
1. 监听事件总线的消息，持久化到 messages 表
2. 管理 sink_results 表（各 Sink 的发送结果）
3. 管理 auth_tokens / auth_requests 表（OAuth Token 存储）
"""
import json
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

    使用 aiosqlite 实现异步数据库操作。
    包含 messages、sink_results、auth_tokens、auth_requests 四张表。
    """

    _instance: ClassVar[Optional["DatabaseManager"]] = None

    def __init__(self):
        self.db_path = settings.database_path
        self.conn: Optional[aiosqlite.Connection] = None
        logger.info(f"DatabaseManager initialized with path: {self.db_path}")

    async def start(self) -> None:
        if self.conn:
            logger.warning("Database already connected")
            return
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.db_path)
        await self._create_tables()
        logger.info(f"Database connected: {self.db_path}")

    async def stop(self) -> None:
        if not self.conn:
            return
        await self.conn.close()
        self.conn = None
        logger.info("Database connection closed")

    async def _create_tables(self) -> None:
        if not self.conn:
            raise RuntimeError("Database not connected")

        # messages 表（增强版）
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT NOT NULL DEFAULT 'text',
                sender_id TEXT NOT NULL,
                sender_name TEXT,
                chat_id TEXT,
                image_path TEXT,
                raw_data TEXT,
                timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # sink_results 表 — 记录各 Sink 平台的发送结果
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sink_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                sink_platform TEXT NOT NULL,
                status_id TEXT,
                status_url TEXT,
                response_data TEXT,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, sink_platform)
            )
        """)

        # auth_tokens 表 — 已授权的永久 token
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_platform TEXT NOT NULL,
                source_user_id TEXT NOT NULL,
                sink_platform TEXT NOT NULL,
                token_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_platform, source_user_id, sink_platform)
            )
        """)

        # auth_requests 表 — OAuth 流程中的临时 request token
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_requests (
                oauth_token TEXT PRIMARY KEY,
                source_platform TEXT NOT NULL,
                source_user_id TEXT NOT NULL,
                sink_platform TEXT NOT NULL,
                token_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 索引
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_id ON messages(event_id)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_source ON messages(source)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sender_id ON messages(sender_id)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)"
        )
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sink_results_event ON sink_results(event_id)"
        )

        await self.conn.commit()
        logger.info("Database tables created/verified")

    # ===== messages 操作 =====

    async def save_message(self, message: UnifiedMessage) -> bool:
        if not self.conn:
            logger.error("Database not connected")
            return False
        try:
            raw_data_json = json.dumps(message.raw_data)
            await self.conn.execute("""
                INSERT INTO messages (
                    event_id, source, content, message_type, sender_id,
                    sender_name, chat_id, image_path, raw_data, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(message.event_id),
                message.source,
                message.content,
                message.message_type,
                message.sender_id,
                message.sender_name,
                message.chat_id,
                message.image_path,
                raw_data_json,
                message.timestamp.isoformat(),
            ))
            await self.conn.commit()
            logger.debug(f"Message {message.event_id} saved to database")
            return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Message {message.event_id} already exists")
            return False
        except Exception as e:
            logger.error(f"Failed to save message {message.event_id}: {e}", exc_info=True)
            return False

    async def handle_message(self, message: UnifiedMessage) -> None:
        """事件总线回调"""
        try:
            await self.save_message(message)
        except Exception as e:
            logger.error(f"Error in database handler: {e}", exc_info=True)
            raise

    async def get_message_count(self) -> int:
        if not self.conn:
            return 0
        cursor = await self.conn.execute("SELECT COUNT(*) FROM messages")
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def get_recent_messages(self, limit: int = 10) -> list:
        if not self.conn:
            return []
        cursor = await self.conn.execute("""
            SELECT event_id, source, content, message_type, sender_name, timestamp
            FROM messages ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        return [
            {
                "event_id": row[0], "source": row[1], "content": row[2],
                "message_type": row[3], "sender_name": row[4], "timestamp": row[5],
            }
            for row in rows
        ]

    # ===== sink_results 操作 =====

    async def save_sink_result(
        self,
        event_id: str,
        sink_platform: str,
        status_id: Optional[str] = None,
        status_url: Optional[str] = None,
        response_data: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> bool:
        if not self.conn:
            return False
        try:
            await self.conn.execute("""
                INSERT OR REPLACE INTO sink_results (
                    event_id, sink_platform, status_id, status_url,
                    response_data, success, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (event_id, sink_platform, status_id, status_url,
                  response_data, success, error_message))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save sink result: {e}")
            return False

    # ===== auth_requests (临时 request token) 操作 =====

    async def save_request_token(
        self,
        oauth_token: str,
        source_platform: str,
        source_user_id: str,
        sink_platform: str,
        token_data: str,
    ) -> bool:
        if not self.conn:
            return False
        try:
            await self.conn.execute("""
                INSERT OR REPLACE INTO auth_requests (
                    oauth_token, source_platform, source_user_id, sink_platform, token_data
                ) VALUES (?, ?, ?, ?, ?)
            """, (oauth_token, source_platform, source_user_id, sink_platform, token_data))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save request token: {e}")
            return False

    async def get_request_token(self, oauth_token: str) -> Optional[dict]:
        if not self.conn:
            return None
        cursor = await self.conn.execute(
            "SELECT * FROM auth_requests WHERE oauth_token = ?", (oauth_token,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "oauth_token": row[0],
            "source_platform": row[1],
            "source_user_id": row[2],
            "sink_platform": row[3],
            "token_data": row[4],
        }

    async def delete_request_token(self, oauth_token: str) -> bool:
        if not self.conn:
            return False
        await self.conn.execute(
            "DELETE FROM auth_requests WHERE oauth_token = ?", (oauth_token,)
        )
        await self.conn.commit()
        return True

    # ===== auth_tokens (永久 user token) 操作 =====

    async def save_user_token(
        self,
        source_platform: str,
        source_user_id: str,
        sink_platform: str,
        token_data: str,
    ) -> bool:
        if not self.conn:
            return False
        try:
            await self.conn.execute("""
                INSERT OR REPLACE INTO auth_tokens (
                    source_platform, source_user_id, sink_platform, token_data, updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (source_platform, source_user_id, sink_platform, token_data))
            await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save user token: {e}")
            return False

    async def get_user_token(
        self, source_platform: str, source_user_id: str, sink_platform: str
    ) -> Optional[str]:
        """获取用户 token_data JSON 字符串"""
        if not self.conn:
            return None
        cursor = await self.conn.execute("""
            SELECT token_data FROM auth_tokens
            WHERE source_platform = ? AND source_user_id = ? AND sink_platform = ?
        """, (source_platform, source_user_id, sink_platform))
        row = await cursor.fetchone()
        return row[0] if row else None

    async def delete_user_token(
        self, source_platform: str, source_user_id: str, sink_platform: str
    ) -> bool:
        if not self.conn:
            return False
        cursor = await self.conn.execute("""
            DELETE FROM auth_tokens
            WHERE source_platform = ? AND source_user_id = ? AND sink_platform = ?
        """, (source_platform, source_user_id, sink_platform))
        await self.conn.commit()
        return cursor.rowcount > 0

    # ===== 单例管理 =====

    @classmethod
    def get_instance(cls) -> Optional["DatabaseManager"]:
        return cls._instance

    @classmethod
    def create_instance(cls) -> "DatabaseManager":
        if cls._instance is not None:
            raise RuntimeError("DatabaseManager instance already exists")
        cls._instance = cls()
        bus.register(cls._instance.handle_message)
        logger.info("Database manager registered to event bus")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
