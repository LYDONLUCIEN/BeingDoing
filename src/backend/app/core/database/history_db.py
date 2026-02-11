"""
历史数据操作（会话、进度、回答）
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional, List
from app.models.session import Session, Progress
from app.models.answer import Answer, Question


class HistoryDB:
    """历史数据操作类"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # 会话操作
    async def create_session(
        self,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        current_step: Optional[str] = None,
        status: str = "active"
    ) -> Session:
        """创建会话"""
        session = Session(
            user_id=user_id,
            device_id=device_id,
            current_step=current_step,
            status=status
        )
        self.session.add(session)
        await self.session.commit()
        await self.session.refresh(session)
        return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        result = await self.session.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()
    
    async def update_session(
        self,
        session_id: str,
        current_step: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[Session]:
        """更新会话"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        if current_step is not None:
            session.current_step = current_step
        if status is not None:
            session.status = status
        
        await self.session.commit()
        await self.session.refresh(session)
        return session
    
    async def get_user_sessions(self, user_id: str) -> List[Session]:
        """获取用户的所有会话"""
        result = await self.session.execute(
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_session(self, session_id: str) -> bool:
        """删除会话（级联删除进度、回答等）"""
        session = await self.get_session(session_id)
        if not session:
            return False
        await self.session.delete(session)
        await self.session.commit()
        return True

    # 进度操作
    async def create_progress(
        self,
        session_id: str,
        step: str,
        total_count: int = 0
    ) -> Progress:
        """创建进度记录"""
        from datetime import datetime
        progress = Progress(
            session_id=session_id,
            step=step,
            total_count=total_count,
            started_at=datetime.utcnow()
        )
        self.session.add(progress)
        await self.session.commit()
        await self.session.refresh(progress)
        return progress
    
    async def get_progress(self, session_id: str, step: str) -> Optional[Progress]:
        """获取进度记录"""
        result = await self.session.execute(
            select(Progress)
            .where(Progress.session_id == session_id)
            .where(Progress.step == step)
        )
        return result.scalar_one_or_none()
    
    async def update_progress(
        self,
        session_id: str,
        step: str,
        completed_count: Optional[int] = None,
        total_count: Optional[int] = None
    ) -> Optional[Progress]:
        """更新进度"""
        progress = await self.get_progress(session_id, step)
        if not progress:
            return await self.create_progress(session_id, step, total_count or 0)
        
        if completed_count is not None:
            progress.completed_count = completed_count
        if total_count is not None:
            progress.total_count = total_count
        
        # 如果完成
        if progress.completed_count >= progress.total_count and progress.total_count > 0:
            from datetime import datetime
            progress.completed_at = datetime.utcnow()
        
        await self.session.commit()
        await self.session.refresh(progress)
        return progress
    
    async def get_session_progresses(self, session_id: str) -> List[Progress]:
        """获取会话的所有进度记录"""
        result = await self.session.execute(
            select(Progress)
            .where(Progress.session_id == session_id)
        )
        return list(result.scalars().all())
    
    # 回答操作
    async def create_answer(
        self,
        session_id: str,
        category: str,
        content: str,
        question_id: Optional[int] = None,
        metadata: Optional[str] = None
    ) -> Answer:
        """创建回答"""
        answer = Answer(
            session_id=session_id,
            question_id=question_id,
            category=category,
            content=content,
            metadata=metadata
        )
        self.session.add(answer)
        await self.session.commit()
        await self.session.refresh(answer)
        return answer
    
    async def get_answer(self, answer_id: str) -> Optional[Answer]:
        """获取回答"""
        result = await self.session.execute(
            select(Answer).where(Answer.id == answer_id)
        )
        return result.scalar_one_or_none()
    
    async def get_session_answers(
        self,
        session_id: str,
        category: Optional[str] = None
    ) -> List[Answer]:
        """获取会话的回答列表"""
        query = select(Answer).where(Answer.session_id == session_id)
        if category:
            query = query.where(Answer.category == category)
        query = query.order_by(Answer.created_at)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_answer(
        self,
        answer_id: str,
        content: Optional[str] = None,
        metadata: Optional[str] = None
    ) -> Optional[Answer]:
        """更新回答"""
        answer = await self.get_answer(answer_id)
        if not answer:
            return None
        
        if content is not None:
            answer.content = content
        if metadata is not None:
            answer.extra_metadata = metadata
        
        await self.session.commit()
        await self.session.refresh(answer)
        return answer
