"""
引导服务
"""
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from app.core.database import HistoryDB
from app.core.database.init_db import get_db
from app.models.selection import GuidePreference
from app.models.database import AsyncSessionLocal
from app.config.guide_config import GuideConfig
from app.services.question_service import QuestionService
from sqlalchemy import select


class GuideService:
    """引导服务"""
    
    def __init__(self):
        """初始化引导服务"""
        self.question_service = QuestionService()
        self.guide_config = GuideConfig()
    
    async def should_trigger_active_guide(
        self,
        session_id: str,
        last_activity_at: Optional[datetime] = None
    ) -> bool:
        """
        判断是否应该触发主动引导
        
        Args:
            session_id: 会话ID
            last_activity_at: 最后活动时间
        
        Returns:
            是否应该触发
        """
        # 获取引导偏好
        preference = await self.get_guide_preference(session_id)
        preference_mode = preference.get("preference", "normal")
        
        # 获取超时时间
        if preference_mode == "quiet":
            timeout = self.guide_config.get_quiet_timeout()
        else:
            timeout = self.guide_config.get_idle_timeout()
        
        # 如果没有提供最后活动时间，从数据库获取
        if last_activity_at is None:
            async with AsyncSessionLocal() as db:
                history_db = HistoryDB(db)
                session = await history_db.get_session(session_id)
                if session:
                    last_activity_at = session.last_activity_at
        
        if last_activity_at is None:
            return False
        
        # 计算时间差
        time_diff = datetime.utcnow() - last_activity_at
        
        return time_diff.total_seconds() >= timeout
    
    async def should_trigger_passive_guide(
        self,
        answer_content: str,
        current_step: str
    ) -> bool:
        """
        判断是否应该触发被动引导
        
        Args:
            answer_content: 回答内容
            current_step: 当前步骤
        
        Returns:
            是否应该触发
        """
        # 检查回答是否过短
        short_threshold = self.guide_config.get_short_answer_threshold()
        if len(answer_content.strip()) < short_threshold:
            return True
        
        # 可以添加其他判断逻辑（如回答是否模糊等）
        
        return False
    
    async def get_guide_preference(self, session_id: str) -> Dict:
        """
        获取引导偏好
        
        Args:
            session_id: 会话ID
        
        Returns:
            引导偏好字典
        """
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GuidePreference).where(GuidePreference.session_id == session_id)
            )
            preference = result.scalar_one_or_none()
            
            if preference:
                return {
                    "session_id": preference.session_id,
                    "preference": preference.preference,
                    "created_at": str(preference.created_at)
                }
            else:
                # 默认偏好
                return {
                    "session_id": session_id,
                    "preference": "normal",
                    "created_at": None
                }
    
    async def set_guide_preference(
        self,
        session_id: str,
        preference: str
    ) -> Dict:
        """
        设置引导偏好
        
        Args:
            session_id: 会话ID
            preference: 偏好（normal/quiet）
        
        Returns:
            更新后的偏好字典
        """
        if preference not in ["normal", "quiet"]:
            raise ValueError("偏好必须是normal或quiet")
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(GuidePreference).where(GuidePreference.session_id == session_id)
            )
            guide_pref = result.scalar_one_or_none()
            
            if guide_pref:
                guide_pref.preference = preference
                guide_pref.updated_at = datetime.utcnow()
            else:
                guide_pref = GuidePreference(
                    session_id=session_id,
                    preference=preference
                )
                db.add(guide_pref)
            
            await db.commit()
            await db.refresh(guide_pref)
            
            return {
                "session_id": guide_pref.session_id,
                "preference": guide_pref.preference,
                "created_at": str(guide_pref.created_at)
            }
    
    async def generate_guide_questions(
        self,
        current_step: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        生成默认引导问题
        
        Args:
            current_step: 当前步骤
            limit: 返回数量限制
        
        Returns:
            引导问题列表
        """
        return self.question_service.get_guide_questions(current_step, limit)
    
    async def generate_active_guide_message(
        self,
        session_id: str,
        current_step: str
    ) -> str:
        """
        生成主动引导消息
        
        Args:
            session_id: 会话ID
            current_step: 当前步骤
        
        Returns:
            引导消息
        """
        # 获取引导问题
        guide_questions = await self.generate_guide_questions(current_step, limit=3)
        
        if guide_questions:
            questions_text = "\n".join([
                f"{i+1}. {q['content']}"
                for i, q in enumerate(guide_questions)
            ])
            
            return f"""看起来你已经有一段时间没有继续探索了。让我来帮你继续：

当前步骤：{current_step}

你可以尝试回答以下问题：
{questions_text}

或者告诉我你在思考什么，我可以为你提供帮助。"""
        else:
            return "看起来你已经有一段时间没有继续探索了。有什么我可以帮助你的吗？"
