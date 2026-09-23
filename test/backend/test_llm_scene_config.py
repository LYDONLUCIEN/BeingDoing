"""
LLM 场景分流配置测试（2026-09-23）

admin 可配置 chat/rumination/report 三场景的 flash|pro 档位与 thinking 开关：
- 档位固定映射 flash→deepseek-v4-flash / pro→deepseek-v4-pro，不受 .env 覆盖影响
- 未保存配置时走默认（chat→flash，rumination/report→pro，thinking 全开）
- team_analysis/unknown 场景仍走 .env 兜底（LLM_FLASH_MODEL/LLM_PRO_MODEL）
- thinking：三场景读配置；其余场景兜底 settings.LLM_THINKING_ENABLED
- 关闭 thinking → 发 temperature + extra_body={"thinking":{"type":"disabled"}}（DeepSeek V4）

相关模块：core/llmapi/scene_config.py、api/v1/llm_scene.py、
factory._scene_model、openai_provider._apply_thinking_kwargs。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth import get_current_user
from app.config.settings import settings
from app.core.llmapi import scene_config
from app.core.llmapi.factory import _scene_model
from app.core.llmapi.openai_provider import OpenAIProvider
from app.core.llmapi.usage_context import reset_llm_usage_context, set_llm_usage_context
from app.main import app
from app.utils import admin_config as admin_config_mod


@pytest.fixture(autouse=True)
def _clean_scene_ctx():
    """每个测试结束后复位 contextvar，避免串上下文。"""
    yield
    token = set_llm_usage_context(scene="unknown")
    reset_llm_usage_context(token)


@pytest.fixture
def _tmp_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """把 admin_runtime_config.json 重定向到临时文件（读与写都不碰真实 data/）。"""
    path = tmp_path / "admin_runtime_config.json"
    monkeypatch.setattr(admin_config_mod, "_config_path", lambda: path)
    return path


def _set_scene(scene: str | None):
    return set_llm_usage_context(scene=scene)


def _save_scene_config(value: dict) -> None:
    admin_config_mod.set_admin_config(scene_config.CONFIG_KEY, value)


# ── 配置读取与合并 ────────────────────────────────────────
class TestSceneConfig:
    def test_empty_store_returns_defaults(self, _tmp_store) -> None:
        cfg = scene_config.get_llm_scene_config()
        assert cfg == {
            "chat": {"tier": "flash", "thinking": True},
            "rumination": {"tier": "pro", "thinking": True},
            "report": {"tier": "pro", "thinking": True},
        }

    def test_partial_save_merged_with_defaults(self, _tmp_store) -> None:
        _save_scene_config({"rumination": {"tier": "flash"}})
        cfg = scene_config.get_llm_scene_config()
        assert cfg["rumination"] == {"tier": "flash", "thinking": True}  # thinking 缺省回默认
        assert cfg["chat"]["tier"] == "flash"
        assert cfg["report"]["tier"] == "pro"

    def test_dirty_values_fall_back_to_defaults(self, _tmp_store) -> None:
        _save_scene_config(
            {
                "chat": {"tier": "ultra", "thinking": "yes"},  # 均非法
                "report": {"tier": 123},
            }
        )
        cfg = scene_config.get_llm_scene_config()
        assert cfg["chat"] == {"tier": "flash", "thinking": True}
        assert cfg["report"] == {"tier": "pro", "thinking": True}

    def test_tier_model_mapping(self, _tmp_store) -> None:
        assert scene_config.get_scene_tier_model("chat") == "deepseek-v4-flash"
        assert scene_config.get_scene_tier_model("rumination") == "deepseek-v4-pro"
        assert scene_config.get_scene_tier_model("report") == "deepseek-v4-pro"
        assert scene_config.get_scene_tier_model("team_analysis") is None
        assert scene_config.get_scene_tier_model(None) is None

    def test_thinking_fallback_for_uncovered_scene(self, _tmp_store, monkeypatch) -> None:
        _save_scene_config({"chat": {"tier": "flash", "thinking": False}})
        assert scene_config.is_scene_thinking_enabled("chat") is False
        # 未覆盖场景兜底全局开关
        monkeypatch.setattr(settings, "LLM_THINKING_ENABLED", True)
        assert scene_config.is_scene_thinking_enabled("team_analysis") is True
        monkeypatch.setattr(settings, "LLM_THINKING_ENABLED", False)
        assert scene_config.is_scene_thinking_enabled("unknown") is False


# ── 校验 ─────────────────────────────────────────────────
class TestValidate:
    def test_valid_partial(self) -> None:
        cleaned = scene_config.validate_scene_config({"chat": {"tier": "pro"}})
        assert cleaned == {"chat": {"tier": "pro"}}

    def test_valid_full(self) -> None:
        cfg = {
            s: {"tier": "pro", "thinking": False}
            for s in ("chat", "rumination", "report")
        }
        assert scene_config.validate_scene_config(cfg) == cfg

    @pytest.mark.parametrize(
        "bad",
        [
            {"chat": {"tier": "ultra"}},
            {"unknown_scene": {"tier": "pro"}},
            {"chat": {"thinking": "yes"}},
            {"chat": {"extra": 1}},
            {"chat": "flash"},
        ],
    )
    def test_invalid_raises(self, bad) -> None:
        with pytest.raises(ValueError):
            scene_config.validate_scene_config(bad)


# ── factory 分流（admin 配置优先于 .env）──────────────────
class TestFactorySceneModel:
    def test_defaults_fixed_mapping_beats_env(self, _tmp_store, monkeypatch) -> None:
        """.env 覆盖（如 LLM_FLASH_MODEL=deepseek-v4-pro）对三场景不再生效。"""
        monkeypatch.setattr(settings, "LLM_FLASH_MODEL", "deepseek-v4-flash-x")
        monkeypatch.setattr(settings, "LLM_PRO_MODEL", "deepseek-v4-pro-x")
        token = _set_scene("chat")
        try:
            assert _scene_model() == "deepseek-v4-flash"
        finally:
            reset_llm_usage_context(token)
        token = _set_scene("rumination")
        try:
            assert _scene_model() == "deepseek-v4-pro"
        finally:
            reset_llm_usage_context(token)

    def test_saved_config_overrides(self, _tmp_store) -> None:
        _save_scene_config({"chat": {"tier": "pro", "thinking": True}})
        token = _set_scene("chat")
        try:
            assert _scene_model() == "deepseek-v4-pro"
        finally:
            reset_llm_usage_context(token)

    def test_uncovered_scene_still_uses_env(self, _tmp_store, monkeypatch) -> None:
        """team_analysis/unknown 场景维持 .env 分流（2026-08-19 原行为）。"""
        monkeypatch.setattr(settings, "LLM_PRO_MODEL", "deepseek-v4-pro-x")
        token = _set_scene("team_analysis")
        try:
            assert _scene_model() == "deepseek-v4-pro-x"
        finally:
            reset_llm_usage_context(token)


# ── provider thinking 参数 ────────────────────────────────
def _provider(model: str) -> OpenAIProvider:
    return OpenAIProvider(model=model, api_key="test-key", provider_name="deepseek")


class TestProviderThinkingKwargs:
    def _kwargs(self, model: str, scene: str) -> dict:
        token = _set_scene(scene)
        try:
            provider = _provider(model)
            create_kwargs: dict = {}
            provider._apply_thinking_kwargs(create_kwargs, temperature=0.65)
            return create_kwargs
        finally:
            reset_llm_usage_context(token)

    def test_v4_scene_thinking_on(self, _tmp_store) -> None:
        """默认（开）：不发 temperature（V4 思维链模式下会被静默忽略）。"""
        kwargs = self._kwargs("deepseek-v4-pro", "rumination")
        assert "temperature" not in kwargs
        assert "extra_body" not in kwargs

    def test_v4_scene_thinking_off(self, _tmp_store) -> None:
        _save_scene_config({"chat": {"tier": "flash", "thinking": False}})
        kwargs = self._kwargs("deepseek-v4-flash", "chat")
        assert kwargs.get("temperature") == 0.65
        assert kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}

    def test_v4_uncovered_scene_fallback_global_switch(self, _tmp_store, monkeypatch) -> None:
        monkeypatch.setattr(settings, "LLM_THINKING_ENABLED", False)
        kwargs = self._kwargs("deepseek-v4-pro", "team_analysis")
        assert kwargs.get("temperature") == 0.65
        assert kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}

        monkeypatch.setattr(settings, "LLM_THINKING_ENABLED", True)
        kwargs = self._kwargs("deepseek-v4-pro", "team_analysis")
        assert "temperature" not in kwargs and "extra_body" not in kwargs

    def test_non_v4_model_always_temperature_only(self, _tmp_store) -> None:
        """kimi/qwen/gpt 等不支持思维链的模型：只发 temperature，不发 extra_body。"""
        kwargs = self._kwargs("moonshot-v1-8k", "chat")
        assert kwargs.get("temperature") == 0.65
        assert "extra_body" not in kwargs


# ── 路由（super admin 守卫 + 读写/恢复默认）───────────────
def _super_admin_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "SUPER_ADMIN_USER_IDS", "admin-1")
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "admin-1",
        "email": "admin@example.com",
    }
    return TestClient(app)


def _normal_client() -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "user-1",
        "email": "user@example.com",
    }
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


class TestLlmSceneApi:
    def test_get_returns_defaults(self, _tmp_store, monkeypatch) -> None:
        client = _super_admin_client(monkeypatch)
        data = client.get("/api/v1/admin/llm-scene").json()["data"]
        assert data["chat"] == {"tier": "flash", "thinking": True}
        assert data["report"]["tier"] == "pro"

    def test_get_forbidden_for_normal_user(self, _tmp_store) -> None:
        assert _normal_client().get("/api/v1/admin/llm-scene").status_code == 403

    def test_put_then_get(self, _tmp_store, monkeypatch) -> None:
        client = _super_admin_client(monkeypatch)
        resp = client.put(
            "/api/v1/admin/llm-scene",
            json={"config": {
                "chat": {"tier": "pro", "thinking": False},
                "rumination": {"tier": "pro", "thinking": True},
                "report": {"tier": "flash", "thinking": False},
            }},
        )
        assert resp.status_code == 200
        data = client.get("/api/v1/admin/llm-scene").json()["data"]
        assert data["chat"] == {"tier": "pro", "thinking": False}
        assert data["report"] == {"tier": "flash", "thinking": False}

    def test_put_invalid_tier_400(self, _tmp_store, monkeypatch) -> None:
        client = _super_admin_client(monkeypatch)
        resp = client.put(
            "/api/v1/admin/llm-scene",
            json={"config": {"chat": {"tier": "ultra"}}},
        )
        assert resp.status_code == 400

    def test_reset_restores_defaults(self, _tmp_store, monkeypatch) -> None:
        client = _super_admin_client(monkeypatch)
        client.put(
            "/api/v1/admin/llm-scene",
            json={"config": {"chat": {"tier": "pro", "thinking": False}}},
        )
        data = client.post("/api/v1/admin/llm-scene/reset").json()["data"]
        assert data["chat"] == {"tier": "flash", "thinking": True}
        assert client.get("/api/v1/admin/llm-scene").json()["data"] == data


class TestChatAppearanceResetApi:
    def test_reset_writes_defaults(self, _tmp_store, monkeypatch) -> None:
        client = _super_admin_client(monkeypatch)
        client.put(
            "/api/v1/admin/chat-appearance",
            json={"config": {"background": "white"}},
        )
        data = client.post("/api/v1/admin/chat-appearance/reset").json()["data"]
        assert data["background"] == "flow"
        assert data["placement"] == "both"
        assert data["strength"] == 22
        # 落盘校验
        stored = admin_config_mod.get_admin_config("chat_appearance")
        assert stored == data
