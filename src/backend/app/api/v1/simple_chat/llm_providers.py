"""
LLM Provider 选择：按 VIP 等级和用途（对话/推理）路由到不同模型。
"""
import re
from typing import Optional

from app.core.llmapi import get_default_llm_provider
from app.core.llmapi.factory import create_llm_provider
from app.config.settings import settings


def _resolve_provider_and_key_for_vip(vip_level: int) -> tuple[str, Optional[str], Optional[str]]:
    """按 vip_level 解析 provider/api_key/base_url。"""
    level = 1 if vip_level not in (1, 2) else vip_level
    if level == 2:
        provider = (getattr(settings, "LLM_VIP2_PROVIDER", "kimi") or "kimi").lower()
        if provider == "qwen":
            return (
                "qwen",
                getattr(settings, "QWEN_API_KEY", None),
                getattr(settings, "QWEN_BASE_URL", None),
            )
        return (
            "kimi",
            getattr(settings, "KIMI_API_KEY", None),
            getattr(settings, "KIMI_BASE_URL", None),
        )

    provider = (getattr(settings, "LLM_VIP1_PROVIDER", "deepseek") or "deepseek").lower()
    if provider == "deepseek":
        return ("deepseek", getattr(settings, "DEEPSEEK_API_KEY", None), settings.LLM_BASE_URL)
    if provider == "openai":
        return ("openai", getattr(settings, "OPENAI_API_KEY", None), settings.LLM_BASE_URL)
    return (provider, getattr(settings, "DEEPSEEK_API_KEY", None), settings.LLM_BASE_URL)


def to_non_reasoning_model(model: str) -> str:
    """将推理模型名转换为对话模型名。示例：deepseek-reasoner -> deepseek-chat
    v4 系列模型通过 API 参数控制思维链，无需换模型名，直接返回。
    """
    m = (model or "").strip()
    if not m:
        return "deepseek-v4-pro"
    if "v4" in m.lower():
        return m  # v4 系列通过 extra_body 控制思维链，不换模型名
    if "reasoner" in m.lower():
        return re.sub(r"reasoner", "chat", m, flags=re.IGNORECASE)
    return m


def to_reasoning_model(model: str) -> str:
    """将对话模型名转换为推理模型名。示例：deepseek-chat -> deepseek-reasoner
    v4 系列模型通过 API 参数控制思维链，无需换模型名，直接返回。
    """
    m = (model or "").strip()
    if not m:
        return "deepseek-v4-pro"
    if "v4" in m.lower():
        return m  # v4 系列通过 extra_body 控制思维链，不换模型名
    if "reasoner" in m.lower():
        return m
    if "chat" in m.lower():
        return re.sub(r"chat", "reasoner", m, flags=re.IGNORECASE)
    return "deepseek-v4-pro"


def get_dialogue_llm_provider(vip_level: int = 1):
    """普通对话使用非思考模型；结论卡生成链路再使用推理模型。"""
    llm = get_default_llm_provider(vip_level=vip_level)
    model = (getattr(llm, "model", "") or "").lower()
    if "reasoner" not in model:
        return llm
    provider, api_key, base_url = _resolve_provider_and_key_for_vip(vip_level)
    dialog_model = to_non_reasoning_model(getattr(llm, "model", "") or "deepseek-v4-pro")
    try:
        return create_llm_provider(
            provider=provider,
            model=dialog_model,
            api_key=api_key,
            base_url=base_url,
        )
    except Exception:
        return llm


def get_reasoning_llm_provider(vip_level: int = 1):
    """结论判定/结论卡生成使用推理模型；普通对话用 get_dialogue_llm_provider。"""
    llm = get_default_llm_provider(vip_level=vip_level)
    model = (getattr(llm, "model", "") or "").lower()
    if "reasoner" in model:
        return llm
    provider, api_key, base_url = _resolve_provider_and_key_for_vip(vip_level)
    reasoning_model = to_reasoning_model(getattr(llm, "model", "") or "deepseek-v4-pro")
    try:
        return create_llm_provider(
            provider=provider,
            model=reasoning_model,
            api_key=api_key,
            base_url=base_url,
        )
    except Exception:
        return llm
