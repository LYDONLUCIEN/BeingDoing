"""
用户数据操作
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional, List
from app.models.user import User, UserProfile, WorkHistory, ProjectExperience


class UserDB:
    """用户数据操作类"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_user(
        self,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        username: Optional[str] = None,
        password_hash: str = ""
    ) -> User:
        """创建用户"""
        user = User(
            email=email,
            phone=phone,
            username=username,
            password_hash=password_hash
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据ID获取用户"""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            return None
        result = await self.session.execute(
            select(User).where(func.lower(func.trim(User.email)) == normalized_email)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_phone(self, phone: str) -> Optional[User]:
        """根据手机号获取用户"""
        result = await self.session.execute(
            select(User).where(User.phone == phone)
        )
        return result.scalar_one_or_none()
    
    async def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        """更新用户信息"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None
        
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        await self.session.commit()
        await self.session.refresh(user)
        return user
    
    async def create_user_profile(
        self,
        user_id: str,
        gender: Optional[str] = None,
        age: Optional[int] = None
    ) -> UserProfile:
        """创建用户信息"""
        profile = UserProfile(
            user_id=user_id,
            gender=gender,
            age=age
        )
        self.session.add(profile)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户信息"""
        result = await self.session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def update_user_profile(
        self,
        user_id: str,
        gender: Optional[str] = None,
        age: Optional[int] = None,
        profile_completed: Optional[bool] = None
    ) -> Optional[UserProfile]:
        """更新用户信息"""
        profile = await self.get_user_profile(user_id)
        if not profile:
            profile = await self.create_user_profile(user_id, gender, age)

        if gender is not None:
            profile.gender = gender
        if age is not None:
            profile.age = age
        if profile_completed is not None:
            profile.profile_completed = profile_completed

        await self.session.commit()
        await self.session.refresh(profile)
        return profile
    
    async def create_work_history(
        self,
        user_id: str,
        company: Optional[str] = None,
        position: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        evaluation: Optional[str] = None,
        skills_used: Optional[List[str]] = None
    ) -> WorkHistory:
        """创建工作履历"""
        import json
        work_history = WorkHistory(
            user_id=user_id,
            company=company,
            position=position,
            start_date=start_date,
            end_date=end_date,
            evaluation=evaluation,
            skills_used=json.dumps(skills_used) if skills_used else None
        )
        self.session.add(work_history)
        await self.session.commit()
        await self.session.refresh(work_history)
        return work_history
    
    async def get_user_work_histories(self, user_id: str) -> List[WorkHistory]:
        """获取用户工作履历列表"""
        result = await self.session.execute(
            select(WorkHistory)
            .where(WorkHistory.user_id == user_id)
            .order_by(WorkHistory.start_date.desc())
        )
        return list(result.scalars().all())
    
    async def create_project_experience(
        self,
        work_history_id: str,
        name: str,
        description: Optional[str] = None,
        role: Optional[str] = None,
        achievements: Optional[str] = None
    ) -> ProjectExperience:
        """创建项目经历"""
        project = ProjectExperience(
            work_history_id=work_history_id,
            name=name,
            description=description,
            role=role,
            achievements=achievements
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project
    
    async def get_work_history_projects(self, work_history_id: str) -> List[ProjectExperience]:
        """获取工作履历的项目列表"""
        result = await self.session.execute(
            select(ProjectExperience)
            .where(ProjectExperience.work_history_id == work_history_id)
        )
        return list(result.scalars().all())

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        profile_completed: Optional[bool] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
    ) -> tuple[List[User], int]:
        """
        分页查询用户列表（含 profile 子查询）。
        返回 (users, total_count)
        """
        from datetime import datetime as dt
        base = select(User).options(selectinload(User.profile))
        count_q = select(func.count()).select_from(User)

        if search:
            pattern = f"%{search}%"
            cond = User.email.ilike(pattern) | User.username.ilike(pattern)
            base = base.where(cond)
            count_q = count_q.where(cond)
        if is_active is not None:
            base = base.where(User.is_active == is_active)
            count_q = count_q.where(User.is_active == is_active)
        if profile_completed is not None:
            base = base.join(UserProfile, UserProfile.user_id == User.id).where(
                UserProfile.profile_completed == profile_completed
            )
            count_q = count_q.join(UserProfile, UserProfile.user_id == User.id).where(
                UserProfile.profile_completed == profile_completed
            )
        if created_after:
            try:
                dt_after = dt.fromisoformat(created_after)
                base = base.where(User.created_at >= dt_after)
                count_q = count_q.where(User.created_at >= dt_after)
            except ValueError:
                pass
        if created_before:
            try:
                dt_before = dt.fromisoformat(created_before)
                base = base.where(User.created_at <= dt_before)
                count_q = count_q.where(User.created_at <= dt_before)
            except ValueError:
                pass

        total = (await self.session.execute(count_q)).scalar() or 0

        base = base.order_by(User.created_at.desc())
        offset = (page - 1) * page_size
        base = base.offset(offset).limit(page_size)
        result = await self.session.execute(base)
        users = list(result.scalars().all())
        return users, total
