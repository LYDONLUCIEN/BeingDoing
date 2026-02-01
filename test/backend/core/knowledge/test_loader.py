"""
知识库加载器测试
"""
import pytest
import tempfile
import csv
from pathlib import Path
from app.core.knowledge.loader import KnowledgeLoader, ValueItem, InterestItem, StrengthItem


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
    
    # 创建兴趣CSV
    interests_file = temp_dir / "喜欢的事_热情.csv"
    with open(interests_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "名称"])
        writer.writeheader()
        writer.writerow({"id": "1", "名称": "编程"})
        writer.writerow({"id": "2", "名称": "阅读"})
    
    # 创建才能CSV
    strengths_file = temp_dir / "擅长的事_才能.csv"
    with open(strengths_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "名称", "优势", "劣势"])
        writer.writeheader()
        writer.writerow({"id": "1", "名称": "逻辑思维", "优势": "分析能力强", "劣势": "缺乏创意"})
    
    yield temp_dir


def test_load_values(temp_csv_dir):
    """测试加载价值观"""
    loader = KnowledgeLoader(base_dir=str(temp_csv_dir))
    values = loader.load_values()
    
    assert len(values) == 2
    assert values[0].name == "发现"
    assert values[0].definition == "探索新事物"


def test_load_interests(temp_csv_dir):
    """测试加载兴趣"""
    loader = KnowledgeLoader(base_dir=str(temp_csv_dir))
    interests = loader.load_interests()
    
    assert len(interests) == 2
    assert interests[0].name == "编程"


def test_load_strengths(temp_csv_dir):
    """测试加载才能"""
    loader = KnowledgeLoader(base_dir=str(temp_csv_dir))
    strengths = loader.load_strengths()
    
    assert len(strengths) == 1
    assert strengths[0].name == "逻辑思维"
    assert strengths[0].strengths == "分析能力强"


def test_load_all(temp_csv_dir):
    """测试加载所有数据"""
    loader = KnowledgeLoader(base_dir=str(temp_csv_dir))
    all_data = loader.load_all()
    
    assert "values" in all_data
    assert "interests" in all_data
    assert "strengths" in all_data
    assert len(all_data["values"]) == 2


def test_cache(temp_csv_dir):
    """测试缓存机制"""
    loader = KnowledgeLoader(base_dir=str(temp_csv_dir))
    
    # 第一次加载
    values1 = loader.load_values()
    
    # 第二次加载（应该使用缓存）
    values2 = loader.load_values()
    
    assert values1 is values2  # 同一个对象
    
    # 强制重新加载
    values3 = loader.load_values(force_reload=True)
    assert values3 is not values1  # 新对象


def test_file_not_found():
    """测试文件不存在的情况"""
    loader = KnowledgeLoader(base_dir="/nonexistent/path")
    
    with pytest.raises(FileNotFoundError):
        loader.load_values()
