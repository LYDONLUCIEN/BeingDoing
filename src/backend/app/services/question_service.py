"""
问题服务（知识源配置从 domain 注入）
"""
from typing import List, Dict, Optional
from app.core.knowledge import KnowledgeLoader
from app.domain.knowledge_config import get_knowledge_config


class QuestionService:
    """问题服务"""
    
    def __init__(self):
        """初始化问题服务"""
        self.loader = KnowledgeLoader(config=get_knowledge_config())
    
    def get_questions_by_category(self, category: str) -> List[Dict]:
        """
        根据分类获取问题列表
        
        Args:
            category: 问题分类（values/strengths/interests）
        
        Returns:
            问题列表
        """
        questions = self.loader.load_questions()
        category_questions = [q for q in questions if q.category == category]
        
        return [
            {
                "id": q.id,
                "category": q.category,
                "question_number": q.question_number,
                "content": q.content,
                "is_starred": q.is_starred
            }
            for q in category_questions
        ]
    
    def get_question_by_id(self, question_id: int) -> Optional[Dict]:
        """
        根据ID获取问题
        
        Args:
            question_id: 问题ID
        
        Returns:
            问题字典，如果不存在则返回None
        """
        questions = self.loader.load_questions()
        for q in questions:
            if q.id == question_id:
                return {
                    "id": q.id,
                    "category": q.category,
                    "question_number": q.question_number,
                    "content": q.content,
                    "is_starred": q.is_starred
                }
        return None
    
    def get_starred_questions(self, category: str) -> List[Dict]:
        """
        获取带星号的问题（用于工作目的）
        
        Args:
            category: 问题分类
        
        Returns:
            带星号的问题列表
        """
        questions = self.loader.load_questions()
        starred = [q for q in questions if q.category == category and q.is_starred]
        
        return [
            {
                "id": q.id,
                "category": q.category,
                "question_number": q.question_number,
                "content": q.content,
                "is_starred": q.is_starred
            }
            for q in starred
        ]
    
    def get_guide_questions(
        self,
        current_step: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        获取默认引导问题
        
        Args:
            current_step: 当前步骤（values_exploration/strengths_exploration/interests_exploration）
            limit: 返回数量限制
        
        Returns:
            引导问题列表
        """
        from app.domain import STEP_TO_CATEGORY
        category = STEP_TO_CATEGORY.get(current_step, "values")
        
        # 优先返回带星号的问题
        starred = self.get_starred_questions(category)
        if starred:
            return starred[:limit]
        
        # 如果没有带星号的问题，返回前几个问题
        questions = self.get_questions_by_category(category)
        return questions[:limit]
    
    def get_all_questions(self) -> List[Dict]:
        """
        获取所有问题
        
        Returns:
            所有问题列表
        """
        questions = self.loader.load_questions()
        
        return [
            {
                "id": q.id,
                "category": q.category,
                "question_number": q.question_number,
                "content": q.content,
                "is_starred": q.is_starred
            }
            for q in questions
        ]
