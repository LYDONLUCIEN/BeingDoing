"""
OpenAI Whisper Provider测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.asr.openai_whisper_provider import OpenAIWhisperProvider, ASRError


@pytest.fixture
def mock_openai_client():
    """模拟OpenAI客户端"""
    with patch("app.core.asr.openai_whisper_provider.AsyncOpenAI") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


@pytest.fixture
def provider(mock_openai_client):
    """创建Provider实例"""
    return OpenAIWhisperProvider(api_key="test-key")


@pytest.mark.asyncio
async def test_transcribe_success(provider, mock_openai_client):
    """测试成功转录"""
    # 模拟API响应
    mock_response = MagicMock()
    mock_response.text = "测试转录文本"
    
    mock_openai_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
    
    # 模拟音频文件
    audio_file = b"fake audio data"
    
    response = await provider.transcribe(audio_file)
    
    assert response.text == "测试转录文本"


@pytest.mark.asyncio
async def test_transcribe_error(provider, mock_openai_client):
    """测试转录错误处理"""
    mock_openai_client.audio.transcriptions.create = AsyncMock(
        side_effect=Exception("API错误")
    )
    
    audio_file = b"fake audio data"
    
    with pytest.raises(ASRError):
        await provider.transcribe(audio_file)
