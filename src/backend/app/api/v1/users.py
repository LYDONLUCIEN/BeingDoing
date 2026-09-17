"""
用户信息API
"""
from fastapi import APIRouter, HTTPException, Depends, File, Response, UploadFile, status
from pydantic import BaseModel
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.models.database import get_db
from app.services import avatar_service
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["用户"])


class UserProfileRequest(BaseModel):
    """用户信息请求"""
    gender: Optional[str] = None
    age: Optional[int] = None


class WorkHistoryRequest(BaseModel):
    """工作履历请求"""
    company: Optional[str] = None
    position: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    evaluation: Optional[str] = None
    skills_used: Optional[List[str]] = None


class ProjectExperienceRequest(BaseModel):
    """项目经历请求"""
    name: str
    description: Optional[str] = None
    role: Optional[str] = None
    achievements: Optional[str] = None


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


class UpdateMeRequest(BaseModel):
    """更新当前用户基本信息请求"""
    username: Optional[str] = None


@router.post("/avatar", response_model=StandardResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传当前用户头像（OSS 覆盖写，返回永久有效的后端代理 URL）"""
    file_bytes = await file.read()
    try:
        avatar_url = await avatar_service.upload_avatar(
            db=db,
            user_id=current_user["user_id"],
            file_data=file_bytes,
            content_type=file.content_type or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    await db.commit()
    return StandardResponse(code=200, message="上传成功", data={"avatar_url": avatar_url})


@router.get("/{user_id}/avatar")
async def get_avatar(user_id: str):
    """
    头像代理转发（公开端点，无鉴权——CSS background 请求不带 Authorization 头）。
    图片本体在 OSS 私有桶，此处从 OSS 拉字节流转发，URL 永久有效。
    """
    try:
        data, content_type = await avatar_service.download_avatar(user_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    return Response(
        content=data,
        media_type=content_type,
        # avatar_url 带 ?v=<上传时间戳>，换头像即换 URL，可以安全长缓存
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.patch("/me", response_model=StandardResponse)
async def update_me(
    request: UpdateMeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户基本信息（目前仅昵称）"""
    username = (request.username or "").strip()
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="昵称不能为空"
        )
    if len(username) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="昵称最长 100 个字符"
        )

    from app.core.database import UserDB

    user_db = UserDB(db)
    user = await user_db.update_user(current_user["user_id"], username=username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    await db.commit()
    return StandardResponse(code=200, message="保存成功", data={"username": user.username})


@router.post("/profile", response_model=StandardResponse)
async def submit_profile(
    request: UserProfileRequest,
    current_user: dict = Depends(get_current_user)
):
    """提交用户基本信息"""
    try:
        result = await UserService.save_user_profile(
            user_id=current_user["user_id"],
            gender=request.gender,
            age=request.age
        )
        
        return StandardResponse(
            code=200,
            message="保存成功",
            data=result
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/profile", response_model=StandardResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """获取用户完整信息"""
    try:
        result = await UserService.get_user_profile(current_user["user_id"])
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户信息不存在"
            )
        
        return StandardResponse(
            code=200,
            message="success",
            data=result
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/work-history", response_model=StandardResponse)
async def submit_work_history(
    request: WorkHistoryRequest,
    current_user: dict = Depends(get_current_user)
):
    """提交工作履历"""
    try:
        result = await UserService.save_work_history(
            user_id=current_user["user_id"],
            company=request.company,
            position=request.position,
            start_date=request.start_date,
            end_date=request.end_date,
            evaluation=request.evaluation,
            skills_used=request.skills_used
        )
        
        return StandardResponse(
            code=200,
            message="保存成功",
            data=result
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/work-history/{work_history_id}/projects", response_model=StandardResponse)
async def submit_project_experience(
    work_history_id: str,
    request: ProjectExperienceRequest,
    current_user: dict = Depends(get_current_user)
):
    """提交项目经历"""
    try:
        result = await UserService.save_project_experience(
            work_history_id=work_history_id,
            name=request.name,
            description=request.description,
            role=request.role,
            achievements=request.achievements
        )
        
        return StandardResponse(
            code=200,
            message="保存成功",
            data=result
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/profile/complete", response_model=StandardResponse)
async def mark_profile_complete(current_user: dict = Depends(get_current_user)):
    """标记用户信息收集完成"""
    try:
        success = await UserService.mark_profile_completed(current_user["user_id"])
        
        return StandardResponse(
            code=200,
            message="标记成功",
            data={"success": success}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
