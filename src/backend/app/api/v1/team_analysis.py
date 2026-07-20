"""
团队分析 API（用户侧，P-E，ADR-0008/0010）

接口（全部 get_current_user 登录鉴权，统一响应 {code, message, data}）：
- GET  /team-analysis/candidates      候选报告列表（自己码的 + 购买交付且已授权的）
- POST /team-analysis                 创建分析（后台 LLM 生成）
- GET  /team-analysis                 我的分析列表
- GET  /team-analysis/{id}            分析详情（含结果 markdown）

异常映射：ValueError → 400；AnalysisNotFoundError → 404。
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.v1.auth import get_current_user
from app.services.team_analysis_service import AnalysisNotFoundError, TeamAnalysisService

router = APIRouter(prefix="/team-analysis", tags=["TeamAnalysis"])


def _ok(data: Any) -> Dict[str, Any]:
    return {"code": 200, "message": "success", "data": data}


class AnalysisCreateRequest(BaseModel):
    """创建团队分析"""

    code_list: List[str] = Field(..., min_length=2, max_length=10, description="参与分析的激活码")
    title: Optional[str] = Field(None, description="分析标题（可选）")


@router.get("/candidates")
async def list_candidates(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """候选报告列表"""
    return _ok({"items": TeamAnalysisService.list_candidates(str(current_user["user_id"]))})


@router.post("")
async def create_analysis(
    payload: AnalysisCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """创建团队分析（异步 LLM 生成，前端轮询详情）"""
    try:
        analysis = await TeamAnalysisService.create_analysis(
            user_id=str(current_user["user_id"]),
            code_list=payload.code_list,
            title=payload.title,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    background_tasks.add_task(TeamAnalysisService.run_generation, analysis.id)
    return _ok({"analysis": TeamAnalysisService._to_dict(analysis, with_result=False)})


@router.get("")
async def list_analyses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """我的团队分析列表"""
    items, total = await TeamAnalysisService.list_my_analyses(
        user_id=str(current_user["user_id"]), page=page, page_size=page_size
    )
    return _ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """分析详情（含结果正文；generating 时前端轮询）"""
    try:
        analysis = await TeamAnalysisService.get_my_analysis(
            user_id=str(current_user["user_id"]), analysis_id=analysis_id
        )
    except AnalysisNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _ok({"analysis": analysis})
