"""
漏斗统计服务测试（ADR-0013，事件时间口径）

覆盖：
1. PV/UV 与 auth_active 事件聚合计数
2. 注册人数按时段过滤
3. values 里程碑：首条=试用开聊、第 10 条=完成10轮（全量历史定里程碑，再看落点）
4. 付费口径：paid/granted 计入、refunded 剔除、咨询子集、实收/理论收益
5. 报告审核通过：reviewed_at 优先、祖父豁免回退 created_at、pending 排除
6. 激活码：累计/trial/full 分型/时段内新增
7. 时区边界：UTC 16:30 = Shanghai 次日 00:30，落在次日桶
8. granularity=month 分组
9. 参数校验：end<start、非法 granularity

fixture 风格同 test_consultation.py：内存 SQLite + monkeypatch AsyncSessionLocal / Registry。
"""

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from app.models.analytics import AnalyticsChatTurn, AnalyticsEvent
from app.models.database import Base
from app.models.payment import PaymentOrder
from app.models.user import User
from app.services import analytics_funnel_service as fs_mod
from app.services.analytics_funnel_service import AnalyticsFunnelService
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)

UTC = timezone.utc

# values 轮次：u1 有 10 条（第 1 条 8/1、第 10 条 8/3），u2 只有 2 条
_FAKE_REPORTS = [
    {
        "report_id": "rpt-1",
        "activation_code": "CODE1",
        "user_id": "u1",
        "created_at": "2026-08-01T00:00:00Z",
        "steps": {"values": {"session_ids": ["s-u1"]}},
        # 祖父豁免：无 review_status → approved，回退 created_at（8/1）
    },
    {
        "report_id": "rpt-2",
        "activation_code": "CODE2",
        "user_id": "u2",
        "created_at": "2026-08-02T00:00:00Z",
        "steps": {"values": {"session_ids": ["s-u2"]}},
        "review_status": "approved",
        "reviewed_at": "2026-08-04T10:00:00Z",  # 审核通过时间 8/4
    },
    {
        "report_id": "rpt-3",
        "activation_code": "CODE3",
        "user_id": "u3",
        "created_at": "2026-08-02T00:00:00Z",
        "steps": {},
        "review_status": "pending_review",  # 审核中，不计入
    },
]


class FakeRegistry:
    def list_reports(self):
        return list(_FAKE_REPORTS)


def _dt(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 8, day, hour, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch, tmp_path):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(fs_mod, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(fs_mod, "ReportRegistry", lambda: FakeRegistry())

    # 激活码文件：trial×1（8/1 新建）、full×2（一个 7 月旧码）
    simple_dir = tmp_path / "simple"
    simple_dir.mkdir()
    (simple_dir / "activations.json").write_text(
        json.dumps(
            {
                "CODE1": {"code_type": "trial", "created_at": "2026-08-01T08:00:00Z"},
                "CODE2": {"code_type": "full", "created_at": "2026-08-02T08:00:00Z"},
                "CODE0": {"created_at": "2026-07-15T08:00:00Z"},  # 缺省=full，时段外
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(fs_mod, "get_simple_base_dir", lambda: simple_dir)

    # _resolve_session_users 的兜底（Session 表/logs 目录）在测试中无数据，
    # registry 已覆盖 s-u1/s-u2；其余 session 走 session:{sid} 伪用户
    async with _TestSessionLocal() as db:
        db.add_all(
            [
                User(id="u1", email="a@t.com", username="a", password_hash="x",
                     is_active=True, created_at=_dt(1)),
                User(id="u2", email="b@t.com", username="b", password_hash="x",
                     is_active=True, created_at=_dt(2)),
                User(id="u-old", email="old@t.com", username="old", password_hash="x",
                     is_active=True, created_at=datetime(2026, 7, 1, tzinfo=UTC)),
            ]
        )
        # 事件：PV 3 次（visitor v1×2、v2×1，其中一次在 Shanghai 8/2 凌晨）、
        # auth_active u1×2、u2×1
        db.add_all(
            [
                AnalyticsEvent(event_type="page_view", visitor_id="v1", path="/",
                               created_at=_dt(1, 10)),
                AnalyticsEvent(event_type="page_view", visitor_id="v1", path="/about",
                               created_at=_dt(1, 11)),
                AnalyticsEvent(event_type="page_view", visitor_id="v2", path="/",
                               created_at=datetime(2026, 8, 1, 16, 30, tzinfo=UTC)),  # SH 8/2 00:30
                AnalyticsEvent(event_type="auth_active", user_id="u1", created_at=_dt(2, 9)),
                AnalyticsEvent(event_type="auth_active", user_id="u1", created_at=_dt(2, 10)),
                AnalyticsEvent(event_type="auth_active", user_id="u2", created_at=_dt(3, 9)),
            ]
        )
        # values 轮次：u1 10 条（8/1 一条、8/2 八条、8/3 一条=第10条）、u2 2 条（8/2）
        turns = [AnalyticsChatTurn(session_id="s-u1", dimension="values", created_at=_dt(1, 8))]
        turns += [
            AnalyticsChatTurn(session_id="s-u1", dimension="values", created_at=_dt(2, 8 + i))
            for i in range(8)
        ]
        turns.append(
            AnalyticsChatTurn(session_id="s-u1", dimension="values", created_at=_dt(3, 8))
        )
        turns += [
            AnalyticsChatTurn(session_id="s-u2", dimension="values", created_at=_dt(2, 9)),
            AnalyticsChatTurn(session_id="s-u2", dimension="values_exploration",
                              created_at=_dt(2, 10)),  # full 模式命名也兼容
        ]
        turns.append(
            AnalyticsChatTurn(session_id="s-u1", dimension="strengths", created_at=_dt(4, 8))
        )  # 非 values，不计
        db.add_all(turns)
        # 订单：u1 套餐 granted（原价 6900 实付 1900）、u2 咨询 paid（29800）、
        # u1 延期 refunded（剔除）、pending（剔除）
        db.add_all(
            [
                PaymentOrder(order_no="o1", user_id="u1", product_type="quarterly_package",
                             amount_original=6900, amount_discount=5000, amount_paid=1900,
                             channel="alipay", status="granted", paid_at=_dt(2, 14)),
                PaymentOrder(order_no="o2", user_id="u2", product_type="consultation",
                             amount_original=29800, amount_discount=0, amount_paid=29800,
                             channel="alipay", status="paid", paid_at=_dt(3, 10)),
                PaymentOrder(order_no="o3", user_id="u1", product_type="renewal",
                             amount_original=2000, amount_discount=0, amount_paid=2000,
                             channel="alipay", status="refunded", paid_at=_dt(2, 15),
                             refunded_at=_dt(4, 9)),
                PaymentOrder(order_no="o4", user_id="u2", product_type="annual_package",
                             amount_original=12800, amount_discount=0, amount_paid=12800,
                             channel="alipay", status="pending"),
            ]
        )
        await db.commit()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_funnel_totals():
    """整区间汇总：漏斗各环节 + 日活 + 咨询 + 收益（8/1 ~ 8/5）"""
    data = await AnalyticsFunnelService.get_funnel_stats(date(2026, 8, 1), date(2026, 8, 5))
    f = data["funnel"]
    assert f["pv"] == 3
    assert f["uv"] == 2  # v1、v2
    assert f["registrations"] == 2  # u-old 在 7 月，不计
    assert f["trial_started"] == 2  # u1 首条 8/1、u2 首条 8/2
    assert f["values_10_completed"] == 1  # 仅 u1 满 10 轮（第 10 条 8/3）
    assert f["paid_users"] == 2  # refunded/pending 剔除
    assert f["report_approved_users"] == 2  # rpt-1 祖父豁免(8/1) + rpt-2 reviewed(8/4)

    assert data["daily_active"] == {"total_events": 3, "unique_users": 2}
    assert data["consultation_users"] == 1

    rev = data["revenue"]
    assert rev["actual_cents"] == 1900 + 29800  # 实收（纯利润）：剔除 refunded
    assert rev["theoretical_cents"] == 6900 + 29800  # 理论收益：原价不扣折扣
    assert rev["by_product"]["quarterly_package"] == {
        "orders": 1, "actual_cents": 1900, "theoretical_cents": 6900
    }
    assert rev["by_product"]["consultation"]["orders"] == 1


@pytest.mark.asyncio
async def test_activation_codes():
    data = await AnalyticsFunnelService.get_funnel_stats(date(2026, 8, 1), date(2026, 8, 5))
    codes = data["activation_codes"]
    assert codes == {"total": 3, "trial": 1, "full": 2, "new_in_range": 2}  # CODE0 在 7 月


@pytest.mark.asyncio
async def test_timezone_boundary_bucket():
    """UTC 8/1 16:30 = Shanghai 8/2 00:30：该 PV 应落在 8/2 桶"""
    data = await AnalyticsFunnelService.get_funnel_stats(date(2026, 8, 1), date(2026, 8, 5))
    by_date = {row["date"]: row for row in data["trends"]}
    assert by_date["2026-08-01"]["pv"] == 2
    assert by_date["2026-08-02"]["pv"] == 1


@pytest.mark.asyncio
async def test_trends_per_day():
    data = await AnalyticsFunnelService.get_funnel_stats(date(2026, 8, 1), date(2026, 8, 5))
    by_date = {row["date"]: row for row in data["trends"]}
    assert by_date["2026-08-02"]["active_events"] == 2
    assert by_date["2026-08-02"]["active_users"] == 1  # u1 当天 2 次刷新算 1 人
    assert by_date["2026-08-03"]["values_10_completed"] == 1  # 第 10 条落在 8/3
    assert by_date["2026-08-02"]["actual_cents"] == 1900
    assert by_date["2026-08-03"]["theoretical_cents"] == 29800
    assert by_date["2026-08-04"]["report_approved_users"] == 1  # rpt-2 reviewed_at


@pytest.mark.asyncio
async def test_granularity_month():
    data = await AnalyticsFunnelService.get_funnel_stats(
        date(2026, 7, 1), date(2026, 8, 31), granularity="month"
    )
    by_month = {row["date"]: row for row in data["trends"]}
    assert set(by_month) == {"2026-07", "2026-08"}
    assert by_month["2026-07"]["registrations"] == 1  # u-old
    assert by_month["2026-08"]["pv"] == 3
    assert by_month["2026-08"]["paid_users"] == 2


@pytest.mark.asyncio
async def test_narrow_range_filters_events():
    """只查 8/3 当天：只有落在当天的事件计入"""
    data = await AnalyticsFunnelService.get_funnel_stats(date(2026, 8, 3), date(2026, 8, 3))
    f = data["funnel"]
    assert f["pv"] == 0
    assert f["trial_started"] == 0  # 首条都在 8/1、8/2
    assert f["values_10_completed"] == 1  # 第 10 条正好 8/3
    assert f["paid_users"] == 1  # u2 咨询 8/3
    assert data["revenue"]["actual_cents"] == 29800


@pytest.mark.asyncio
async def test_empty_range_no_crash():
    data = await AnalyticsFunnelService.get_funnel_stats(date(2025, 1, 1), date(2025, 1, 7))
    assert data["funnel"]["pv"] == 0
    assert data["revenue"]["actual_cents"] == 0
    assert len(data["trends"]) == 7


@pytest.mark.asyncio
async def test_param_validation():
    with pytest.raises(ValueError):
        await AnalyticsFunnelService.get_funnel_stats(date(2026, 8, 5), date(2026, 8, 1))
    with pytest.raises(ValueError):
        await AnalyticsFunnelService.get_funnel_stats(
            date(2026, 8, 1), date(2026, 8, 5), granularity="week"
        )
