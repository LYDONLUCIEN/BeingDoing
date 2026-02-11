"""
内容检索API
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel
from typing import Optional
from app.api.v1.auth import get_current_user
from app.core.knowledge import KnowledgeLoader, KnowledgeSearcher
from app.domain.knowledge_config import get_knowledge_config

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
        loader = KnowledgeLoader(config=get_knowledge_config())
        searcher = KnowledgeSearcher(loader=loader)
        
        results = []
        
        if request.category == "values" or request.category is None:
            values = searcher.search_values(request.query, limit=request.limit)
            results.extend([{
                "type": "value",
                "name": r["item"].name,
                "definition": r["item"].definition,
                "score": r["score"]
            } for r in values])
        
        if request.category == "interests" or request.category is None:
            interests = searcher.search_interests(request.query, limit=request.limit)
            results.extend([{
                "type": "interest",
                "name": r["item"].name,
                "score": r["score"]
            } for r in interests])
        
        if request.category == "strengths" or request.category is None:
            strengths = searcher.search_strengths(request.query, limit=request.limit)
            results.extend([{
                "type": "strength",
                "name": r["item"].name,
                "strengths": r["item"].strengths,
                "weaknesses": r["item"].weaknesses,
                "score": r["score"]
            } for r in strengths])
        
        # 按分数排序
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return StandardResponse(
            code=200,
            message="success",
            data={
                "query": request.query,
                "category": request.category,
                "results": results[:request.limit],
                "count": len(results)
            }
        )
    
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
        loader = KnowledgeLoader(config=get_knowledge_config())
        searcher = KnowledgeSearcher(loader=loader)
        examples = searcher.get_similar_examples(category, query, limit)
        
        return StandardResponse(
            code=200,
            message="success",
            data={
                "query": query,
                "category": category,
                "examples": [
                    {
                        "name": e["item"].name,
                        "score": e["score"]
                    }
                    for e in examples
                ],
                "count": len(examples)
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
