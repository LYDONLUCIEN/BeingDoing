"""
API配置接口测试
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


def test_get_architecture_config(client):
    """测试获取架构配置接口"""
    response = client.get("/api/v1/config/architecture")
    assert response.status_code == 200
    data = response.json()
    
    assert "architecture_mode" in data
    assert "audio_mode" in data
    assert "features" in data
    assert isinstance(data["features"], dict)
    assert "gateway" in data["features"]
    assert "vector_db" in data["features"]
