"""
会话和进度相关数据模型
"""
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.database import Base


class Session(Base):
    """会话表"""
    __tablename__ = "sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    device_id = Column(String(255), nullable=True)  # 设备指纹
    current_step = Column(String(50), nullable=True)  # values_exploration, strengths_exploration, interests_exploration, combination, refinement
    status = Column(String(20), default="active")  # active, paused, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="sessions")
    progress_records = relationship("Progress", back_populates="session", cascade="all, delete-orphan")
    answers = relationship("Answer", back_populates="session", cascade="all, delete-orphan")
    selections = relationship("UserSelection", back_populates="session", cascade="all, delete-orphan")
    guide_preference = relationship("GuidePreference", back_populates="session", uselist=False, cascade="all, delete-orphan")
    exploration_result = relationship("ExplorationResult", back_populates="session", uselist=False, cascade="all, delete-orphan")


class Progress(Base):
    """进度表"""
    __tablename__ = "progress"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    step = Column(String(50), nullable=False)  # values_exploration, strengths_exploration, interests_exploration
    completed_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    session = relationship("Session", back_populates="progress_records")
