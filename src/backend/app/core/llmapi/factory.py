"""
LLM Provider工厂

支持 API 池与 VIP 模型：DeepSeek=VIP1（基础），Kimi/Qwen=VIP2（高级）。

模型场景分流（2026-08-19 起，deepseek 专用）：按 usage_context 的 scene 选模型——
scene=chat（前四 phase 对话+结论卡）→ flash；rumination/report/其他 → pro。
"""
from typing import Optional
from app.core.llmapi.base import BaseLLMProvider
from app.core.llmapi.openai_provider import OpenAIProvider
from app.config.settings import settings

# scene → flash 档位（前四 phase values/strengths/interests/purpose 的对话与结论卡）
_FLASH_SCENES = {"chat"}


def _scene_model() -> str:
    """按当前 usage_context 的 scene 确定性选择 deepseek 模型。

    chat → flash（LLM_FLASH_MODEL）；其余（rumination/report/team_analysis/unknown）→ pro。
    usage_context 为无依赖的 contextvar 模块，各入口在 LLM 调用前已设置 scene。
    """
    try:
        from app.core.llmapi.usage_context import get_llm_usage_context

        scene = (get_llm_usage_context().get("scene") or "unknown").strip()
    except Exception:
        scene = "unknown"
    if scene in _FLASH_SCENES:
        return settings.LLM_FLASH_MODEL or "deepseek-v4-flash"
    return settings.LLM_PRO_MODEL or "deepseek-v4-pro"


def create_llm_provider(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> BaseLLMProvider:
    """
    创建LLM Provider实例（从 .env / 环境变量读取配置）
    """
    provider = (provider or settings.LLM_PROVIDER or "openai").lower()
    model = model or settings.LLM_MODEL or "gpt-4"
    if provider == "openai":
        final_api_key = api_key or settings.OPENAI_API_KEY
        final_base_url = base_url or settings.LLM_BASE_URL
        return OpenAIProvider(model=model, api_key=final_api_key, base_url=final_base_url, provider_name="openai")

    if provider == "deepseek":
        final_api_key = api_key or settings.DEEPSEEK_API_KEY
        final_base_url = base_url or settings.LLM_BASE_URL or "https://api.deepseek.com"
        final_model = model or "deepseek-v4-pro"
        return OpenAIProvider(model=final_model, api_key=final_api_key, base_url=final_base_url, provider_name="deepseek")

    if provider == "kimi":
        final_api_key = api_key or getattr(settings, "KIMI_API_KEY", None)
        final_base_url = base_url or getattr(settings, "KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        final_model = model or getattr(settings, "KIMI_MODEL", "moonshot-v1-8k")
        return OpenAIProvider(model=final_model, api_key=final_api_key, base_url=final_base_url, provider_name="kimi")

    if provider == "qwen":
        final_api_key = api_key or getattr(settings, "QWEN_API_KEY", None)
        final_base_url = base_url or getattr(settings, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        final_model = model or getattr(settings, "QWEN_MODEL", "qwen-plus")
        return OpenAIProvider(model=final_model, api_key=final_api_key, base_url=final_base_url, provider_name="qwen")

    raise ValueError(f"不支持的LLM Provider: {provider}")


def _get_vip_provider_config(vip_level: int) -> tuple[str, Optional[str], Optional[str], Optional[str]]:
    """按 VIP 等级返回 (provider, model, api_key, base_url)"""
    level = 1 if vip_level not in (1, 2) else vip_level
    if level == 2:
        p = getattr(settings, "LLM_VIP2_PROVIDER", "deepseek").lower()
        if p == "deepseek":
            # P-A 起（ADR-0008）：VIP2 与 VIP1 同配 DeepSeek；
            # 模型按场景分流（2026-08-19 起），不再读 VIP 模型配置
            return (
                "deepseek",
                _scene_model(),
                settings.DEEPSEEK_API_KEY,
                settings.LLM_BASE_URL or "https://api.deepseek.com",
            )
        if p == "qwen":
            return (
                "qwen",
                getattr(settings, "QWEN_MODEL", "qwen-plus"),
                getattr(settings, "QWEN_API_KEY", None),
                getattr(settings, "QWEN_BASE_URL", None),
            )
        return (
            "kimi",
            getattr(settings, "KIMI_MODEL", "moonshot-v1-8k"),
            getattr(settings, "KIMI_API_KEY", None),
            getattr(settings, "KIMI_BASE_URL", None),
        )
    # VIP1 = DeepSeek
    p = getattr(settings, "LLM_VIP1_PROVIDER", "deepseek").lower()
    if p == "deepseek":
        return (
            "deepseek",
            _scene_model(),
            settings.DEEPSEEK_API_KEY,
            settings.LLM_BASE_URL or "https://api.deepseek.com",
        )
    return (
        p,
        getattr(settings, "LLM_VIP1_MODEL", None) or settings.LLM_MODEL,
        settings.OPENAI_API_KEY if p == "openai" else settings.DEEPSEEK_API_KEY,
        settings.LLM_BASE_URL,
    )


def get_llm_provider_for_vip(vip_level: int = 1) -> BaseLLMProvider:
    """
    按 VIP 等级获取 LLM Provider。
    VIP1 = DeepSeek（基础），VIP2 = Kimi/Qwen（高级）。
    """
    provider, model, api_key, base_url = _get_vip_provider_config(vip_level)
    return create_llm_provider(provider=provider, model=model, api_key=api_key, base_url=base_url)


def get_default_llm_provider(vip_level: Optional[int] = None) -> BaseLLMProvider:
    """
    获取默认LLM Provider。
    若传入 vip_level（1 或 2），则按 VIP 选择；否则使用 legacy 配置（LLM_PROVIDER）。

    DB 配置优先：无 vip_level 时先查 resolver（DB 默认记录），
    命中则用 DB 中的 provider/model/api_key/base_url；否则回退 .env。
    """
    if vip_level is not None and vip_level in (1, 2):
        return get_llm_provider_for_vip(vip_level)
    try:
        from app.core.llmapi.resolver import get_default_config

        rc = get_default_config()
        return create_llm_provider(
            provider=rc.provider,
            model=rc.model,
            api_key=rc.api_key,
            base_url=rc.base_url,
        )
    except Exception:
        # resolver 任何异常 → 完全回退原行为
        return create_llm_provider()
