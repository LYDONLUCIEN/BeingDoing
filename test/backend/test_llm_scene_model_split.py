"""
模型场景分流测试（2026-08-19）

deepseek provider 的模型由 usage_context 的 scene 确定性决定：
- scene=chat（前四 phase values/strengths/interests/purpose 的对话+结论卡）→ flash
- scene=rumination / report / team_analysis / 未设置 → pro
- LLM_FLASH_MODEL / LLM_PRO_MODEL 可覆盖默认值
- 非 deepseek provider 不受 scene 影响
"""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.core.llmapi.factory import _get_vip_provider_config, _scene_model
from app.core.llmapi.usage_context import (
    reset_llm_usage_context,
    set_llm_usage_context,
)


@pytest.fixture(autouse=True)
def _clean_scene_ctx():
    """每个测试结束后复位 contextvar，避免串上下文。"""
    yield
    # 无 token 可复位时直接再 set 一个 unknown 兜底（contextvar 测试间隔离兜底）
    token = set_llm_usage_context(scene="unknown")
    reset_llm_usage_context(token)


def _model_for_scene(scene: str | None) -> str:
    token = set_llm_usage_context(scene=scene)
    try:
        return _scene_model()
    finally:
        reset_llm_usage_context(token)


class TestSceneModel:
    def test_chat_scene_uses_flash(self) -> None:
        assert _model_for_scene("chat") == "deepseek-v4-flash"

    def test_rumination_scene_uses_pro(self) -> None:
        assert _model_for_scene("rumination") == "deepseek-v4-pro"

    def test_report_scene_uses_pro(self) -> None:
        assert _model_for_scene("report") == "deepseek-v4-pro"

    def test_team_analysis_scene_uses_pro(self) -> None:
        assert _model_for_scene("team_analysis") == "deepseek-v4-pro"

    def test_unset_scene_uses_pro(self) -> None:
        assert _scene_model() == "deepseek-v4-pro"

    def test_unknown_scene_uses_pro(self) -> None:
        assert _model_for_scene("unknown") == "deepseek-v4-pro"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "LLM_FLASH_MODEL", "deepseek-v4-flash-x")
        monkeypatch.setattr(settings, "LLM_PRO_MODEL", "deepseek-v4-pro-x")
        assert _model_for_scene("chat") == "deepseek-v4-flash-x"
        assert _model_for_scene("report") == "deepseek-v4-pro-x"


class TestVipProviderConfig:
    def test_vip1_deepseek_uses_scene_model(self) -> None:
        token = set_llm_usage_context(scene="chat")
        try:
            provider, model, _key, _url = _get_vip_provider_config(1)
        finally:
            reset_llm_usage_context(token)
        assert provider == "deepseek"
        assert model == "deepseek-v4-flash"

    def test_vip2_deepseek_uses_scene_model(self) -> None:
        """VIP2-deepseek 分支同样走 scene 分流（原误读 LLM_VIP1_MODEL 的分支已删除）。"""
        token = set_llm_usage_context(scene="rumination")
        try:
            provider, model, _key, _url = _get_vip_provider_config(2)
        finally:
            reset_llm_usage_context(token)
        assert provider == "deepseek"
        assert model == "deepseek-v4-pro"

    def test_non_deepseek_provider_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非 deepseek provider（如 VIP2=qwen）不受 scene 影响。"""
        monkeypatch.setattr(settings, "LLM_VIP2_PROVIDER", "qwen")
        token = set_llm_usage_context(scene="chat")
        try:
            provider, model, _key, _url = _get_vip_provider_config(2)
        finally:
            reset_llm_usage_context(token)
        assert provider == "qwen"
        assert model == getattr(settings, "QWEN_MODEL", "qwen-plus")
