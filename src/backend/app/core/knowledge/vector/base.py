"""
向量存储基类接口
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any


class BaseVectorStore(ABC):
    """向量存储基类"""
    
    @abstractmethod
    async def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ) -> List[str]:
        """
        添加文档到向量存储
        
        Args:
            documents: 文档列表
            metadatas: 元数据列表
            ids: 文档ID列表
        
        Returns:
            文档ID列表
        """
        pass
    
    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索相似文档
        
        Args:
            query: 查询文本
            top_k: 返回数量
            filter: 过滤条件
        
        Returns:
            相似文档列表（包含文档、相似度、元数据等）
        """
        pass
    
    @abstractmethod
    async def delete(self, ids: List[str]) -> bool:
        """
        删除文档
        
        Args:
            ids: 文档ID列表
        
        Returns:
            是否成功
        """
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """
        清空所有文档
        
        Returns:
            是否成功
        """
        pass


class VectorStoreError(Exception):
    """向量存储相关错误"""
    pass
