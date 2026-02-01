"""
引导工具
"""
from typing import Dict, Any
from app.core.agent.tools.base import BaseAgentTool
from app.core.agent.state import AgentState
from app.core.knowledge import KnowledgeLoader


class GuideTool(BaseAgentTool):
    """引导工具：获取引导问题"""
    
    def __init__(self):
        super().__init__(
            name="guide_tool",
            description="获取当前步骤的引导问题，帮助用户继续探索"
        )
        self.loader = KnowledgeLoader()
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        state: AgentState
    ) -> Dict[str, Any]:
        """
        执行引导
        
        Args:
            input_data: 包含step（当前步骤）
            state: 当前状态
        
        Returns:
            引导问题列表
        """
        step = input_data.get("step") or state.get("current_step", "values_exploration")
        
        # 映射步骤到分类
        step_to_category = {
            "values_exploration": "values",
            "strengths_exploration": "strengths",
            "interests_exploration": "interests"
        }
        
        category = step_to_category.get(step, "values")
        
        # 获取问题
        questions = self.loader.load_questions()
        category_questions = [q for q in questions if q.category == category]
        
        # 优先返回带星号的问题
        starred_questions = [q for q in category_questions if q.is_starred]
        if starred_questions:
            guide_questions = starred_questions[:5]
        else:
            guide_questions = category_questions[:5]
        
        return {
            "success": True,
            "step": step,
            "category": category,
            "questions": [
                {
                    "id": q.id,
                    "content": q.content,
                    "is_starred": q.is_starred
                }
                for q in guide_questions
            ],
            "count": len(guide_questions)
        }
    
    def _get_parameters(self) -> Dict[str, Any]:
        """获取参数定义"""
        return {
            "type": "object",
            "properties": {
                "step": {
                    "type": "string",
                    "enum": ["values_exploration", "strengths_exploration", "interests_exploration"],
                    "description": "当前探索步骤"
                }
            }
        }
