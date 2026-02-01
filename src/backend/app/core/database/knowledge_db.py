"""
知识数据操作（问题等）
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List
from app.models.answer import Question


class KnowledgeDB:
    """知识数据操作类"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_question(
        self,
        category: str,
        question_number: int,
        content: str,
        is_starred: Optional[str] = None
    ) -> Question:
        """创建问题"""
        question = Question(
            category=category,
            question_number=question_number,
            content=content,
            is_starred=is_starred
        )
        self.session.add(question)
        await self.session.commit()
        await self.session.refresh(question)
        return question
    
    async def get_question(self, question_id: int) -> Optional[Question]:
        """获取问题"""
        result = await self.session.execute(
            select(Question).where(Question.id == question_id)
        )
        return result.scalar_one_or_none()
    
    async def get_questions_by_category(
        self,
        category: str
    ) -> List[Question]:
        """根据分类获取问题列表"""
        result = await self.session.execute(
            select(Question)
            .where(Question.category == category)
            .order_by(Question.question_number)
        )
        return list(result.scalars().all())
    
    async def get_starred_questions(self, category: str) -> List[Question]:
        """获取带星号的问题"""
        result = await self.session.execute(
            select(Question)
            .where(Question.category == category)
            .where(Question.is_starred.isnot(None))
            .order_by(Question.question_number)
        )
        return list(result.scalars().all())
    
    async def get_all_questions(self) -> List[Question]:
        """获取所有问题"""
        result = await self.session.execute(
            select(Question).order_by(Question.category, Question.question_number)
        )
        return list(result.scalars().all())
