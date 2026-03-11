"""
数据分析与埋点模型
用于 Admin 统计：用户数、访问、对话轮次、token、报告、点赞等
"""
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Text, BigInteger
from datetime import datetime
import uuid
from app.models.database import Base


class AnalyticsChatTurn(Base):
    """每次对话轮次埋点：维度、用户输入字数、LLM token"""
    __tablename__ = "analytics_chat_turns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(128), nullable=False, index=True)  # chat 或 simple-chat 的 session
    dimension = Column(String(50), nullable=True)  # values_exploration, strengths_exploration, interests_exploration, combination, refinement, 或 simple 的 values/strengths/interests
    user_input_chars = Column(Integer, default=0)
    llm_input_tokens = Column(Integer, default=0)
    llm_output_tokens = Column(Integer, default=0)
    log_index = Column(Integer, nullable=True)  # 对应 runs.jsonl 的行号或对话索引，用于关联点赞详情
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalyticsReport(Base):
    """报告生成埋点"""
    __tablename__ = "analytics_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(128), nullable=False, index=True)
    activation_code = Column(String(64), nullable=True)  # simple 模式
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalyticsLike(Base):
    """用户点赞埋点：关联原始记录索引，可点击查看详情"""
    __tablename__ = "analytics_likes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(128), nullable=False, index=True)
    log_index = Column(Integer, nullable=False)  # 原始 runs.jsonl 中的索引
    content_preview = Column(Text, nullable=True)  # 被点赞内容摘要，便于快速浏览
    dimension = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
