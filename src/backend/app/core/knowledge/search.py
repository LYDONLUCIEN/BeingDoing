"""
知识检索模块（关键词匹配）
"""
from typing import List, Dict, Optional
from app.core.knowledge.loader import (
    KnowledgeLoader,
    ValueItem,
    InterestItem,
    StrengthItem,
    QuestionItem
)


class KnowledgeSearcher:
    """知识检索器（关键词匹配）"""
    
    def __init__(self, loader: Optional[KnowledgeLoader] = None):
        """
        初始化检索器
        
        Args:
            loader: 知识库加载器，None则创建新实例
        """
        self.loader = loader or KnowledgeLoader()
        self._ensure_loaded()
    
    def _ensure_loaded(self):
        """确保数据已加载"""
        if self.loader._values_cache is None:
            self.loader.load_all()
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        提取关键词
        
        Args:
            text: 输入文本
        
        Returns:
            关键词列表
        """
        # 简单的关键词提取（可以后续优化）
        # 移除标点符号和常见停用词
        import re
        stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
        
        # 提取中文词汇（2-4字）
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        
        # 过滤停用词
        keywords = [kw for kw in keywords if kw not in stop_words]
        
        return list(set(keywords))  # 去重
    
    def _match_score(self, text: str, keywords: List[str]) -> float:
        """
        计算匹配分数
        
        Args:
            text: 文本内容
            keywords: 关键词列表
        
        Returns:
            匹配分数（0-1）
        """
        if not keywords:
            return 0.0
        
        matches = sum(1 for kw in keywords if kw in text)
        return matches / len(keywords) if keywords else 0.0
    
    def search_values(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        搜索价值观
        
        Args:
            query: 查询文本
            limit: 返回数量限制
        
        Returns:
            匹配的价值观列表（包含匹配分数）
        """
        values = self.loader.load_values()
        keywords = self._extract_keywords(query)
        
        results = []
        for value in values:
            # 在名称和定义中搜索
            score = max(
                self._match_score(value.name, keywords),
                self._match_score(value.definition, keywords) * 0.5  # 定义权重较低
            )
            
            if score > 0:
                results.append({
                    "item": value,
                    "score": score,
                    "matched_text": value.name
                })
        
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:limit]
    
    def search_interests(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        搜索兴趣
        
        Args:
            query: 查询文本
            limit: 返回数量限制
        
        Returns:
            匹配的兴趣列表
        """
        interests = self.loader.load_interests()
        keywords = self._extract_keywords(query)
        
        results = []
        for interest in interests:
            score = self._match_score(interest.name, keywords)
            
            if score > 0:
                results.append({
                    "item": interest,
                    "score": score,
                    "matched_text": interest.name
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def search_strengths(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        搜索才能
        
        Args:
            query: 查询文本
            limit: 返回数量限制
        
        Returns:
            匹配的才能列表
        """
        strengths = self.loader.load_strengths()
        keywords = self._extract_keywords(query)
        
        results = []
        for strength in strengths:
            # 在名称、优势、劣势中搜索
            score = max(
                self._match_score(strength.name, keywords),
                self._match_score(strength.strengths, keywords) * 0.5,
                self._match_score(strength.weaknesses, keywords) * 0.3
            )
            
            if score > 0:
                results.append({
                    "item": strength,
                    "score": score,
                    "matched_text": strength.name
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def search_questions(
        self,
        category: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        搜索问题
        
        Args:
            category: 问题分类（values/strengths/interests），None表示所有
            query: 查询文本，None表示返回所有
            limit: 返回数量限制
        
        Returns:
            匹配的问题列表
        """
        questions = self.loader.load_questions()
        
        # 按分类过滤
        if category:
            questions = [q for q in questions if q.category == category]
        
        # 按查询文本搜索
        if query:
            keywords = self._extract_keywords(query)
            results = []
            for question in questions:
                score = self._match_score(question.content, keywords)
                if score > 0:
                    results.append({
                        "item": question,
                        "score": score,
                        "matched_text": question.content
                    })
            
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
        else:
            # 返回所有问题
            return [{"item": q, "score": 1.0, "matched_text": q.content} for q in questions[:limit]]
    
    def get_similar_examples(
        self,
        category: str,
        query: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        获取相似示例
        
        Args:
            category: 分类（values/interests/strengths）
            query: 查询文本
            limit: 返回数量限制
        
        Returns:
            相似示例列表
        """
        if category == "values":
            return self.search_values(query, limit)
        elif category == "interests":
            return self.search_interests(query, limit)
        elif category == "strengths":
            return self.search_strengths(query, limit)
        else:
            return []
