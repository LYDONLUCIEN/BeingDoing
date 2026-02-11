"""
会话管理API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from typing import Optional
from app.api.v1.auth import get_current_user
from app.core.database import HistoryDB
from app.models.database import AsyncSessionLocal
from app.domain import DEFAULT_CURRENT_STEP

router = APIRouter(prefix="/sessions", tags=["会话"])


class CreateSessionRequest(BaseModel):
    """创建会话请求（current_step 默认从 domain 读取）"""
    device_id: Optional[str] = None
    current_step: Optional[str] = DEFAULT_CURRENT_STEP


class UpdateSessionRequest(BaseModel):
    """更新会话请求"""
    current_step: Optional[str] = None
    status: Optional[str] = None


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.post("", response_model=StandardResponse)
async def create_session(
    request: CreateSessionRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """创建会话"""
    try:
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            
            user_id = current_user["user_id"] if current_user else None
            session = await history_db.create_session(
                user_id=user_id,
                device_id=request.device_id,
                current_step=request.current_step,
                status="active"
            )
            
            return StandardResponse(
                code=200,
                message="创建成功",
                data={
                    "session_id": session.id,
                    "user_id": session.user_id,
                    "current_step": session.current_step,
                    "status": session.status,
                    "created_at": str(session.created_at)
                }
            )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=StandardResponse)
async def list_sessions(
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取当前用户的会话列表（按最近活动排序）"""
    try:
        if not current_user:
            return StandardResponse(code=200, message="success", data={"sessions": []})
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            sessions = await history_db.get_user_sessions(current_user["user_id"])
            return StandardResponse(
                code=200,
                message="success",
                data={
                    "sessions": [
                        {
                            "session_id": s.id,
                            "user_id": s.user_id,
                            "current_step": s.current_step,
                            "status": s.status,
                            "created_at": str(s.created_at),
                            "updated_at": str(s.updated_at),
                            "last_activity_at": str(s.last_activity_at),
                        }
                        for s in sessions
                    ]
                },
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/{session_id}", response_model=StandardResponse)
async def delete_session(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """删除会话（含对话文件）"""
    try:
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            session = await history_db.get_session(session_id)
            if not session:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
            if current_user and session.user_id != current_user["user_id"]:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权删除此会话")
            await history_db.delete_session(session_id)
        from app.utils.conversation_file_manager import ConversationFileManager
        conv = ConversationFileManager()
        await conv.delete_session(session_id)
        return StandardResponse(code=200, message="删除成功", data={})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{session_id}", response_model=StandardResponse)
async def get_session(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取会话信息"""
    try:
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            session = await history_db.get_session(session_id)
            
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="会话不存在"
                )
            
            # 检查权限（如果是登录用户，只能访问自己的会话）
            if current_user and session.user_id != current_user["user_id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无权访问此会话"
                )
            
            return StandardResponse(
                code=200,
                message="success",
                data={
                    "session_id": session.id,
                    "user_id": session.user_id,
                    "current_step": session.current_step,
                    "status": session.status,
                    "created_at": str(session.created_at),
                    "updated_at": str(session.updated_at),
                    "last_activity_at": str(session.last_activity_at)
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.patch("/{session_id}/progress", response_model=StandardResponse)
async def update_progress(
    session_id: str,
    step: str = Query(...),
    completed_count: Optional[int] = Query(None),
    total_count: Optional[int] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """更新会话进度"""
    try:
        async with AsyncSessionLocal() as db:
            history_db = HistoryDB(db)
            
            # 验证会话存在
            session = await history_db.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="会话不存在"
                )
            
            # 检查权限
            if current_user and session.user_id != current_user["user_id"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="无权访问此会话"
                )
            
            progress = await history_db.update_progress(
                session_id=session_id,
                step=step,
                completed_count=completed_count,
                total_count=total_count
            )
            
            percentage = 0
            if progress.total_count > 0:
                percentage = int((progress.completed_count / progress.total_count) * 100)
            
            return StandardResponse(
                code=200,
                message="更新成功",
                data={
                    "session_id": progress.session_id,
                    "step": progress.step,
                    "completed_count": progress.completed_count,
                    "total_count": progress.total_count,
                    "percentage": percentage
                }
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
