"""
中间件测试
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.api.middleware import AudioModeMiddleware, ErrorHandlerMiddleware
from app.config.audio_config import AudioConfig


@pytest.fixture
def app_with_middleware():
    """创建带中间件的测试应用"""
    app = FastAPI()
    
    @app.get("/api/v1/audio/test")
    async def audio_endpoint():
        return {"status": "ok"}
    
    @app.get("/api/v1/normal")
    async def normal_endpoint():
        return {"status": "ok"}
    
    @app.get("/api/v1/error")
    async def error_endpoint():
        raise ValueError("Test error")
    
    app.add_middleware(AudioModeMiddleware)
    app.add_middleware(ErrorHandlerMiddleware)
    return app


def test_audio_middleware_disabled(app_with_middleware):
    """测试语音中间件 - 禁用状态"""
    # 临时禁用语音功能
    original_mode = AudioConfig.AUDIO_MODE
    AudioConfig.AUDIO_MODE = False
    
    try:
        client = TestClient(app_with_middleware)
        response = client.get("/api/v1/audio/test")
        
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == 403
        assert "Audio mode is disabled" in data["message"]
    finally:
        AudioConfig.AUDIO_MODE = original_mode


def test_audio_middleware_enabled(app_with_middleware):
    """测试语音中间件 - 启用状态"""
    # 临时启用语音功能
    original_mode = AudioConfig.AUDIO_MODE
    AudioConfig.AUDIO_MODE = True
    
    try:
        client = TestClient(app_with_middleware)
        response = client.get("/api/v1/audio/test")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    finally:
        AudioConfig.AUDIO_MODE = original_mode


def test_audio_middleware_normal_endpoint(app_with_middleware):
    """测试语音中间件 - 普通接口不受影响"""
    client = TestClient(app_with_middleware)
    response = client.get("/api/v1/normal")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_error_handler_middleware(app_with_middleware):
    """测试错误处理中间件"""
    client = TestClient(app_with_middleware)
    response = client.get("/api/v1/error")
    
    # 应该捕获错误并返回500
    assert response.status_code == 500
    data = response.json()
    assert data["code"] == 500
