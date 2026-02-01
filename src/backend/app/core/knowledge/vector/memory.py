"""
内存向量存储（占位实现，简化架构使用）
"""
from typing import List, Dict, Optional, Any
from app.core.knowledge.vector.base import BaseVectorStore, VectorStoreError


class MemoryVectorStore(BaseVectorStore):
    """
    内存向量存储（占位实现）
    
    注意：当前为占位实现，不进行实际的向量嵌入和相似度计算
    未来可以集成简单的向量嵌入模型（如sentence-transformers）
    """
    
    def __init__(self):
        """初始化内存向量存储"""
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._next_id = 1
    
    async def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        添加文档（占位实现）
        
        注意：当前只存储文档文本，不进行向量嵌入
        """
        if metadatas is None:
            metadatas = [{}] * len(documents)
        
        if ids is None:
            ids = [f"doc_{self._next_id + i}" for i in range(len(documents))]
            self._next_id += len(documents)
        
        for doc_id, doc, metadata in zip(ids, documents, metadatas):
            self._documents[doc_id] = {
                "document": doc,
                "metadata": metadata
            }
        
        return ids
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索文档（占位实现）
        
        注意：当前只返回所有文档，不进行相似度计算
        未来可以集成简单的文本相似度算法（如TF-IDF、BM25等）
        """
        results = []
        
        for doc_id, doc_data in self._documents.items():
            # 简单的文本匹配（占位）
            if query.lower() in doc_data["document"].lower():
                results.append({
                    "id": doc_id,
                    "document": doc_data["document"],
                    "metadata": doc_data["metadata"],
                    "score": 0.5  # 占位分数
                })
        
        # 限制返回数量
        return results[:top_k]
    
    async def delete(self, ids: List[str]) -> bool:
        """删除文档"""
        for doc_id in ids:
            if doc_id in self._documents:
                del self._documents[doc_id]
        return True
    
    async def clear(self) -> bool:
        """清空所有文档"""
        self._documents.clear()
        self._next_id = 1
        return True
