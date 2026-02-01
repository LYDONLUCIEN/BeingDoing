"""
用户选择相关数据模型
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.database import Base


class UserSelection(Base):
    """用户选择表"""
    __tablename__ = "user_selections"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(20), nullable=False)  # values, strengths, interests
    selected_items = Column(Text, nullable=False)  # JSON字符串，存储选中的项目列表
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="selections")
    session = relationship("Session", back_populates="selections")


class GuidePreference(Base):
    """引导偏好表"""
    __tablename__ = "guide_preferences"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    preference = Column(String(20), default="normal")  # normal, quiet
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    session = relationship("Session", back_populates="guide_preference")


class ExplorationResult(Base):
    """探索结果表"""
    __tablename__ = "exploration_results"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), unique=True, nullable=False)
    values_selected = Column(Text, nullable=True)  # JSON字符串数组
    strengths_selected = Column(Text, nullable=True)  # JSON字符串数组
    interests_selected = Column(Text, nullable=True)  # JSON字符串数组
    wanted_thing = Column(Text, nullable=True)  # 想做的事
    true_wanted_thing = Column(Text, nullable=True)  # 真正想做的事
    summary = Column(Text, nullable=True)  # JSON字符串，完整摘要
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    session = relationship("Session", back_populates="exploration_result")
