"""
示例推荐工具
"""
from typing import Dict, Any
from app.core.agent.tools.base import BaseAgentTool
from app.core.agent.state import AgentState
from app.core.knowledge import KnowledgeSearcher


class ExampleTool(BaseAgentTool):
    """示例推荐工具：根据用户输入推荐相似示例"""
    
    def __init__(self):
        super().__init__(
            name="example_tool",
            description="根据用户输入推荐相似的价值观、兴趣或才能示例"
        )
        self.searcher = KnowledgeSearcher()
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        state: AgentState
    ) -> Dict[str, Any]:
        """
        执行示例推荐
        
        Args:
            input_data: 包含query和category
            state: 当前状态
        
        Returns:
            推荐示例列表
        """
        query = input_data.get("query", "")
        category = input_data.get("category", None)
        
        if not query:
            return {
                "success": False,
                "error": "查询内容不能为空"
            }
        
        # 获取相似示例
        if category:
            examples = self.searcher.get_similar_examples(category, query, limit=5)
        else:
            # 如果没有指定分类，搜索所有分类
            examples = []
            for cat in ["values", "interests", "strengths"]:
                cat_examples = self.searcher.get_similar_examples(cat, query, limit=3)
                examples.extend(cat_examples)
            examples.sort(key=lambda x: x.get("score", 0), reverse=True)
            examples = examples[:5]
        
        return {
            "success": True,
            "query": query,
            "category": category,
            "examples": [
                {
                    "name": e["item"].name,
                    "score": e["score"],
                    "type": category or "mixed"
                }
                for e in examples
            ],
            "count": len(examples)
        }
    
    def _get_parameters(self) -> Dict[str, Any]:
        """获取参数定义"""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "查询文本"
                },
                "category": {
                    "type": "string",
                    "enum": ["values", "interests", "strengths"],
                    "description": "示例类别，可选"
                }
            },
            "required": ["query"]
        }
