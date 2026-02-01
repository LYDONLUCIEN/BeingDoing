"""
LLM基础接口测试
"""
import pytest
from app.core.llmapi.base import BaseLLMProvider, LLMMessage, LLMResponse


def test_llm_message_model():
    """测试LLM消息模型"""
    msg = LLMMessage(role="user", content="测试消息")
    assert msg.role == "user"
    assert msg.content == "测试消息"


def test_llm_response_model():
    """测试LLM响应模型"""
    response = LLMResponse(
        content="测试回复",
        model="gpt-4",
        usage={"prompt_tokens": 10, "completion_tokens": 20}
    )
    assert response.content == "测试回复"
    assert response.model == "gpt-4"
    assert response.usage["prompt_tokens"] == 10
