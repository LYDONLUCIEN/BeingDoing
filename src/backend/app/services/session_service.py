"""
会话管理服务
会话 CRUD、更新会话状态。删除会话时同时清理对话文件。
"""
from typing import Optional, List, Dict
from app.core.database import HistoryDB
from app.models.database import AsyncSessionLocal


def _session_to_dict(session) -> Dict:
    """将 Session 模型转为字典"""
    return {
        "session_id": session.id,
        "user_id": session.user_id,
        "current_step": session.current_step,
        "status": session.status,
        "created_at": str(session.created_at),
        "updated_at": str(session.updated_at),
        "last_activity_at": str(session.last_activity_at),
    }


class SessionService:
    """会话管理服务"""

    @staticmethod
    async def create_session(
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        current_step: Optional[str] = None,
        status: str = "active",
    ) -> Dict:
        """
        创建会话

        Args:
            user_id: 用户ID，匿名时None
            device_id: 设备ID（可选）
            current_step: 当前步骤
            status: 状态

        Returns:
            会话字典
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            session = await history_db.create_session(
                user_id=user_id,
                device_id=device_id,
                current_step=current_step,
                status=status,
            )
            return _session_to_dict(session)

    @staticmethod
    async def get_session(session_id: str) -> Optional[Dict]:
        """
        获取会话

        Args:
            session_id: 会话ID

        Returns:
            会话字典，不存在则 None
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            session = await history_db.get_session(session_id)
            if not session:
                return None
            return _session_to_dict(session)

    @staticmethod
    async def list_user_sessions(user_id: str) -> List[Dict]:
        """
        获取用户会话列表（按最近活动排序）

        Args:
            user_id: 用户ID

        Returns:
            会话字典列表
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            sessions = await history_db.get_user_sessions(user_id)
            return [_session_to_dict(s) for s in sessions]

    @staticmethod
    async def update_session(
        session_id: str,
        current_step: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        更新会话

        Args:
            session_id: 会话ID
            current_step: 当前步骤（可选）
            status: 状态（可选）

        Returns:
            更新后的会话字典，不存在则 None
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            session = await history_db.update_session(
                session_id=session_id,
                current_step=current_step,
                status=status,
            )
            if not session:
                return None
            return _session_to_dict(session)

    @staticmethod
    async def delete_session(session_id: str) -> bool:
        """
        删除会话（含数据库记录与对话文件）

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        from app.utils.conversation_file_manager import ConversationFileManager

        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            session = await history_db.get_session(session_id)
            if not session:
                return False
            await history_db.delete_session(session_id)

        conv = ConversationFileManager()
        await conv.delete_session(session_id)
        return True
