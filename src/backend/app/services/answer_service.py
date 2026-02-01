"""
回答服务
"""
from typing import Optional, Dict, List
from app.core.database import HistoryDB
from app.models.database import AsyncSessionLocal


class AnswerService:
    """回答服务"""
    
    @staticmethod
    async def save_answer(
        session_id: str,
        category: str,
        content: str,
        question_id: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        保存回答
        
        Args:
            session_id: 会话ID
            category: 问题分类（values/strengths/interests）
            content: 回答内容
            question_id: 问题ID（可选）
            metadata: 元数据（可选，如语音文件路径等）
        
        Returns:
            回答字典
        """
        import json
        
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            
            metadata_str = json.dumps(metadata) if metadata else None
            
            answer = await history_db.create_answer(
                session_id=session_id,
                category=category,
                content=content,
                question_id=question_id,
                metadata=metadata_str
            )
            
            return {
                "id": answer.id,
                "session_id": answer.session_id,
                "question_id": answer.question_id,
                "category": answer.category,
                "content": answer.content,
                "created_at": str(answer.created_at)
            }
    
    @staticmethod
    async def update_answer(
        answer_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        更新回答
        
        Args:
            answer_id: 回答ID
            content: 新的回答内容
            metadata: 新的元数据
        
        Returns:
            更新后的回答字典，如果不存在则返回None
        """
        import json
        
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            
            metadata_str = json.dumps(metadata) if metadata else None
            
            answer = await history_db.update_answer(
                answer_id=answer_id,
                content=content,
                metadata=metadata_str
            )
            
            if not answer:
                return None
            
            return {
                "id": answer.id,
                "session_id": answer.session_id,
                "question_id": answer.question_id,
                "category": answer.category,
                "content": answer.content,
                "updated_at": str(answer.updated_at)
            }
    
    @staticmethod
    async def get_answer(answer_id: str) -> Optional[Dict]:
        """
        获取回答
        
        Args:
            answer_id: 回答ID
        
        Returns:
            回答字典，如果不存在则返回None
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            answer = await history_db.get_answer(answer_id)
            
            if not answer:
                return None
            
            import json
            metadata = None
            if answer.metadata:
                try:
                    metadata = json.loads(answer.metadata)
                except:
                    pass
            
            return {
                "id": answer.id,
                "session_id": answer.session_id,
                "question_id": answer.question_id,
                "category": answer.category,
                "content": answer.content,
                "metadata": metadata,
                "created_at": str(answer.created_at),
                "updated_at": str(answer.updated_at)
            }
    
    @staticmethod
    async def get_session_answers(
        session_id: str,
        category: Optional[str] = None
    ) -> List[Dict]:
        """
        获取会话的回答列表
        
        Args:
            session_id: 会话ID
            category: 问题分类（可选）
        
        Returns:
            回答列表
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            answers = await history_db.get_session_answers(session_id, category)
            
            import json
            result = []
            for answer in answers:
                metadata = None
                if answer.metadata:
                    try:
                        metadata = json.loads(answer.metadata)
                    except:
                        pass
                
                result.append({
                    "id": answer.id,
                    "session_id": answer.session_id,
                    "question_id": answer.question_id,
                    "category": answer.category,
                    "content": answer.content,
                    "metadata": metadata,
                    "created_at": str(answer.created_at),
                    "updated_at": str(answer.updated_at)
                })
            
            return result
    
    @staticmethod
    def validate_answer(content: str, min_length: int = 10) -> Dict[str, any]:
        """
        验证回答
        
        Args:
            content: 回答内容
            min_length: 最小长度
        
        Returns:
            验证结果（包含is_valid和error_message）
        """
        if not content or not content.strip():
            return {
                "is_valid": False,
                "error_message": "回答内容不能为空"
            }
        
        if len(content.strip()) < min_length:
            return {
                "is_valid": False,
                "error_message": f"回答内容至少需要{min_length}个字符"
            }
        
        return {
            "is_valid": True,
            "error_message": None
        }
