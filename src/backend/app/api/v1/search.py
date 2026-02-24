"""
内容检索API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from typing import Optional
from app.api.v1.auth import get_current_user
from app.services.search_service import SearchService

router = APIRouter(prefix="/search", tags=["检索"])


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str
    category: Optional[str] = None  # values, interests, strengths, questions
    limit: int = 10


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.post("", response_model=StandardResponse)
async def search(
    request: SearchRequest,
    current_user: Optional[dict] = Depends(get_current_user)
):
    """搜索内容（知识源配置从 domain 注入）"""
    try:
        result = SearchService().search(
            query=request.query,
            category=request.category,
            limit=request.limit,
        )
        return StandardResponse(code=200, message="success", data=result)
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/similar", response_model=StandardResponse)
async def get_similar_examples(
    query: str = Query(..., description="查询文本"),
    category: str = Query(..., description="分类（values/interests/strengths）"),
    limit: int = Query(5, description="返回数量限制"),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """获取相似示例（知识源配置从 domain 注入）"""
    try:
        examples = SearchService().get_similar_examples(category=category, query=query, limit=limit)
        return StandardResponse(
            code=200,
            message="success",
            data={"query": query, "category": category, "examples": examples, "count": len(examples)}
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
