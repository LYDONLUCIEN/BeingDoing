"""
用户相关数据模型
"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Text, ARRAY, Date
from sqlalchemy.dialects.postgresql import UUID, ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=True)
    phone = Column(String(20), unique=True, nullable=True)
    username = Column(String(100), nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    
    # 关系
    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    work_histories = relationship("WorkHistory", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    selections = relationship("UserSelection", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    """用户信息表"""
    __tablename__ = "user_profiles"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    gender = Column(String(20), nullable=True)  # male, female, other
    age = Column(Integer, nullable=True)
    profile_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="profile")


class WorkHistory(Base):
    """工作履历表"""
    __tablename__ = "work_history"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company = Column(String(255), nullable=True)
    position = Column(String(255), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)  # NULL表示当前工作
    evaluation = Column(Text, nullable=True)  # 工作评价和感受
    skills_used = Column(Text, nullable=True)  # SQLite不支持数组，存储为JSON字符串
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="work_histories")
    projects = relationship("ProjectExperience", back_populates="work_history", cascade="all, delete-orphan")


class ProjectExperience(Base):
    """项目经历表"""
    __tablename__ = "project_experiences"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    work_history_id = Column(String(36), ForeignKey("work_history.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    role = Column(String(255), nullable=True)
    achievements = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    work_history = relationship("WorkHistory", back_populates="projects")
