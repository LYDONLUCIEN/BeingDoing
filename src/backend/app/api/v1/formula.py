"""
公式和流程API
"""
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from app.api.v1.auth import get_current_user

router = APIRouter(prefix="/formula", tags=["公式"])


class StandardResponse(BaseModel):
    """标准响应"""
    code: int = 200
    message: str = "success"
    data: dict


@router.get("", response_model=StandardResponse)
async def get_formula(current_user: Optional[dict] = Depends(get_current_user)):
    """获取公式"""
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
        "explanation": "这个公式帮助你找到真正想做的事。只有当三个要素都有交集时，你才能找到真正适合自己的方向。"
    }
    
    return StandardResponse(
        code=200,
        message="success",
        data=formula_data
    )


@router.get("/flowchart", response_model=StandardResponse)
async def get_flowchart(current_user: Optional[dict] = Depends(get_current_user)):
    """获取流程图"""
    flowchart_data = {
        "steps": [
            {
                "id": "values_exploration",
                "name": "探索重要的事（价值观）",
                "description": "了解你认为重要的事",
                "order": 1
            },
            {
                "id": "strengths_exploration",
                "name": "探索擅长的事（才能）",
                "description": "了解你的优势和才能",
                "order": 2
            },
            {
                "id": "interests_exploration",
                "name": "探索喜欢的事（热情）",
                "description": "了解你的兴趣和热情",
                "order": 3
            },
            {
                "id": "combination",
                "name": "组合分析",
                "description": "将三个要素进行组合分析",
                "order": 4
            },
            {
                "id": "refinement",
                "name": "精炼结果",
                "description": "精炼和验证最终结果",
                "order": 5
            }
        ],
        "current_step": "values_exploration"
    }
    
    return StandardResponse(
        code=200,
        message="success",
        data=flowchart_data
    )
