"""
LLM Provider工厂测试
"""
import pytest
from unittest.mock import patch
from app.core.llmapi.factory import create_llm_provider, get_default_llm_provider
from app.core.llmapi.openai_provider import OpenAIProvider


def test_create_openai_provider():
    """测试创建OpenAI Provider"""
    provider = create_llm_provider(
        provider="openai",
        model="gpt-3.5-turbo",
        api_key="test-key"
    )
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-3.5-turbo"


def test_create_unsupported_provider():
    """测试创建不支持的Provider"""
    with pytest.raises(ValueError, match="不支持的LLM Provider"):
        create_llm_provider(provider="unsupported")


@patch("app.core.llmapi.factory.settings")
def test_get_default_llm_provider(mock_settings):
    """测试获取默认Provider"""
    mock_settings.LLM_PROVIDER = "openai"
    mock_settings.LLM_MODEL = "gpt-4"
    mock_settings.OPENAI_API_KEY = "test-key"
    
    provider = get_default_llm_provider()
    assert isinstance(provider, OpenAIProvider)
