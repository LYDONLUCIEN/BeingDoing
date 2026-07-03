"""
激活码归属迁移功能测试:
- ReportRegistry.change_report_user_id
- SimpleActivationManager.transfer_owner
- admin 路由的沙箱码限制
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.report_registry import ReportRegistry
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    _looks_like_debug_activation_code,
)


# ──────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────


def _make_base(tmp_path: Path) -> Path:
    base = tmp_path / "simple"
    (base / "reports").mkdir(parents=True)
    (base / "activations.json").write_text("{}", encoding="utf-8")
    return base


def _add_activation(base: Path, code: str, owner_user_id=None, owner_email=None, report_id=None) -> None:
    f = base / "activations.json"
    data = json.loads(f.read_text(encoding="utf-8") or "{}")
    data[code.upper()] = {
        "code": code.upper(),
        "session_id": "sess-" + code,
        "activation_session_id": "sess-" + code,
        "mode": "combined",
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": "2036-01-01T00:00:00Z",
        "last_activity_at": "2026-01-01T00:00:00Z",
        "status": "active",
        "owner_user_id": owner_user_id,
        "owner_email": owner_email,
        "claimed_at": "2026-01-01T00:00:00Z" if owner_user_id else None,
        "deleted_at": None,
        "purge_after": None,
        "source": None,
        "vip_level": 1,
        "is_sandbox": False,
        "sandbox_root": None,
        "fork_id": None,
        "forked_from_code": None,
        "forked_at": None,
        "forked_by_user_id": None,
        "sandbox_expires_at": None,
        "workspace_kind": None,
        "workspace_root": None,
        "report_id": report_id,
        "report_index_updated_at": None,
    }
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _add_report(base: Path, report_id: str, code: str, user_id: str) -> None:
    d = base / "reports" / report_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "record.json").write_text(json.dumps({
        "report_id": report_id,
        "activation_code": code,
        "user_id": user_id,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "status": "in_progress",
        "final_conclusion": None,
        "steps": {},
    }, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return _make_base(tmp_path)


@pytest.fixture
def manager(base: Path) -> SimpleActivationManager:
    return SimpleActivationManager(base_dir=str(base))


@pytest.fixture
def registry(base: Path) -> ReportRegistry:
    return ReportRegistry(base_dir=str(base))


# ──────────────────────────────────────────────────────────────────
# ReportRegistry.change_report_user_id
# ──────────────────────────────────────────────────────────────────


def test_change_report_user_id_success(registry: ReportRegistry, base: Path) -> None:
    _add_report(base, "r1", "CODE1", "old-user")
    result = registry.change_report_user_id("r1", "new-user", activation_code="CODE1")
    assert result is not None
    assert result["user_id"] == "new-user"
    # 持久化
    rec = json.loads((base / "reports" / "r1" / "record.json").read_text(encoding="utf-8"))
    assert rec["user_id"] == "new-user"


def test_change_report_user_id_idempotent(registry: ReportRegistry, base: Path) -> None:
    _add_report(base, "r1", "CODE1", "user-x")
    result = registry.change_report_user_id("r1", "user-x", activation_code="CODE1")
    # user_id 相同,应直接返回不报错
    assert result["user_id"] == "user-x"


def test_change_report_user_id_missing_report(registry: ReportRegistry) -> None:
    result = registry.change_report_user_id("ghost", "u1", activation_code="CODE1")
    assert result is None


def test_change_report_user_id_empty_args(registry: ReportRegistry) -> None:
    with pytest.raises(ValueError):
        registry.change_report_user_id("", "u1", activation_code="CODE1")
    with pytest.raises(ValueError):
        registry.change_report_user_id("r1", "", activation_code="CODE1")


# ──────────────────────────────────────────────────────────────────
# SimpleActivationManager.transfer_owner
# ──────────────────────────────────────────────────────────────────


def test_transfer_owner_updates_activations_and_report(manager: SimpleActivationManager, base: Path) -> None:
    _add_activation(base, "TRX1", owner_user_id="old-uid", owner_email="old@test.com", report_id="r1")
    _add_report(base, "r1", "TRX1", "old-uid")

    rec = manager.transfer_owner("TRX1", "new-uid", "new@test.com", actor={"user_id": "admin-1", "email": "admin@test.com"})

    assert rec.owner_user_id == "new-uid"
    assert rec.owner_email == "new@test.com"

    # activations.json 已更新
    acts = json.loads((base / "activations.json").read_text(encoding="utf-8"))
    assert acts["TRX1"]["owner_user_id"] == "new-uid"
    assert acts["TRX1"]["owner_email"] == "new@test.com"

    # record.json 的 user_id 也已更新
    rec_data = json.loads((base / "reports" / "r1" / "record.json").read_text(encoding="utf-8"))
    assert rec_data["user_id"] == "new-uid"


def test_transfer_owner_idempotent(manager: SimpleActivationManager, base: Path) -> None:
    _add_activation(base, "TRX2", owner_user_id="same-uid", owner_email="same@test.com", report_id="r1")
    _add_report(base, "r1", "TRX2", "same-uid")

    rec = manager.transfer_owner("TRX2", "same-uid", "same@test.com")
    assert rec.owner_user_id == "same-uid"


def test_transfer_owner_missing_code(manager: SimpleActivationManager) -> None:
    with pytest.raises(ValueError, match="不存在"):
        manager.transfer_owner("GHOST", "new-uid", "new@test.com")


def test_transfer_owner_empty_user_id(manager: SimpleActivationManager, base: Path) -> None:
    _add_activation(base, "TRX3", owner_user_id="old-uid")
    with pytest.raises(ValueError, match="new_user_id"):
        manager.transfer_owner("TRX3", "", None)


def test_transfer_owner_writes_audit_log(manager: SimpleActivationManager, base: Path) -> None:
    _add_activation(base, "TRX4", owner_user_id="old-uid", owner_email="old@test.com", report_id="r1")
    _add_report(base, "r1", "TRX4", "old-uid")

    # 审计日志写入路径依赖全局 get_simple_base_dir(),与 fixture 的 tmp 无关,
    # 因此 patch append_activation_audit 验证调用参数即可。
    with patch("app.utils.activation_audit.append_activation_audit") as mock_audit:
        manager.transfer_owner("TRX4", "new-uid", "new@test.com", actor={"user_id": "admin-x"})

    mock_audit.assert_called_once()
    args, kwargs = mock_audit.call_args
    assert args[0] == "owner_transferred"
    assert args[1] == "TRX4"
    assert kwargs["actor_user_id"] == "admin-x"
    assert kwargs["detail"]["old_owner_user_id"] == "old-uid"
    assert kwargs["detail"]["new_owner_user_id"] == "new-uid"


def test_transfer_owner_report_missing_logs_but_activations_updated(manager: SimpleActivationManager, base: Path) -> None:
    """canonical report 不存在:仅改 activations.json,不抛异常。"""
    _add_activation(base, "TRX5", owner_user_id="old-uid", report_id="r-missing")
    # 不创建 report 目录

    rec = manager.transfer_owner("TRX5", "new-uid", None)
    assert rec.owner_user_id == "new-uid"

    acts = json.loads((base / "activations.json").read_text(encoding="utf-8"))
    assert acts["TRX5"]["owner_user_id"] == "new-uid"


# ──────────────────────────────────────────────────────────────────
# admin 路由沙箱码限制(单元测试 _looks_like_debug_activation_code)
# ──────────────────────────────────────────────────────────────────


def test_looks_like_debug_activation_code_sbx() -> None:
    assert _looks_like_debug_activation_code("SBXABC123") is True
    assert _looks_like_debug_activation_code("sbxabc123") is True  # 大小写不敏感


def test_looks_like_debug_activation_code_adm() -> None:
    assert _looks_like_debug_activation_code("ADM12345") is True


def test_looks_like_debug_activation_code_real_code() -> None:
    assert _looks_like_debug_activation_code("1EPJC91L88") is False
    assert _looks_like_debug_activation_code("FAVNF9UC06") is False


def test_looks_like_debug_activation_code_empty() -> None:
    assert _looks_like_debug_activation_code("") is False
    assert _looks_like_debug_activation_code(None) is False
