"""
引导工具（步骤与分类、知识源配置从 domain 读取）
"""
from typing import Dict, Any
from app.core.agent.tools.base import BaseAgentTool
from app.core.agent.state import AgentState
from app.core.knowledge import KnowledgeLoader
from app.domain import STEP_TO_CATEGORY, EXPLORATION_STEP_IDS, DEFAULT_CURRENT_STEP
from app.domain.knowledge_config import get_knowledge_config


class GuideTool(BaseAgentTool):
    """引导工具：获取引导问题"""
    
    def __init__(self):
        super().__init__(
            name="guide_tool",
            description="获取当前步骤的引导问题，帮助用户继续探索"
        )
        self.loader = KnowledgeLoader(config=get_knowledge_config())
    
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
        step = input_data.get("step") or state.get("current_step", DEFAULT_CURRENT_STEP)
        category = STEP_TO_CATEGORY.get(step, "values")
        
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
                    "enum": EXPLORATION_STEP_IDS,
                    "description": "当前探索步骤"
                }
            }
        }
