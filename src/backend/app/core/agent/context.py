"""
上下文管理模块
"""
from typing import Dict, Any, Optional, List
from app.core.agent.state import AgentState
from app.core.database import UserDB, HistoryDB
from app.models.database import AsyncSessionLocal
from app.utils.conversation_file_manager import ConversationFileManager, ConversationCategory
from app.core.llmapi import LLMMessage


class ContextManager:
    """上下文管理器"""
    
    def __init__(self, session_id: str, user_id: Optional[str] = None):
        """
        初始化上下文管理器
        
        Args:
            session_id: 会话ID
            user_id: 用户ID（可选）
        """
        self.session_id = session_id
        self.user_id = user_id
        self.conversation_manager = ConversationFileManager()
    
    async def get_user_info(self) -> Dict[str, Any]:
        """
        获取用户信息
        
        Returns:
            用户信息字典
        """
        if not self.user_id:
            return {}
        
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            user = await user_db.get_user_by_id(self.user_id)
            if not user:
                return {}
            
            profile = await user_db.get_user_profile(self.user_id)
            
            return {
                "user_id": user.id,
                "email": user.email,
                "username": user.username,
                "gender": profile.gender if profile else None,
                "age": profile.age if profile else None,
                "profile_completed": profile.profile_completed if profile else False
            }
    
    async def get_work_history(self) -> List[Dict[str, Any]]:
        """
        获取工作履历
        
        Returns:
            工作履历列表
        """
        if not self.user_id:
            return []
        
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            work_histories = await user_db.get_user_work_histories(self.user_id)
            
            result = []
            for wh in work_histories:
                projects = await user_db.get_work_history_projects(wh.id)
                result.append({
                    "company": wh.company,
                    "position": wh.position,
                    "start_date": str(wh.start_date) if wh.start_date else None,
                    "end_date": str(wh.end_date) if wh.end_date else None,
                    "evaluation": wh.evaluation,
                    "projects": [
                        {
                            "name": p.name,
                            "description": p.description,
                            "role": p.role,
                            "achievements": p.achievements
                        }
                        for p in projects
                    ]
                })
            
            return result
    
    async def get_answered_questions(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取已回答的问题
        
        Args:
            category: 问题分类（可选）
        
        Returns:
            已回答问题列表
        """
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            answers = await history_db.get_session_answers(self.session_id, category)
            
            return [
                {
                    "question_id": a.question_id,
                    "category": a.category,
                    "content": a.content,
                    "created_at": str(a.created_at)
                }
                for a in answers
            ]
    
    async def get_conversation_history(
        self,
        category: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取对话历史
        
        Args:
            category: 对话分类（可选）
            limit: 限制数量（可选）
        
        Returns:
            对话历史列表
        """
        if category:
            messages = await self.conversation_manager.get_messages(
                self.session_id,
                category=category
            )
        else:
            all_conversations = await self.conversation_manager.get_all_conversations(self.session_id)
            messages = []
            for cat_messages in all_conversations.values():
                messages.extend(cat_messages)
        
        # 限制数量
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    async def build_context(self, current_step: str) -> Dict[str, Any]:
        """
        构建完整上下文（当前：直接拼接）
        
        Args:
            current_step: 当前步骤
        
        Returns:
            上下文字典
        """
        context = {
            "current_step": current_step,
            "user_info": await self.get_user_info(),
            "work_history": await self.get_work_history(),
            "answered_questions": await self.get_answered_questions(),
            "conversation_history": await self.get_conversation_history(limit=10)
        }
        
        return context
    
    async def build_messages_for_llm(
        self,
        user_input: str,
        current_step: str
    ) -> List[LLMMessage]:
        """
        构建LLM消息列表（当前：直接拼接）
        
        Args:
            user_input: 用户输入
            current_step: 当前步骤
        
        Returns:
            LLM消息列表
        """
        context = await self.build_context(current_step)
        
        # 构建系统提示词
        system_content = f"""你是一个专业的职业规划助手。你的任务是帮助用户探索他们的价值观、才能和兴趣。

当前探索步骤：{current_step}

用户信息：
- 性别：{context['user_info'].get('gender', '未知')}
- 年龄：{context['user_info'].get('age', '未知')}
- 是否完成信息收集：{context['user_info'].get('profile_completed', False)}

工作履历：{len(context['work_history'])}段经历
已回答问题：{len(context['answered_questions'])}个

请根据用户输入提供有针对性的帮助。
"""
        
        messages = [LLMMessage(role="system", content=system_content)]
        
        # 添加对话历史（最近10条）
        for msg in context["conversation_history"][-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"]:
                messages.append(LLMMessage(role=role, content=content))
        
        # 添加当前用户输入
        messages.append(LLMMessage(role="user", content=user_input))
        
        return messages
