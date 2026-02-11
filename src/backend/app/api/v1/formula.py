"""
公式和流程API：流程步骤与公式文案从 domain 读取，单点维护。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.api.v1.auth import get_current_user
from app.domain import FLOW_STEPS, DEFAULT_CURRENT_STEP

router = APIRouter(prefix="/formula", tags=["公式"])


class StandardResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


@router.get("", response_model=StandardResponse)
async def get_formula(current_user: Optional[dict] = Depends(get_current_user)):
    """获取公式（公式文案仍在此处，步骤对应关系与 domain 一致）"""
    formula_data = {
        "formula": "喜欢的事 × 擅长的事 × 重要的事 = 真正想做的事",
        "elements": {
            "喜欢的事": {
                "name": "喜欢的事",
                "description": "你的兴趣和热情所在",
                "exploration_step": "interests_exploration"
            },
            "擅长的事": {
                "name": "擅长的事",
                "description": "你的才能和优势",
                "exploration_step": "strengths_exploration"
            },
            "重要的事": {
                "name": "重要的事",
                "description": "你的价值观和认为重要的事",
                "exploration_step": "values_exploration"
            },
            "真正想做的事": {
                "name": "真正想做的事",
                "description": "三个要素的交集，是你真正应该追求的方向"
            }
        },
        "explanation": "这个公式帮助你找到真正想做的事。只有当三个要素都有交集时，我们才能找到真正适合自己的方向。"
    }
    return StandardResponse(code=200, message="success", data=formula_data)


@router.get("/flowchart", response_model=StandardResponse)
async def get_flowchart(current_user: Optional[dict] = Depends(get_current_user)):
    """获取流程图（步骤列表与默认步从 domain 读取）"""
    flowchart_data = {
        "steps": FLOW_STEPS,
        "current_step": DEFAULT_CURRENT_STEP,
    }
    return StandardResponse(code=200, message="success", data=flowchart_data)
