"""
内容检索工具
"""
from typing import Dict, Any
from app.core.agent.tools.base import BaseAgentTool
from app.core.agent.state import AgentState
from app.core.knowledge import KnowledgeSearcher


class SearchTool(BaseAgentTool):
    """内容检索工具"""
    
    def __init__(self):
        super().__init__(
            name="search_tool",
            description="在知识库中搜索相关内容（价值观、兴趣、才能、问题）"
        )
        self.searcher = KnowledgeSearcher()
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        state: AgentState
    ) -> Dict[str, Any]:
        """
        执行搜索
        
        Args:
            input_data: 包含query和category
            state: 当前状态
        
        Returns:
            搜索结果
        """
        query = input_data.get("query", "")
        category = input_data.get("category", None)  # values, interests, strengths, questions
        
        if not query:
            return {
                "success": False,
                "error": "查询内容不能为空"
            }
        
        results = []
        
        if category == "values" or category is None:
            values = self.searcher.search_values(query, limit=5)
            results.extend([{
                "type": "value",
                "name": r["item"].name,
                "definition": r["item"].definition,
                "score": r["score"]
            } for r in values])
        
        if category == "interests" or category is None:
            interests = self.searcher.search_interests(query, limit=5)
            results.extend([{
                "type": "interest",
                "name": r["item"].name,
                "score": r["score"]
            } for r in interests])
        
        if category == "strengths" or category is None:
            strengths = self.searcher.search_strengths(query, limit=5)
            results.extend([{
                "type": "strength",
                "name": r["item"].name,
                "strengths": r["item"].strengths,
                "weaknesses": r["item"].weaknesses,
                "score": r["score"]
            } for r in strengths])
        
        # 按分数排序
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return {
            "success": True,
            "query": query,
            "category": category,
            "results": results[:10],  # 限制返回10个
            "count": len(results)
        }
    
    def _get_parameters(self) -> Dict[str, Any]:
        """获取参数定义"""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询文本"
                },
                "category": {
                    "type": "string",
                    "enum": ["values", "interests", "strengths", "questions"],
                    "description": "搜索类别，可选"
                }
            },
            "required": ["query"]
        }
