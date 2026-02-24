"""
知识检索服务
包装 KnowledgeLoader + KnowledgeSearcher，供 API 层统一调用。
"""
from typing import Optional, List, Dict
from app.core.knowledge import KnowledgeLoader, KnowledgeSearcher
from app.domain.knowledge_config import get_knowledge_config


class SearchService:
    """知识检索服务"""

    def __init__(self):
        loader = KnowledgeLoader(config=get_knowledge_config())
        self._searcher = KnowledgeSearcher(loader=loader)

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> Dict:
        """
        检索知识库（价值观、兴趣、才能）

        Args:
            query: 查询文本
            category: values | interests | strengths | None（全部）
            limit: 返回数量限制

        Returns:
            {"query", "category", "results": [...], "count": N}
        """
        results = []
        if category == "values" or category is None:
            values = self._searcher.search_values(query, limit=limit)
            results.extend([
                {"type": "value", "name": r["item"].name, "definition": r["item"].definition, "score": r["score"]}
                for r in values
            ])
        if category == "interests" or category is None:
            interests = self._searcher.search_interests(query, limit=limit)
            results.extend([
                {"type": "interest", "name": r["item"].name, "score": r["score"]}
                for r in interests
            ])
        if category == "strengths" or category is None:
            strengths = self._searcher.search_strengths(query, limit=limit)
            results.extend([
                {
                    "type": "strength",
                    "name": r["item"].name,
                    "strengths": r["item"].strengths,
                    "weaknesses": r["item"].weaknesses,
                    "score": r["score"],
                }
                for r in strengths
            ])
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return {
            "query": query,
            "category": category,
            "results": results[:limit],
            "count": len(results),
        }

    def get_similar_examples(
        self,
        category: str,
        query: str,
        limit: int = 5,
    ) -> List[Dict]:
        """
        获取相似示例

        Args:
            category: values | interests | strengths
            query: 查询文本
            limit: 返回数量

        Returns:
            [{"name", "score"}, ...]
        """
        raw = self._searcher.get_similar_examples(category, query, limit)
        return [{"name": e["item"].name, "score": e["score"]} for e in raw]
