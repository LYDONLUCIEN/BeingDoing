"""
退款 API 路由测试（2026-10-05）

覆盖路由接线与异常映射（mock 服务层，不打真实 DB/渠道）：
- 旧直接退款接口 410（已废弃）
- 非 super_admin 访问 admin 退款接口 403
- 用户侧：refund-options / refund-requests / withdraw 的 200/400/404
- admin：approve 的 200/400/502、reject 422（缺理由）
"""

from unittest.mock import AsyncMock, patch

import pytest
from app.api.v1.auth import get_current_user
from app.main import app
from app.services.refund_service import RefundNotFoundError, RefundService
from app.services.payment_service import OrderNotFoundError
from fastapi.testclient import TestClient

_USER = {"user_id": "u1", "email": "alice@test.com"}
_ADMIN = {"user_id": "admin-1", "email": "admin@test.com"}


def _client(user: dict) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _as_admin(client: TestClient):
    return patch("app.api.v1.admin_payment.is_super_admin_user", return_value=True)


# ─── 旧接口废弃 ───────────────────────────────────────────────


def test_legacy_direct_refund_endpoint_gone():
    """旧 POST /admin/payment/orders/{id}/refund → 410，指向新流程"""
    client = _client(_ADMIN)
    with _as_admin(client):
        res = client.post("/api/v1/admin/payment/orders/xxx/refund")
    assert res.status_code == 410
    assert "代录" in res.json()["detail"]


def test_admin_refunds_require_super_admin():
    """非 super_admin 访问退款列表 / 审批 → 403"""
    client = _client(_USER)
    assert client.get("/api/v1/admin/payment/refunds").status_code == 403
    assert client.post("/api/v1/admin/payment/refunds/x/approve", json={}).status_code == 403
    assert client.post("/api/v1/admin/payment/refunds/x/reject", json={"note": "r"}).status_code == 403
    assert client.get("/api/v1/admin/payment/refunds/x").status_code == 403


# ─── 用户侧 ───────────────────────────────────────────────────


def test_refund_options_ok():
    with patch.object(
        RefundService,
        "get_refund_options",
        new_callable=AsyncMock,
        return_value={"full_allowed": True, "lines": []},
    ):
        res = _client(_USER).get("/api/v1/payment/orders/o1/refund-options")
    assert res.status_code == 200
    assert res.json()["data"]["full_allowed"] is True


def test_refund_options_not_owner_404():
    with patch.object(
        RefundService,
        "get_refund_options",
        new_callable=AsyncMock,
        side_effect=OrderNotFoundError("订单不存在"),
    ):
        res = _client(_USER).get("/api/v1/payment/orders/o1/refund-options")
    assert res.status_code == 404


def test_create_refund_request_validation():
    """守卫违反 → 400；成功 → 200"""
    with patch.object(
        RefundService,
        "create_refund_request",
        new_callable=AsyncMock,
        side_effect=ValueError("延期订单交付后即已使用，不可退款"),
    ):
        res = _client(_USER).post(
            "/api/v1/payment/orders/o1/refund-requests",
            json={"refund_type": "full", "reason": "x"},
        )
    assert res.status_code == 400
    assert "不可退款" in res.json()["detail"]

    with patch.object(
        RefundService,
        "create_refund_request",
        new_callable=AsyncMock,
        return_value=AsyncMock(refund_no="R1", status="pending_review"),
    ), patch("app.api.v1.payment.refund_to_dict", lambda r: {"refund_no": r.refund_no}):
        res = _client(_USER).post(
            "/api/v1/payment/orders/o1/refund-requests",
            json={"refund_type": "partial", "line_ids": ["l1"], "reason": "x"},
        )
    assert res.status_code == 200


def test_withdraw_not_found_404():
    with patch.object(
        RefundService,
        "withdraw_refund_request",
        new_callable=AsyncMock,
        side_effect=RefundNotFoundError("退款单不存在"),
    ):
        res = _client(_USER).post("/api/v1/payment/refund-requests/r1/withdraw")
    assert res.status_code == 404


def test_withdraw_wrong_state_400():
    with patch.object(
        RefundService,
        "withdraw_refund_request",
        new_callable=AsyncMock,
        side_effect=ValueError("仅待审批的申请可撤回"),
    ):
        res = _client(_USER).post("/api/v1/payment/refund-requests/r1/withdraw")
    assert res.status_code == 400


# ─── admin 侧 ─────────────────────────────────────────────────


def test_admin_approve_ok_and_errors():
    client = _client(_ADMIN)
    with _as_admin(client):
        with patch.object(
            RefundService,
            "approve_refund",
            new_callable=AsyncMock,
            return_value=AsyncMock(refund_no="R1", status="succeeded", approved_amount=100),
        ), patch("app.api.v1.admin_payment.refund_to_dict", lambda r: {"refund_no": r.refund_no}):
            res = client.post(
                "/api/v1/admin/payment/refunds/r1/approve",
                json={"approved_amount": 100, "note": "协商"},
            )
        assert res.status_code == 200

        with patch.object(
            RefundService,
            "approve_refund",
            new_callable=AsyncMock,
            side_effect=ValueError("批准金额与申请金额不一致，必须填写调整理由"),
        ):
            res = client.post("/api/v1/admin/payment/refunds/r1/approve", json={})
        assert res.status_code == 400

        from app.core.payment.base import PaymentChannelError

        with patch.object(
            RefundService,
            "approve_refund",
            new_callable=AsyncMock,
            side_effect=PaymentChannelError("渠道超时"),
        ):
            res = client.post("/api/v1/admin/payment/refunds/r1/approve", json={})
        assert res.status_code == 502


def test_admin_reject_requires_note():
    """驳回缺 note → 422（schema min_length）"""
    client = _client(_ADMIN)
    with _as_admin(client):
        res = client.post("/api/v1/admin/payment/refunds/r1/reject", json={"note": ""})
    assert res.status_code == 422


def test_admin_create_proxy_ok():
    client = _client(_ADMIN)
    with _as_admin(client):
        with patch.object(
            RefundService,
            "admin_create_refund_request",
            new_callable=AsyncMock,
            return_value=AsyncMock(refund_no="R1", status="pending_review", originated="admin"),
        ), patch("app.api.v1.admin_payment.refund_to_dict", lambda r: {"originated": r.originated}):
            res = client.post(
                "/api/v1/admin/payment/refunds",
                json={"order_id": "o1", "refund_type": "full", "reason": "线下协商"},
            )
    assert res.status_code == 200
    assert res.json()["data"]["refund"]["originated"] == "admin"


def test_admin_list_refunds_ok():
    client = _client(_ADMIN)
    with _as_admin(client):
        with patch.object(
            RefundService,
            "admin_list_refunds",
            new_callable=AsyncMock,
            return_value=([{"refund_no": "R1"}], 1),
        ):
            res = client.get("/api/v1/admin/payment/refunds", params={"status": "pending_review"})
    assert res.status_code == 200
    assert res.json()["data"]["total"] == 1
