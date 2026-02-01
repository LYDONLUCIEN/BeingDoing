"""
进度管理服务
"""
from typing import Optional, Dict, List
from app.core.database import HistoryDB
from app.models.database import AsyncSessionLocal


class ProgressService:
    """进度管理服务"""
    
    @staticmethod
    async def get_progress(session_id: str, step: str) -> Optional[Dict]:
        """
        获取进度
        
        Args:
            session_id: 会话ID
            step: 探索步骤（values_exploration/strengths_exploration/interests_exploration）
        
        Returns:
            进度字典，如果不存在则返回None
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            progress = await history_db.get_progress(session_id, step)
            
            if not progress:
                return None
            
            # 计算进度百分比
            percentage = 0
            if progress.total_count > 0:
                percentage = int((progress.completed_count / progress.total_count) * 100)
            
            return {
                "id": progress.id,
                "session_id": progress.session_id,
                "step": progress.step,
                "completed_count": progress.completed_count,
                "total_count": progress.total_count,
                "percentage": percentage,
                "started_at": str(progress.started_at) if progress.started_at else None,
                "completed_at": str(progress.completed_at) if progress.completed_at else None
            }
    
    @staticmethod
    async def update_progress(
        session_id: str,
        step: str,
        completed_count: Optional[int] = None,
        total_count: Optional[int] = None
    ) -> Dict:
        """
        更新进度
        
        Args:
            session_id: 会话ID
            step: 探索步骤
            completed_count: 已完成数量
            total_count: 总数量
        
        Returns:
            更新后的进度字典
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            
            progress = await history_db.update_progress(
                session_id=session_id,
                step=step,
                completed_count=completed_count,
                total_count=total_count
            )
            
            # 计算进度百分比
            percentage = 0
            if progress.total_count > 0:
                percentage = int((progress.completed_count / progress.total_count) * 100)
            
            return {
                "id": progress.id,
                "session_id": progress.session_id,
                "step": progress.step,
                "completed_count": progress.completed_count,
                "total_count": progress.total_count,
                "percentage": percentage,
                "started_at": str(progress.started_at) if progress.started_at else None,
                "completed_at": str(progress.completed_at) if progress.completed_at else None
            }
    
    @staticmethod
    async def get_all_progresses(session_id: str) -> List[Dict]:
        """
        获取会话的所有进度
        
        Args:
            session_id: 会话ID
        
        Returns:
            进度列表
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            progresses = await history_db.get_session_progresses(session_id)
            
            result = []
            for progress in progresses:
                percentage = 0
                if progress.total_count > 0:
                    percentage = int((progress.completed_count / progress.total_count) * 100)
                
                result.append({
                    "id": progress.id,
                    "session_id": progress.session_id,
                    "step": progress.step,
                    "completed_count": progress.completed_count,
                    "total_count": progress.total_count,
                    "percentage": percentage,
                    "started_at": str(progress.started_at) if progress.started_at else None,
                    "completed_at": str(progress.completed_at) if progress.completed_at else None
                })
            
            return result
    
    @staticmethod
    def calculate_overall_progress(progresses: List[Dict]) -> Dict:
        """
        计算总体进度
        
        Args:
            progresses: 各步骤进度列表
        
        Returns:
            总体进度字典
        """
        if not progresses:
            return {
                "overall_percentage": 0,
                "total_steps": 0,
                "completed_steps": 0
            }
        
        total_steps = len(progresses)
        completed_steps = sum(1 for p in progresses if p.get("percentage", 0) == 100)
        overall_percentage = int((completed_steps / total_steps) * 100) if total_steps > 0 else 0
        
        return {
            "overall_percentage": overall_percentage,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "step_details": progresses
        }
