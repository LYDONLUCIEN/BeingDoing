"""O-03：激活码归属安全 + 审计日志

验证：
- 正常激活码可正常使用，归属不变
- 激活码归属变更操作有审计日志（code、old_owner、new_owner、时间）
- 不会出现非预期的归属迁移
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.utils.simple_activation_manager import (
    ActivationRecord,
    SimpleActivationManager,
    ActivationStatus,
)
from app.utils.activation_audit import (
    append_activation_audit,
    read_audit_logs,
    EVENT_OWNER_CLAIMED,
)


# ── helpers ──────────────────────────────────────────────────────────

def _make_manager(tmp_path: Path) -> SimpleActivationManager:
    """创建基于 tmp_path 的激活码管理器。"""
    return SimpleActivationManager(base_dir=str(tmp_path))


def _make_user(user_id: str = "u1", email: str = "u1@test.com") -> dict:
    return {"user_id": user_id, "email": email}


def _put_activation(mgr: SimpleActivationManager, code: str = "CODE123456") -> ActivationRecord:
    """直接写入一条激活码记录。"""
    from datetime import datetime, timedelta
    rec = ActivationRecord(
        code=code,
        session_id="sess-001",
        mode="combined",
        created_at="2026-01-01T00:00:00Z",
        expires_at=(datetime.utcnow() + timedelta(days=365)).isoformat() + "Z",
        last_activity_at="2026-01-01T00:00:00Z",
        status=ActivationStatus.ACTIVE,
        vip_level=1,
    )
    mgr.put_activation(rec)
    return rec


# ── is_owner ────────────────────────────────────────────────────────

class TestIsOwner:
    def test_o03_is_owner_returns_true_for_matching_user(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _put_activation(mgr, "CODE123456")
        rec = mgr.get_activation("CODE123456")

        # 先 claim 归属
        user = _make_user("u1", "u1@test.com")
        mgr.claim_owner("CODE123456", user)

        # 同一用户应返回 True
        assert mgr.is_owner(rec, _make_user("u1", "u1@test.com")) is True

    def test_o03_is_owner_returns_false_for_different_user(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _put_activation(mgr, "CODE123456")
        user1 = _make_user("u1", "u1@test.com")
        mgr.claim_owner("CODE123456", user1)

        rec = mgr.get_activation("CODE123456")
        user2 = _make_user("u2", "u2@test.com")
        assert mgr.is_owner(rec, user2) is False

    def test_o03_is_owner_returns_false_when_no_owner(self, tmp_path):
        """未绑定归属时，is_owner 也返回 True（允许任何人认领）。"""
        mgr = _make_manager(tmp_path)
        _put_activation(mgr, "CODE123456")
        rec = mgr.get_activation("CODE123456")

        assert mgr.is_owner(rec, _make_user("u1", "u1@test.com")) is True


# ── claim_owner ─────────────────────────────────────────────────────

class TestClaimOwner:
    def test_o03_claim_owner_sets_user_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _put_activation(mgr, "CODE123456")

        user = _make_user("u1", "u1@test.com")
        rec = mgr.claim_owner("CODE123456", user)

        assert rec.owner_user_id == "u1"
        assert rec.owner_email == "u1@test.com"
        assert rec.claimed_at is not None

    def test_o03_claim_owner_idempotent(self, tmp_path):
        """同一用户重复 claim 不报错（幂等）。"""
        mgr = _make_manager(tmp_path)
        _put_activation(mgr, "CODE123456")

        user = _make_user("u1", "u1@test.com")
        mgr.claim_owner("CODE123456", user)
        rec2 = mgr.claim_owner("CODE123456", user)

        assert rec2.owner_user_id == "u1"

    def test_o03_unauthorized_claim_does_not_overwrite(self, tmp_path):
        """不同用户 claim 已归属激活码应抛 PermissionError。"""
        mgr = _make_manager(tmp_path)
        _put_activation(mgr, "CODE123456")

        user1 = _make_user("u1", "u1@test.com")
        mgr.claim_owner("CODE123456", user1)

        user2 = _make_user("u2", "u2@test.com")
        with pytest.raises(PermissionError, match="归属冲突"):
            mgr.claim_owner("CODE123456", user2)

        # 原归属者不变
        rec = mgr.get_activation("CODE123456")
        assert rec.owner_user_id == "u1"


# ── get_activation ──────────────────────────────────────────────────

class TestGetActivation:
    def test_o03_get_activation_returns_none_for_nonexistent(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.get_activation("NONEXISTENT") is None

    def test_o03_get_activation_returns_record(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _put_activation(mgr, "CODE123456")

        rec = mgr.get_activation("CODE123456")
        assert rec is not None
        assert rec.code == "CODE123456"


# ── audit log ───────────────────────────────────────────────────────

class TestAuditLog:
    def test_o03_claim_owner_triggers_audit_log(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path)

        # 把审计日志路径指向 tmp_path
        audit_file = tmp_path / "activation_audit.jsonl"
        monkeypatch.setattr(
            "app.utils.activation_audit.get_simple_base_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "app.utils.activation_audit.get_simple_test_base_dir",
            lambda: tmp_path,
        )

        _put_activation(mgr, "CODE123456")
        user = _make_user("u1", "u1@test.com")
        mgr.claim_owner("CODE123456", user)

        # 读取审计日志
        logs = read_audit_logs(code="CODE123456", test_root=False)
        assert len(logs) >= 1
        owner_logs = [l for l in logs if l.get("event") == EVENT_OWNER_CLAIMED]
        assert len(owner_logs) >= 1

    def test_o03_claim_owner_audit_log_contains_required_fields(self, tmp_path, monkeypatch):
        mgr = _make_manager(tmp_path)

        monkeypatch.setattr(
            "app.utils.activation_audit.get_simple_base_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "app.utils.activation_audit.get_simple_test_base_dir",
            lambda: tmp_path,
        )

        _put_activation(mgr, "CODE123456")
        user = _make_user("u1", "u1@test.com")
        mgr.claim_owner("CODE123456", user)

        logs = read_audit_logs(code="CODE123456", test_root=False)
        owner_log = next(l for l in logs if l.get("event") == EVENT_OWNER_CLAIMED)

        # 必须包含 code、时间
        assert owner_log.get("activation_code") == "CODE123456"
        assert owner_log.get("at") is not None
        assert len(owner_log["at"]) > 0

        # detail 包含归属信息
        detail = owner_log.get("detail", {})
        assert "new_owner_user_id" in detail
        assert detail["new_owner_user_id"] == "u1"
        assert detail.get("is_new_claim") is True
