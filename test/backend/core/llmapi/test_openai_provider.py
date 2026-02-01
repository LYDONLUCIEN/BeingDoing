"""
OpenAI Provider测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.llmapi.openai_provider import OpenAIProvider, LLMError
from app.core.llmapi.base import LLMMessage


@pytest.fixture
def mock_openai_client():
    """模拟OpenAI客户端"""
    with patch("app.core.llmapi.openai_provider.AsyncOpenAI") as mock:
        client = AsyncMock()
        mock.return_value = client
        yield client


@pytest.fixture
def provider(mock_openai_client):
    """创建Provider实例"""
    return OpenAIProvider(
        model="gpt-3.5-turbo",
        api_key="test-key"
    )


@pytest.mark.asyncio
async def test_openai_provider_init(provider):
    """测试Provider初始化"""
    assert provider.model == "gpt-3.5-turbo"
    assert provider.api_key == "test-key"


@pytest.mark.asyncio
async def test_count_tokens(provider):
    """测试token计数"""
    text = "Hello, world!"
    count = await provider.count_tokens(text)
    assert count > 0
    assert isinstance(count, int)


@pytest.mark.asyncio
async def test_chat_success(provider, mock_openai_client):
    """测试成功聊天请求"""
    # 模拟API响应
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "测试回复"
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage = MagicMock()
    mock_response.usage.model_dump.return_value = {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30
    }
    
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    # 调用chat
    messages = [LLMMessage(role="user", content="测试")]
    response = await provider.chat(messages)
    
    assert response.content == "测试回复"
    assert response.model == "gpt-3.5-turbo"
    assert response.usage is not None


@pytest.mark.asyncio
async def test_chat_error(provider, mock_openai_client):
    """测试聊天请求错误处理"""
    # 模拟API错误
    mock_openai_client.chat.completions.create = AsyncMock(
        side_effect=Exception("API错误")
    )
    
    messages = [LLMMessage(role="user", content="测试")]
    
    with pytest.raises(LLMError):
        await provider.chat(messages)


@pytest.mark.asyncio
async def test_chat_stream(provider, mock_openai_client):
    """测试流式聊天"""
    # 模拟流式响应
    async def mock_stream():
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"
        yield chunk1
        
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " World"
        yield chunk2
    
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_stream())
    
    messages = [LLMMessage(role="user", content="测试")]
    chunks = []
    async for chunk in provider.chat_stream(messages):
        chunks.append(chunk)
    
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_estimate_cost(provider):
    """测试成本估算"""
    messages = [
        LLMMessage(role="user", content="测试消息"),
        LLMMessage(role="assistant", content="测试回复")
    ]
    
    cost_info = await provider.estimate_cost(messages, response_tokens=20)
    
    assert "input_tokens" in cost_info
    assert "output_tokens" in cost_info
    assert "total_cost" in cost_info
    assert cost_info["output_tokens"] == 20
