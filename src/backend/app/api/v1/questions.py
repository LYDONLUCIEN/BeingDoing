"""
问题API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from typing import Optional, List
from app.api.v1.auth import get_current_user
from app.services.question_service import QuestionService

router = APIRouter(prefix="/questions", tags=["问题"])


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.get("", response_model=StandardResponse)
async def get_questions(
    category: Optional[str] = Query(None, description="问题分类（values/strengths/interests）"),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取问题列表"""
    try:
        service = QuestionService()
        
        if category:
            questions = service.get_questions_by_category(category)
        else:
            questions = service.get_all_questions()
        
        return StandardResponse(
            code=200,
            message="success",
            data={"questions": questions, "count": len(questions)}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{question_id}", response_model=StandardResponse)
async def get_question(
    question_id: int,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取单个问题"""
    try:
        service = QuestionService()
        question = service.get_question_by_id(question_id)
        
        if not question:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="问题不存在"
            )
        
        return StandardResponse(
            code=200,
            message="success",
            data=question
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/guide-questions/list", response_model=StandardResponse)
async def get_guide_questions(
    current_step: str = Query(..., description="当前步骤"),
    limit: int = Query(5, description="返回数量限制"),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取默认引导问题"""
    try:
        service = QuestionService()
        questions = service.get_guide_questions(current_step, limit)
        
        return StandardResponse(
            code=200,
            message="success",
            data={"questions": questions, "count": len(questions)}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/starred/list", response_model=StandardResponse)
async def get_starred_questions(
    category: str = Query(..., description="问题分类"),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取带星号的问题（用于工作目的）"""
    try:
        service = QuestionService()
        questions = service.get_starred_questions(category)
        
        return StandardResponse(
            code=200,
            message="success",
            data={"questions": questions, "count": len(questions)}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
