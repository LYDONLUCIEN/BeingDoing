"""
数据模型模块
"""
from app.models.database import Base, engine, AsyncSessionLocal, get_db
from app.models.user import User, UserProfile, WorkHistory, ProjectExperience
from app.models.session import Session, Progress
from app.models.answer import Question, Answer
from app.models.selection import UserSelection, GuidePreference, ExplorationResult

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
]
