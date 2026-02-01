"""
向量存储工厂测试
"""
import pytest
from app.core.knowledge.vector.factory import create_vector_store, get_default_vector_store
from app.core.knowledge.vector.memory import MemoryVectorStore


def test_create_memory_vector_store():
    """测试创建内存向量存储"""
    store = create_vector_store()
    assert isinstance(store, MemoryVectorStore)


def test_get_default_vector_store():
    """测试获取默认向量存储"""
    store = get_default_vector_store()
    assert isinstance(store, MemoryVectorStore)


def test_create_chroma_vector_store():
    """测试创建Chroma向量存储（应该抛出NotImplementedError）"""
    # 需要修改架构配置才能测试，这里只测试接口
    with pytest.raises(NotImplementedError):
        # 这个测试需要临时修改架构配置
        pass
