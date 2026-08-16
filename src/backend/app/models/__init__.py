"""
数据模型模块
"""
from app.models.database import Base, engine, AsyncSessionLocal, get_db
from app.models.user import User, UserProfile, WorkHistory, ProjectExperience
from app.models.session import Session, Progress
from app.models.answer import Question, Answer
from app.models.selection import UserSelection, GuidePreference, ExplorationResult
from app.models.analytics import AnalyticsChatTurn, AnalyticsReport, AnalyticsLike
from app.models.llm_usage import LlmUsageLog
from app.models.refresh_token import RefreshToken
from app.models.notification import NotificationTask, NotificationRecipient
from app.models.email_bounce import EmailBounce
from app.models.site_notice import SiteNotice
from app.models.rumination_ab import RuminationAbAssignment
from app.models.llm_model_config import LlmModelConfig, UserLlmModelConfig
from app.models.feedback import Feedback, FeedbackAttachment, Notification
from app.models.payment import (
    PaymentOrder,
    Coupon,
    Subscription,
    ConsultationBooking,
    TeamAnalysis,
)

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "User",
    "UserProfile",
    "WorkHistory",
    "ProjectExperience",
    "Session",
    "Progress",
    "Question",
    "Answer",
    "UserSelection",
    "GuidePreference",
    "ExplorationResult",
    "AnalyticsChatTurn",
    "AnalyticsReport",
    "AnalyticsLike",
    "LlmUsageLog",
    "RefreshToken",
    "NotificationTask",
    "NotificationRecipient",
    "EmailBounce",
    "SiteNotice",
    "RuminationAbAssignment",
    "LlmModelConfig",
    "UserLlmModelConfig",
    # 反馈与站内信
    "Feedback",
    "FeedbackAttachment",
    "Notification",
    # 支付与会员
    "PaymentOrder",
    "Coupon",
    "Subscription",
    "ConsultationBooking",
    "TeamAnalysis",
]
