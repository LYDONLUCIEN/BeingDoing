"""
向量存储工厂
"""
from typing import Optional
from app.core.knowledge.vector.base import BaseVectorStore
from app.core.knowledge.vector.memory import MemoryVectorStore
from app.config.architecture import get_arch_config


def create_vector_store() -> BaseVectorStore:
    """
    创建向量存储实例
    
    根据架构模式选择实现：
    - simple: 内存向量存储（占位实现）
    - full: Chroma/FAISS（保留接口，暂不实现）
    
    Returns:
        向量存储实例
    """
    config = get_arch_config()
    vector_store_type = config.get("vector_store", "memory")
    
    if vector_store_type == "memory":
        return MemoryVectorStore()
    elif vector_store_type == "chroma":
        # 保留接口，暂不实现
        raise NotImplementedError("Chroma向量存储暂未实现，请使用memory模式")
    elif vector_store_type == "faiss":
        # 保留接口，暂不实现
        raise NotImplementedError("FAISS向量存储暂未实现，请使用memory模式")
    else:
        # 默认使用内存实现
        return MemoryVectorStore()


def get_default_vector_store() -> BaseVectorStore:
    """
    获取默认向量存储实例
    
    Returns:
        默认向量存储实例
    """
    return create_vector_store()
