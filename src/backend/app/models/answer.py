"""
回答相关数据模型
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.models.database import Base


class Question(Base):
    """问题表（从question.md加载）"""
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)  # values, strengths, interests
    question_number = Column(Integer, nullable=False)  # 问题编号
    content = Column(Text, nullable=False)
    is_starred = Column(String(1), nullable=True)  # 带星号的问题
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    answers = relationship("Answer", back_populates="question")


class Answer(Base):
    """回答表"""
    __tablename__ = "answers"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    category = Column(String(50), nullable=False)  # values, strengths, interests
    content = Column(Text, nullable=False)
    # 注意：SQLAlchemy Declarative API 中属性名 `metadata` 是保留的，
    # 这里使用属性名 `extra_metadata`，但数据库列名仍然叫 `metadata`。
    extra_metadata = Column("metadata", Text, nullable=True)  # JSON字符串，存储语音文件、编辑历史等
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    session = relationship("Session", back_populates="answers")
    question = relationship("Question", back_populates="answers")
