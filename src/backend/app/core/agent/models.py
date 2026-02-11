"""
智能体结构化输出模型（Pydantic）
用于 reasoning / observation 等节点的 LLM 输出解析，降低手写 JSON 解析错误率。
"""
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class ReasoningDecision(BaseModel):
    """推理节点输出：下一步行动与内容"""
    action: Literal["use_tool", "respond", "guide"] = "respond"
    tool_name: Optional[str] = Field(None, description="当 action=use_tool 时的工具名")
    tool_input: Optional[Dict[str, Any]] = Field(default_factory=dict, description="工具入参，如 {\"query\": \"...\"}")
    response: Optional[str] = Field(None, description="当 action 为 respond/guide 时给用户的回答")
    reasoning: Optional[str] = Field(None, description="推理过程说明")


class ObservationDecision(BaseModel):
    """观察节点输出：是否继续、分析、最终回答"""
    should_continue: bool = False
    next_action: Literal["use_tool", "respond"] = "respond"
    analysis: Optional[str] = Field(None, description="对本轮工具结果的分析摘要")
    response: Optional[str] = Field(None, description="当 should_continue=false 时的最终回答")
