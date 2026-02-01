"""
内存向量存储测试
"""
import pytest
from app.core.knowledge.vector.memory import MemoryVectorStore


@pytest.mark.asyncio
async def test_add_documents():
    """测试添加文档"""
    store = MemoryVectorStore()
    
    documents = ["文档1", "文档2", "文档3"]
    ids = await store.add_documents(documents)
    
    assert len(ids) == 3
    assert ids[0].startswith("doc_")


@pytest.mark.asyncio
async def test_search():
    """测试搜索文档"""
    store = MemoryVectorStore()
    
    # 添加文档
    await store.add_documents(["这是测试文档", "另一个文档"])
    
    # 搜索
    results = await store.search("测试", top_k=5)
    
    assert len(results) > 0
    assert "测试" in results[0]["document"]


@pytest.mark.asyncio
async def test_delete():
    """测试删除文档"""
    store = MemoryVectorStore()
    
    # 添加文档
    ids = await store.add_documents(["文档1", "文档2"])
    
    # 删除
    success = await store.delete([ids[0]])
    assert success is True
    
    # 验证已删除
    results = await store.search("文档1", top_k=5)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_clear():
    """测试清空"""
    store = MemoryVectorStore()
    
    # 添加文档
    await store.add_documents(["文档1", "文档2"])
    
    # 清空
    success = await store.clear()
    assert success is True
    
    # 验证已清空
    results = await store.search("文档", top_k=5)
    assert len(results) == 0
