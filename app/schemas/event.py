"""
Unified Message Event Schema
统一消息事件模型 - 用于在系统内部流转的标准化消息格式
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageSource(str, Enum):
    """
    消息来源枚举
    定义所有支持的消息输入源平台
    """
    TELEGRAM = "telegram"
    FEISHU = "feishu"
    SYSTEM = "system"  # 系统内部消息


class UnifiedMessage(BaseModel):
    """
    统一消息模型
    
    这是系统内部流转的标准化消息格式，所有平台的消息都会被转换为此格式。
    通过异步消息总线在生产者和消费者之间传递。
    
    设计原则：
    - 平台无关：字段设计不依赖任何特定平台的数据结构
    - 可扩展：通过 raw_data 保留原始数据，支持未来扩展
    - 可追溯：包含 event_id 和 timestamp 用于调试和日志
    """
    
    event_id: UUID = Field(
        default_factory=uuid4,
        description="事件唯一标识符，自动生成"
    )
    
    source: MessageSource = Field(
        ...,
        description="消息来源平台"
    )
    
    content: str = Field(
        ...,
        description="消息文本内容"
    )
    
    sender_id: str = Field(
        ...,
        description="发送者 ID（平台相关格式）"
    )
    
    sender_name: Optional[str] = Field(
        default=None,
        description="发送者名称（可选）"
    )
    
    chat_id: Optional[str] = Field(
        default=None,
        description="会话 ID（可选，用于群聊等场景）"
    )
    
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="原始平台数据，保留完整上下文信息"
    )
    
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="消息创建时间戳"
    )
    
    class Config:
        """Pydantic 配置"""
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }
        use_enum_values = True
    
    def __str__(self) -> str:
        """字符串表示，便于日志输出"""
        return (
            f"UnifiedMessage(id={self.event_id}, "
            f"source={self.source}, "
            f"sender={self.sender_id}, "
            f"content={self.content[:50]}...)"
        )
