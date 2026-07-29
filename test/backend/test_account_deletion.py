"""
账户注销 / 恢复 / 到期清除测试

测试场景：
1. 注销确认文字错误 → 400
2. 注销成功 → is_active=False、deleted_at/purge_after 正确、普通 API 401、
   登录返回 account_status=deleted（受限 token，无 refresh token）
3. 恢复流程：发码 → 错误码 400 → 正确码恢复 → is_active=True、可正常访问
4. purge：过期用户被物理清除（DB 行 + 用户目录 + activations.json 条目），
   审计 jsonl 有 purged 记录
5. 超过 purge_after 后自助恢复被显式拒绝（提示联系管理员）
6. admin 恢复：清注销标记 + is_active=True + 审计 by_admin + 通知邮件；
   不受 30 天限制；PATCH status 对已注销用户启用被 400 拦截；
   列表 deleted 筛选三态互斥

使用独立 in-memory SQLite + monkeypatch 替换各模块的 AsyncSessionLocal；
data 目录与激活码管理器指向 tmp_path，邮件 mock，不污染真实数据。
端点通过 httpx ASGITransport 异步调用（不触发 lifespan 后台任务）。
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.main import app
from app.api.v1 import admin as admin_mod
from app.models.database import Base
from app.models.feedback import Feedback
from app.models.refresh_token import RefreshToken
from app.models.user import ProjectExperience, User, UserProfile, WorkHistory
from app.services import account_deletion_service as ads_mod
from app.services import auth_service as as_mod
from app.services import payment_service as ps_mod
from app.services.account_deletion_service import AccountDeletionService
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.utils.simple_activation_manager import ActivationRecord, SimpleActivationManager

# ─── 测试专用引擎 + 会话工厂 ──────────────────────────────────

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

USER_ID = "user-del-1"
EMAIL = "del@test.com"
PASSWORD = "Passw0rd!"
CONFIRM_TEXT = "注销我的账户"


@pytest.fixture(autouse=True)
async def _setup(monkeypatch, tmp_path):
    """每个测试前：建表 + 插测试用户 + monkeypatch DB/目录/邮件"""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # DB：auth_service / account_deletion_service / payment_service 各自的模块级引用
    monkeypatch.setattr(as_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(as_mod, "engine", _test_engine)
    monkeypatch.setattr(ads_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(ps_mod, "AsyncSessionLocal", _TestSessionLocal)

    # data 目录指向 tmp_path（不写真实 data/）
    data_dir = tmp_path / "data"
    (data_dir / "user").mkdir(parents=True)
    simple_dir = tmp_path / "simple"
    simple_dir.mkdir()
    monkeypatch.setattr(ads_mod, "get_project_data_dir", lambda: data_dir)
    monkeypatch.setattr(ads_mod, "get_user_data_dir", lambda: data_dir / "user")
    monkeypatch.setattr(ads_mod, "get_simple_base_dir", lambda: simple_dir)

    # 邮件：mock 发送
    monkeypatch.setattr(
        as_mod.EmailService, "send_account_recovery_code", AsyncMock(return_value=None)
    )

    # 清账号恢复验证码内存
    as_mod._account_recovery_codes.clear()

    # 测试用户
    now = datetime.now(timezone.utc)
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=USER_ID,
                email=EMAIL,
                username="deluser",
                password_hash=AuthService.get_password_hash(PASSWORD),
                is_active=True,
                created_at=now,
            )
        )
        await db.commit()

    yield {"tmp_path": tmp_path, "data_dir": data_dir, "simple_dir": simple_dir}

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _access_token(user_id: str = USER_ID) -> str:
    return AuthService.create_access_token({"sub": user_id, "email": EMAIL})


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _get_user(user_id: str = USER_ID) -> User:
    async with _TestSessionLocal() as db:
        return (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def _delete_account(client: AsyncClient) -> None:
    """通过端点完成注销（供恢复场景复用）"""
    res = await client.post(
        "/api/v1/auth/account/delete",
        json={"confirm_text": CONFIRM_TEXT},
        headers=_auth_headers(_access_token()),
    )
    assert res.status_code == 200


# ─── 场景 1：确认文字错误 → 400 ─────────────────────────────


async def test_delete_wrong_confirm_text_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/account/delete",
            json={"confirm_text": "确定注销"},
            headers=_auth_headers(_access_token()),
        )
    assert res.status_code == 400
    assert "确认文字不正确" in res.json()["detail"]


# ─── 场景 2：注销成功后的状态与登录行为 ──────────────────────


async def test_delete_success_state_and_restricted_login():
    token = _access_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/account/delete",
            json={"confirm_text": CONFIRM_TEXT},
            headers=_auth_headers(token),
        )
        assert res.status_code == 200
        assert res.json()["data"]["purge_after"]

        # DB 状态：is_active=False、deleted_at/purge_after 正确
        user = await _get_user()
        assert user.is_active is False
        assert user.deleted_at is not None
        assert user.deletion_purge_after is not None
        delta = user.deletion_purge_after - user.deleted_at
        assert abs(delta.total_seconds() - settings.ACCOUNT_DELETION_RETENTION_DAYS * 86400) < 2

        # 普通 API 被 401 拦截（旧 access token 失效）
        res_me = await client.get("/api/v1/auth/me", headers=_auth_headers(token))
        assert res_me.status_code == 401

        # 登录返回受限 token + account_status=deleted，且无 refresh token
        res_login = await client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        assert res_login.status_code == 200
        data = res_login.json()["data"]
        assert data["account_status"] == "deleted"
        assert data["token"]
        assert "refresh_token" not in data

        # 受限 token 不能访问普通 API
        res_me2 = await client.get("/api/v1/auth/me", headers=_auth_headers(data["token"]))
        assert res_me2.status_code == 401


# ─── 场景 3：恢复流程 ────────────────────────────────────────


async def test_recovery_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _delete_account(client)

        # 登录拿受限 token
        res_login = await client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        restricted_token = res_login.json()["data"]["token"]

        # 发送恢复验证码
        res_code = await client.post(
            "/api/v1/auth/account/recovery/code",
            headers=_auth_headers(restricted_token),
        )
        assert res_code.status_code == 200
        as_mod.EmailService.send_account_recovery_code.assert_awaited_once()
        record = as_mod._account_recovery_codes.get(EMAIL)
        assert record is not None

        # 错误验证码 → 400
        wrong_code = "000000" if record["code"] != "000000" else "000001"
        res_wrong = await client.post(
            "/api/v1/auth/account/recovery/confirm",
            json={"code": wrong_code},
            headers=_auth_headers(restricted_token),
        )
        assert res_wrong.status_code == 400

        # 正确验证码 → 恢复成功，签发正式 token 对
        res_ok = await client.post(
            "/api/v1/auth/account/recovery/confirm",
            json={"code": record["code"]},
            headers=_auth_headers(restricted_token),
        )
        assert res_ok.status_code == 200
        ok_data = res_ok.json()["data"]
        assert ok_data["token"]

        # DB 状态：is_active=True、注销标记清空
        user = await _get_user()
        assert user.is_active is True
        assert user.deleted_at is None
        assert user.deletion_purge_after is None

        # 新 token 可正常访问
        res_me = await client.get("/api/v1/auth/me", headers=_auth_headers(ok_data["token"]))
        assert res_me.status_code == 200


# ─── 场景 4：到期 purge 物理清除 ─────────────────────────────


async def test_purge_expired_account(_setup):
    data_dir = _setup["data_dir"]
    simple_dir = _setup["simple_dir"]

    purge_user_id = "user-purge-1"
    purge_email = "purge@test.com"
    now = datetime.now(timezone.utc)

    # 到期用户 + 关联 DB 行
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=purge_user_id,
                email=purge_email,
                username="purgeuser",
                password_hash="x",
                is_active=False,
                created_at=now - timedelta(days=40),
                deleted_at=now - timedelta(days=31),
                deletion_purge_after=now - timedelta(days=1),
            )
        )
        db.add(UserProfile(user_id=purge_user_id, gender="male", age=30))
        db.add(WorkHistory(id="wh-1", user_id=purge_user_id, company="测试公司"))
        db.add(ProjectExperience(id="pe-1", work_history_id="wh-1", name="测试项目"))
        db.add(
            RefreshToken(
                user_id=purge_user_id,
                token_hash="hash-purge-1",
                jti="jti-purge-1",
                family_id="fam-purge-1",
                expires_at=now + timedelta(days=1),
            )
        )
        db.add(
            Feedback(
                id="fb-1",
                user_id=purge_user_id,
                user_email=purge_email,
                type="bug",
                content="测试反馈内容",
            )
        )
        await db.commit()

    # 文件：用户目录
    user_dir = data_dir / "user" / purge_user_id
    user_dir.mkdir(parents=True)
    (user_dir / "basic_info.json").write_text("{}", encoding="utf-8")

    # 文件：名下激活码 + 会话目录；另有一个属于别人的码不应被动
    mgr = SimpleActivationManager(base_dir=str(simple_dir))
    mgr.put_activation(
        ActivationRecord(
            code="OWNEDCODE1",
            session_id="sess-purge-1",
            mode="values",
            created_at=now.isoformat(),
            expires_at=None,
            last_activity_at=now.isoformat(),
            owner_user_id=purge_user_id,
            owner_email=purge_email,
        )
    )
    mgr.put_activation(
        ActivationRecord(
            code="OTHERCODE1",
            session_id="sess-other-1",
            mode="values",
            created_at=now.isoformat(),
            expires_at=None,
            last_activity_at=now.isoformat(),
            owner_user_id="someone-else",
            owner_email="other@test.com",
        )
    )
    sess_dir = simple_dir / "sess-purge-1"
    sess_dir.mkdir()
    (sess_dir / "chat.jsonl").write_text("", encoding="utf-8")
    other_sess_dir = simple_dir / "sess-other-1"
    other_sess_dir.mkdir()

    # 文件：名下报告目录
    report_dir = simple_dir / "reports" / "report-purge-1"
    report_dir.mkdir(parents=True)
    (report_dir / "record.json").write_text(
        json.dumps({"user_id": purge_user_id, "activation_code": "OWNEDCODE1"}),
        encoding="utf-8",
    )

    # 执行 purge
    purged = await AccountDeletionService.purge_expired_accounts()
    assert purged == 1

    # DB 行物理清除
    async with _TestSessionLocal() as db:
        assert (
            await db.execute(select(User).where(User.id == purge_user_id))
        ).scalar_one_or_none() is None
        assert (
            await db.execute(select(UserProfile).where(UserProfile.user_id == purge_user_id))
        ).scalar_one_or_none() is None
        assert (
            await db.execute(select(WorkHistory).where(WorkHistory.id == "wh-1"))
        ).scalar_one_or_none() is None
        assert (
            await db.execute(select(ProjectExperience).where(ProjectExperience.id == "pe-1"))
        ).scalar_one_or_none() is None
        assert (
            await db.execute(select(RefreshToken).where(RefreshToken.user_id == purge_user_id))
        ).scalar_one_or_none() is None
        # feedbacks 行保留但 user_email 已匿名化清空
        fb = (await db.execute(select(Feedback).where(Feedback.id == "fb-1"))).scalar_one_or_none()
        assert fb is not None
        assert fb.user_email == ""

    # 文件清除
    assert not user_dir.exists()
    assert not sess_dir.exists()
    assert not report_dir.exists()
    # 别人的码与会话目录不动
    assert "OWNEDCODE1" not in mgr.list_activations()
    assert "OTHERCODE1" in mgr.list_activations()
    assert other_sess_dir.exists()

    # 审计 jsonl 有 purged 记录（含 email）
    audit_file = data_dir / "account_deletion_audit.jsonl"
    assert audit_file.is_file()
    events = [
        json.loads(line)
        for line in audit_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    purged_events = [e for e in events if e.get("event") == "purged"]
    assert len(purged_events) == 1
    assert purged_events[0]["user_id"] == purge_user_id
    assert purged_events[0]["email"] == purge_email


# ─── 场景 5：超过 purge_after 自助恢复被显式拒绝 ────────────────


async def test_recovery_expired_purge_after_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _delete_account(client)

        # 手动把 purge_after 改到过去（模拟 purge 任务尚未跑到的过期账户）
        async with _TestSessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == USER_ID))).scalar_one()
            user.deletion_purge_after = datetime.now(timezone.utc) - timedelta(days=1)
            await db.commit()

        # 登录仍可拿受限 token（login 不卡恢复期）
        res_login = await client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        restricted_token = res_login.json()["data"]["token"]

        await client.post(
            "/api/v1/auth/account/recovery/code",
            headers=_auth_headers(restricted_token),
        )
        record = as_mod._account_recovery_codes.get(EMAIL)
        assert record is not None

        # 显式 30 天判断：拒绝自助恢复并提示联系管理员
        res = await client.post(
            "/api/v1/auth/account/recovery/confirm",
            json={"code": record["code"]},
            headers=_auth_headers(restricted_token),
        )
        assert res.status_code == 400
        assert "已超过账户恢复期" in res.json()["detail"]

        # 状态未被改动
        user = await _get_user()
        assert user.deleted_at is not None
        assert user.is_active is False


# ─── 场景 6：admin 恢复 / PATCH 拦截 / 列表筛选 ─────────────────

ADMIN_ID = "admin-1"
ADMIN_EMAIL = "admin@test.com"


async def _make_admin(monkeypatch) -> str:
    """创建超管用户并返回其 access token"""
    monkeypatch.setattr(settings, "SUPER_ADMIN_USER_IDS", ADMIN_ID)
    # admin 路由使用自己的模块级 AsyncSessionLocal
    monkeypatch.setattr(admin_mod, "AsyncSessionLocal", _TestSessionLocal)
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id=ADMIN_ID,
                email=ADMIN_EMAIL,
                username="admin",
                password_hash="x",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
    return AuthService.create_access_token({"sub": ADMIN_ID, "email": ADMIN_EMAIL})


async def test_admin_restore_deletion(monkeypatch, _setup):
    data_dir = _setup["data_dir"]
    admin_token = await _make_admin(monkeypatch)
    notify_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(EmailService, "send_account_restored_notice", notify_mock)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _delete_account(client)

        # 未注销状态恢复 → 400（先对正常 admin 用户验证）
        res = await client.post(
            f"/api/v1/admin/users/{ADMIN_ID}/restore-deletion",
            json={"notify": False},
            headers=_auth_headers(admin_token),
        )
        assert res.status_code == 400

        # 非超管 → 403（用一个正常的活跃用户 token）
        async with _TestSessionLocal() as db:
            db.add(
                User(
                    id="user-normal-1",
                    email="normal@test.com",
                    username="normal",
                    password_hash="x",
                    is_active=True,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        normal_token = AuthService.create_access_token(
            {"sub": "user-normal-1", "email": "normal@test.com"}
        )
        res = await client.post(
            f"/api/v1/admin/users/{USER_ID}/restore-deletion",
            json={"notify": True},
            headers=_auth_headers(normal_token),
        )
        assert res.status_code == 403

        # 超管恢复（即使 purge_after 已过期也可救回）
        async with _TestSessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == USER_ID))).scalar_one()
            user.deletion_purge_after = datetime.now(timezone.utc) - timedelta(days=1)
            await db.commit()

        res = await client.post(
            f"/api/v1/admin/users/{USER_ID}/restore-deletion",
            json={"notify": True},
            headers=_auth_headers(admin_token),
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["is_active"] is True
        assert data["notified"] is True
        notify_mock.assert_awaited_once_with(EMAIL)

        # DB 状态还原
        user = await _get_user()
        assert user.is_active is True
        assert user.deleted_at is None
        assert user.deletion_purge_after is None

        # 审计含 by_admin 标记
        audit_file = data_dir / "account_deletion_audit.jsonl"
        events = [
            json.loads(line)
            for line in audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        recovered = [e for e in events if e.get("event") == "recovered"]
        assert len(recovered) == 1
        assert recovered[0]["detail"]["by_admin"] is True
        assert recovered[0]["detail"]["admin_id"] == ADMIN_ID


async def test_admin_patch_status_enable_deleted_user_400(monkeypatch):
    admin_token = await _make_admin(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _delete_account(client)

        # 对已注销用户直接「启用」→ 400 拦截引导
        res = await client.patch(
            f"/api/v1/admin/users/{USER_ID}/status",
            json={"is_active": True},
            headers=_auth_headers(admin_token),
        )
        assert res.status_code == 400
        assert "恢复注销账户" in res.json()["detail"]

        # 状态未被改动
        user = await _get_user()
        assert user.is_active is False
        assert user.deleted_at is not None


async def test_admin_list_users_deleted_filter(monkeypatch, _setup):
    simple_dir = _setup["simple_dir"]
    admin_token = await _make_admin(monkeypatch)
    # 避免 list 端点读取真实激活码目录
    monkeypatch.setattr(
        admin_mod,
        "SimpleActivationManager",
        lambda: SimpleActivationManager(base_dir=str(simple_dir)),
    )

    # 再建一个「admin 禁用但未注销」用户
    async with _TestSessionLocal() as db:
        db.add(
            User(
                id="user-disabled-1",
                email="disabled@test.com",
                username="disabled",
                password_hash="x",
                is_active=False,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _delete_account(client)

        headers = _auth_headers(admin_token)

        # deleted=true → 只有已注销用户
        res = await client.get("/api/v1/admin/users?deleted=true", headers=headers)
        assert res.status_code == 200
        ids = {it["user_id"] for it in res.json()["data"]["items"]}
        assert USER_ID in ids
        assert "user-disabled-1" not in ids
        assert ADMIN_ID not in ids

        # is_active=false + deleted=false → 只有 admin 禁用用户（三态互斥）
        res = await client.get(
            "/api/v1/admin/users?is_active=false&deleted=false", headers=headers
        )
        assert res.status_code == 200
        ids = {it["user_id"] for it in res.json()["data"]["items"]}
        assert "user-disabled-1" in ids
        assert USER_ID not in ids


# ─── 场景 7：SMTP 550 拒收 → 400 友好提示（不再 500） ───────────


async def test_recovery_code_smtp_refused_friendly_400():
    import smtplib

    # fixture 里的 mock 改为抛 550 拒收（假邮箱场景）
    as_mod.EmailService.send_account_recovery_code.side_effect = (
        smtplib.SMTPRecipientsRefused({EMAIL: (550, b"Mailbox not found")})
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _delete_account(client)
        res_login = await client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
        )
        restricted_token = res_login.json()["data"]["token"]

        res = await client.post(
            "/api/v1/auth/account/recovery/code",
            headers=_auth_headers(restricted_token),
        )
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert "拒收" in detail
        assert "联系管理员" in detail

        # 未写入验证码记录（发送失败不留存）
        assert as_mod._account_recovery_codes.get(EMAIL) is None
