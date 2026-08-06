"""
数据分析与埋点模型
用于 Admin 统计：用户数、访问、对话轮次、token、报告、点赞等
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text

from app.models.database import Base


class AnalyticsChatTurn(Base):
    """每次对话轮次埋点：维度、用户输入字数、LLM token"""

    __tablename__ = "analytics_chat_turns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(128), nullable=False, index=True)  # chat 或 simple-chat 的 session
    dimension = Column(
        String(50), nullable=True
    )  # values_exploration, strengths_exploration, interests_exploration, combination, refinement, 或 simple 的 values/strengths/interests
    user_input_chars = Column(Integer, default=0)
    llm_input_tokens = Column(Integer, default=0)
    llm_output_tokens = Column(Integer, default=0)
    log_index = Column(Integer, nullable=True)  # 对应 runs.jsonl 的行号或对话索引，用于关联点赞详情
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AnalyticsReport(Base):
    """报告生成埋点"""

    __tablename__ = "analytics_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(128), nullable=False, index=True)
    activation_code = Column(String(64), nullable=True)  # simple 模式
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AnalyticsEvent(Base):
    """通用事件埋点（ADR-0013）：页面浏览 PV / 登录活跃 auth_active

    - page_view：前端埋点上报，不依赖登录；visitor_id 为匿名访客 cookie（兼算 UV）
    - auth_active：仅服务端内部写（登录成功 + token 刷新成功），不开放外部上报
    - 统计口径：事件时间口径，按 Asia/Shanghai 日历日分桶（见 analytics_funnel_service）
    """

    __tablename__ = "analytics_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(32), nullable=False, index=True)  # page_view / auth_active
    user_id = Column(String(36), nullable=True, index=True)  # 登录用户；PV 未登录为空
    visitor_id = Column(String(64), nullable=True, index=True)  # 匿名访客 cookie
    path = Column(String(255), nullable=True)  # page_view 路径
    meta = Column(Text, nullable=True)  # JSON：referrer / ua 摘要等
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AnalyticsLike(Base):
    """用户点赞：支持按 message_id + user_id 去重，快照留存原文"""

    __tablename__ = "analytics_likes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=True, index=True)  # 点赞用户 ID（未登录可为空）
    session_id = Column(String(128), nullable=False, index=True)
    thread_id = Column(
        String(128), nullable=True, index=True
    )  # 对话线程 ID（simple-chat 多线程场景）
    message_id = Column(
        String(128), nullable=False, index=True
    )  # 消息唯一标识（前端 ThreadMessage.id）
    role = Column(String(20), nullable=True)  # 消息角色：assistant / user
    log_index = Column(Integer, nullable=True)  # 保留兼容：原始 runs.jsonl 索引
    content_preview = Column(Text, nullable=True)  # 内容摘要（前端截断传入，用于快速浏览）
    content_snapshot = Column(Text, nullable=True)  # 完整原文快照（点赞时留存，删除兜底用）
    dimension = Column(String(50), nullable=True)  # 探索维度
    phase = Column(
        String(50), nullable=True
    )  # 阶段 key：values / strengths / interests / purpose / rumination
    activation_code = Column(String(64), nullable=True, index=True)  # simple 模式激活码
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
