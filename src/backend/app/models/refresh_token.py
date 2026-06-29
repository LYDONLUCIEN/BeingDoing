"""
Refresh Token 持久化模型
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String

from app.models.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    jti = Column(String(64), nullable=False, unique=True, index=True)
    family_id = Column(String(64), nullable=False, index=True)

    is_revoked = Column(Boolean, nullable=False, default=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String(64), nullable=True)
    replaced_by_jti = Column(String(64), nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
