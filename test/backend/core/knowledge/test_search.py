"""
知识检索测试
"""
import pytest
import tempfile
import csv
from pathlib import Path
from app.core.knowledge.loader import KnowledgeLoader
from app.core.knowledge.search import KnowledgeSearcher


@pytest.fixture
def temp_csv_dir():
    """创建临时CSV文件"""
    temp_dir = Path(tempfile.mkdtemp())
    
    # 创建价值观CSV
    values_file = temp_dir / "重要的事_价值观.csv"
    with open(values_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "名称", "定义"])
        writer.writeheader()
        writer.writerow({"id": "1", "名称": "发现", "定义": "探索新事物"})
        writer.writerow({"id": "2", "名称": "成长", "定义": "不断进步"})
        writer.writerow({"id": "3", "名称": "创新", "定义": "创造新价值"})
    
    # 创建兴趣CSV
    interests_file = temp_dir / "喜欢的事_热情.csv"
    with open(interests_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "名称"])
        writer.writeheader()
        writer.writerow({"id": "1", "名称": "编程开发"})
        writer.writerow({"id": "2", "名称": "阅读书籍"})
    
    # 创建才能CSV
    strengths_file = temp_dir / "擅长的事_才能.csv"
    with open(strengths_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "名称", "优势", "劣势"])
        writer.writeheader()
        writer.writerow({"id": "1", "名称": "逻辑思维", "优势": "分析能力强", "劣势": "缺乏创意"})
        writer.writerow({"id": "2", "名称": "沟通表达", "优势": "善于交流", "劣势": "不够细致"})
    
    yield temp_dir


def test_search_values(temp_csv_dir):
    """测试搜索价值观"""
    searcher = KnowledgeSearcher(KnowledgeLoader(base_dir=str(temp_csv_dir)))
    
    results = searcher.search_values("发现新事物", limit=5)
    
    assert len(results) > 0
    assert results[0]["item"].name == "发现"
    assert results[0]["score"] > 0


def test_search_interests(temp_csv_dir):
    """测试搜索兴趣"""
    searcher = KnowledgeSearcher(KnowledgeLoader(base_dir=str(temp_csv_dir)))
    
    results = searcher.search_interests("编程", limit=5)
    
    assert len(results) > 0
    assert "编程" in results[0]["item"].name


def test_search_strengths(temp_csv_dir):
    """测试搜索才能"""
    searcher = KnowledgeSearcher(KnowledgeLoader(base_dir=str(temp_csv_dir)))
    
    results = searcher.search_strengths("逻辑", limit=5)
    
    assert len(results) > 0
    assert "逻辑" in results[0]["item"].name


def test_get_similar_examples(temp_csv_dir):
    """测试获取相似示例"""
    searcher = KnowledgeSearcher(KnowledgeLoader(base_dir=str(temp_csv_dir)))
    
    # 测试价值观
    values = searcher.get_similar_examples("values", "发现", limit=3)
    assert len(values) > 0
    
    # 测试兴趣
    interests = searcher.get_similar_examples("interests", "编程", limit=3)
    assert len(interests) > 0


def test_search_questions(temp_csv_dir):
    """测试搜索问题"""
    searcher = KnowledgeSearcher(KnowledgeLoader(base_dir=str(temp_csv_dir)))
    
    # 测试按分类搜索
    results = searcher.search_questions(category="values", limit=5)
    # 如果没有question.md文件，结果可能为空，但不应该报错
    assert isinstance(results, list)
