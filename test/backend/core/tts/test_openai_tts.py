"""
OpenAI TTS Provider测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.tts.openai_tts_provider import OpenAITTSProvider, TTSError


@pytest.fixture
def mock_openai_client():
    """模拟OpenAI客户端"""
    with patch("app.core.tts.openai_tts_provider.AsyncOpenAI") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


@pytest.fixture
def provider(mock_openai_client):
    """创建Provider实例"""
    return OpenAITTSProvider(api_key="test-key")


@pytest.mark.asyncio
async def test_synthesize_success(provider, mock_openai_client):
    """测试成功合成"""
    # 模拟API响应
    mock_response = MagicMock()
    mock_response.content = b"fake audio data"
    
    mock_openai_client.audio.speech.create = AsyncMock(return_value=mock_response)
    
    response = await provider.synthesize("测试文本", voice="alloy")
    
    assert response.audio_data == b"fake audio data"
    assert response.format == "mp3"


@pytest.mark.asyncio
async def test_synthesize_invalid_voice(provider):
    """测试无效声音类型"""
    with pytest.raises(ValueError, match="不支持的声音类型"):
        await provider.synthesize("测试", voice="invalid")


@pytest.mark.asyncio
async def test_synthesize_invalid_speed(provider):
    """测试无效语速"""
    with pytest.raises(ValueError, match="语速必须在"):
        await provider.synthesize("测试", speed=5.0)


@pytest.mark.asyncio
async def test_synthesize_error(provider, mock_openai_client):
    """测试合成错误处理"""
    mock_openai_client.audio.speech.create = AsyncMock(
        side_effect=Exception("API错误")
    )
    
    with pytest.raises(TTSError):
        await provider.synthesize("测试")
