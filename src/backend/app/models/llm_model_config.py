"""
LLM 模型配置表（admin 可配置）。

- LlmModelConfig: 一条 = 一个可用的模型端点（provider/model/base_url/api_key 等）
- UserLlmModelConfig: 用户 → 模型 绑定（未绑定则走默认）
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)

from app.models.database import Base


def _new_id() -> str:
    return uuid.uuid4().hex


class LlmModelConfig(Base):
    """管理员配置的 LLM 模型条目。"""

    __tablename__ = "llm_model_configs"

    id = Column(String(32), primary_key=True, default=_new_id)
    name = Column(String(120), nullable=False)  # 管理员可读的标签
    provider = Column(String(32), nullable=False)  # openai|deepseek|kimi|qwen
    model = Column(String(128), nullable=False)
    base_url = Column(String(255), nullable=True)
    # Fernet 密文（url-safe base64）。绝不存明文。
    api_key_enc = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UserLlmModelConfig(Base):
    """用户 → 模型 绑定（每个 user 至多一行；不绑则回退 default）。"""

    __tablename__ = "user_llm_model_configs"

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_id = Column(
        String(32),
        ForeignKey("llm_model_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_llm_config_user"),
    )
