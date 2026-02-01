"""
用户信息收集服务
"""
from typing import Optional, Dict, List
from datetime import date
from app.core.database import UserDB
from app.models.database import AsyncSessionLocal


class UserService:
    """用户信息收集服务"""
    
    @staticmethod
    async def save_user_profile(
        user_id: str,
        gender: Optional[str] = None,
        age: Optional[int] = None
    ) -> Dict:
        """
        保存用户基本信息
        
        Args:
            user_id: 用户ID
            gender: 性别
            age: 年龄
        
        Returns:
            用户信息字典
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            
            profile = await user_db.update_user_profile(
                user_id=user_id,
                gender=gender,
                age=age
            )
            
            return {
                "user_id": profile.user_id,
                "gender": profile.gender,
                "age": profile.age,
                "profile_completed": profile.profile_completed
            }
    
    @staticmethod
    async def save_work_history(
        user_id: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        evaluation: Optional[str] = None,
        skills_used: Optional[List[str]] = None
    ) -> Dict:
        """
        保存工作履历
        
        Args:
            user_id: 用户ID
            company: 公司名称
            position: 职位
            start_date: 开始日期（YYYY-MM-DD格式）
            end_date: 结束日期（YYYY-MM-DD格式，None表示当前工作）
            evaluation: 工作评价
            skills_used: 使用的技能列表
        
        Returns:
            工作履历字典
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            
            # 转换日期字符串为date对象
            start_date_obj = None
            end_date_obj = None
            if start_date:
                start_date_obj = date.fromisoformat(start_date)
            if end_date:
                end_date_obj = date.fromisoformat(end_date)
            
            work_history = await user_db.create_work_history(
                user_id=user_id,
                company=company,
                position=position,
                start_date=start_date_obj,
                end_date=end_date_obj,
                evaluation=evaluation,
                skills_used=skills_used
            )
            
            return {
                "id": work_history.id,
                "user_id": work_history.user_id,
                "company": work_history.company,
                "position": work_history.position,
                "start_date": str(work_history.start_date) if work_history.start_date else None,
                "end_date": str(work_history.end_date) if work_history.end_date else None,
                "evaluation": work_history.evaluation
            }
    
    @staticmethod
    async def save_project_experience(
        work_history_id: str,
        name: str,
        description: Optional[str] = None,
        role: Optional[str] = None,
        achievements: Optional[str] = None
    ) -> Dict:
        """
        保存项目经历
        
        Args:
            work_history_id: 工作履历ID
            name: 项目名称
            description: 项目描述
            role: 担任角色
            achievements: 成就描述
        
        Returns:
            项目经历字典
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            
            project = await user_db.create_project_experience(
                work_history_id=work_history_id,
                name=name,
                description=description,
                role=role,
                achievements=achievements
            )
            
            return {
                "id": project.id,
                "work_history_id": project.work_history_id,
                "name": project.name,
                "description": project.description,
                "role": project.role,
                "achievements": project.achievements
            }
    
    @staticmethod
    async def get_user_profile(user_id: str) -> Optional[Dict]:
        """
        获取用户完整信息（包括工作履历和项目经历）
        
        Args:
            user_id: 用户ID
        
        Returns:
            用户完整信息字典
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            
            user = await user_db.get_user_by_id(user_id)
            if not user:
                return None
            
            profile = await user_db.get_user_profile(user_id)
            work_histories = await user_db.get_user_work_histories(user_id)
            
            # 构建工作履历列表（包含项目经历）
            work_history_list = []
            for wh in work_histories:
                projects = await user_db.get_work_history_projects(wh.id)
                work_history_list.append({
                    "id": wh.id,
                    "company": wh.company,
                    "position": wh.position,
                    "start_date": str(wh.start_date) if wh.start_date else None,
                    "end_date": str(wh.end_date) if wh.end_date else None,
                    "evaluation": wh.evaluation,
                    "projects": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "description": p.description,
                            "role": p.role,
                            "achievements": p.achievements
                        }
                        for p in projects
                    ]
                })
            
            return {
                "user_id": user.id,
                "email": user.email,
                "phone": user.phone,
                "username": user.username,
                "gender": profile.gender if profile else None,
                "age": profile.age if profile else None,
                "profile_completed": profile.profile_completed if profile else False,
                "work_histories": work_history_list
            }
    
    @staticmethod
    async def mark_profile_completed(user_id: str) -> bool:
        """
        标记用户信息收集完成
        
        Args:
            user_id: 用户ID
        
        Returns:
            是否成功
        """
        async with AsyncSessionLocal() as db:
            user_db = UserDB(db)
            
            profile = await user_db.update_user_profile(
                user_id=user_id,
                profile_completed=True
            )
            
            return profile is not None
