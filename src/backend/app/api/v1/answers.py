"""
回答API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from typing import Optional, List, Dict
from app.api.v1.auth import get_current_user
from app.services.answer_service import AnswerService

router = APIRouter(prefix="/answers", tags=["回答"])


class SubmitAnswerRequest(BaseModel):
    """提交回答请求"""
    session_id: str
    category: str  # values, strengths, interests
    content: str
    question_id: Optional[int] = None
    metadata: Optional[Dict] = None


class UpdateAnswerRequest(BaseModel):
    """更新回答请求"""
    content: Optional[str] = None
    metadata: Optional[Dict] = None


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.post("", response_model=StandardResponse)
async def submit_answer(
    request: SubmitAnswerRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """提交回答"""
    try:
        # 验证回答
        validation = AnswerService.validate_answer(request.content)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation["error_message"]
            )
        
        result = await AnswerService.save_answer(
            session_id=request.session_id,
            category=request.category,
            content=request.content,
            question_id=request.question_id,
            metadata=request.metadata
        )
        
        return StandardResponse(
            code=200,
            message="提交成功",
            data=result
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.patch("/{answer_id}", response_model=StandardResponse)
async def update_answer(
    answer_id: str,
    request: UpdateAnswerRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """更新回答"""
    try:
        if request.content:
            validation = AnswerService.validate_answer(request.content)
            if not validation["is_valid"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=validation["error_message"]
                )
        
        result = await AnswerService.update_answer(
            answer_id=answer_id,
            content=request.content,
            metadata=request.metadata
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回答不存在"
            )
        
        return StandardResponse(
            code=200,
            message="更新成功",
            data=result
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("", response_model=StandardResponse)
async def get_answers(
    session_id: str = Query(..., description="会话ID"),
    category: Optional[str] = Query(None, description="问题分类"),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取回答列表"""
    try:
        answers = await AnswerService.get_session_answers(session_id, category)
        
        return StandardResponse(
            code=200,
            message="success",
            data={"answers": answers, "count": len(answers)}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{answer_id}", response_model=StandardResponse)
async def get_answer(
    answer_id: str,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取单个回答"""
    try:
        answer = await AnswerService.get_answer(answer_id)
        
        if not answer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="回答不存在"
            )
        
        return StandardResponse(
            code=200,
            message="success",
            data=answer
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
