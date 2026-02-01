"""
知识库模块
"""
from app.core.knowledge.loader import KnowledgeLoader
from app.core.knowledge.search import KnowledgeSearcher

__all__ = [
    "KnowledgeLoader",
    "KnowledgeSearcher",
]
