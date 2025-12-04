import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, Any
from loguru import logger


class MessageDB:
    def __init__(self, db_path: str = "messages.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT UNIQUE NOT NULL,
                        open_id TEXT NOT NULL,
                        message_type TEXT NOT NULL,
                        content TEXT,
                        image_data BLOB,
                        fanfou_status_id TEXT,
                        fanfou_response TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                logger.info("数据库表初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    def save_message(self, message_id: str, open_id: str, message_type: str, 
                    content: Optional[str] = None, image_data: Optional[bytes] = None) -> bool:
        """保存接收到的消息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO messages 
                    (message_id, open_id, message_type, content, image_data, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (message_id, open_id, message_type, content, image_data, datetime.now()))
                conn.commit()
                logger.info(f"消息 {message_id} 保存成功")
                return True
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
            return False
    
    def update_fanfou_response(self, message_id: str, fanfou_status_id: Optional[str] = None, 
                             fanfou_response: Optional[Dict[Any, Any]] = None) -> bool:
        """更新饭否发送结果"""
        try:
            response_json = json.dumps(fanfou_response, ensure_ascii=False) if fanfou_response else None
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE messages 
                    SET fanfou_status_id = ?, fanfou_response = ?, updated_at = ?
                    WHERE message_id = ?
                ''', (fanfou_status_id, response_json, datetime.now(), message_id))
                conn.commit()
                logger.info(f"饭否响应更新成功: {message_id}")
                return True
        except Exception as e:
            logger.error(f"更新饭否响应失败: {e}")
            return False
    
    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """获取单条消息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM messages WHERE message_id = ?', (message_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"获取消息失败: {e}")
            return None
    
    def get_messages_by_open_id(self, open_id: str, limit: int = 50) -> list:
        """获取用户的消息历史"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM messages 
                    WHERE open_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (open_id, limit))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取用户消息历史失败: {e}")
            return []
    
    def get_recent_messages(self, limit: int = 100) -> list:
        """获取最近的消息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM messages 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ''', (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"获取最近消息失败: {e}")
            return []


# 全局数据库实例
message_db = MessageDB()