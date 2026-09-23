"""
模型场景分流测试（2026-08-19；2026-09-23 起三场景改由 admin 场景配置接管）

deepseek provider 的模型由 usage_context 的 scene 确定性决定：
- chat / rumination / report：读 admin 场景配置（scene_config，档位固定映射
  flash→deepseek-v4-flash / pro→deepseek-v4-pro），不受 .env 覆盖影响——
  详见 test_llm_scene_config.py
- team_analysis / 未设置 → pro（LLM_PRO_MODEL 可覆盖）
- 非 deepseek provider 不受 scene 影响

注意：默认值断言需先把 settings 覆盖回 None，否则会被 .env 中的显式配置影响。
"""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.core.llmapi.factory import _get_vip_provider_config, _scene_model
from app.core.llmapi.usage_context import (
    reset_llm_usage_context,
    set_llm_usage_context,
)
from app.utils import admin_config as admin_config_mod


@pytest.fixture(autouse=True)
def _clean_scene_ctx():
    """每个测试结束后复位 contextvar，避免串上下文。"""
    yield
    # 无 token 可复位时直接再 set 一个 unknown 兜底（contextvar 测试间隔离兜底）
    token = set_llm_usage_context(scene="unknown")
    reset_llm_usage_context(token)


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """隔离 admin 场景配置存储（2026-09-23 起 chat/rumination/report 读该配置，
    未保存时与默认值一致），避免开发机真实 data/ 影响断言。"""
    path = tmp_path / "admin_runtime_config.json"
    monkeypatch.setattr(admin_config_mod, "_config_path", lambda: path)


@pytest.fixture
def _default_models(monkeypatch: pytest.MonkeyPatch):
    """屏蔽 .env 中 LLM_FLASH_MODEL/LLM_PRO_MODEL 覆盖，断言代码内默认值。"""
    monkeypatch.setattr(settings, "LLM_FLASH_MODEL", None)
    monkeypatch.setattr(settings, "LLM_PRO_MODEL", None)


def _model_for_scene(scene: str | None) -> str:
    token = set_llm_usage_context(scene=scene)
    try:
        return _scene_model()
    finally:
        reset_llm_usage_context(token)


@pytest.mark.usefixtures("_default_models")
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

    def test_env_override_only_uncovered_scenes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """2026-09-23 起 chat/rumination/report 由 admin 场景配置接管（档位固定映射，
        不受 .env 影响，见 test_llm_scene_config.py）；.env 覆盖仅对未覆盖场景生效。"""
        monkeypatch.setattr(settings, "LLM_PRO_MODEL", "deepseek-v4-pro-x")
        assert _model_for_scene("team_analysis") == "deepseek-v4-pro-x"
        assert _model_for_scene("unknown") == "deepseek-v4-pro-x"
        # 三场景保持固定映射，.env 覆盖不生效
        monkeypatch.setattr(settings, "LLM_FLASH_MODEL", "deepseek-v4-flash-x")
        assert _model_for_scene("chat") == "deepseek-v4-flash"
        assert _model_for_scene("report") == "deepseek-v4-pro"


@pytest.mark.usefixtures("_default_models")
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
