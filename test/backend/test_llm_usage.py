"""
LLM 用量统计测试（llm_usage_logs，调用粒度，落库时定价）

覆盖：
1. 费率表：8-17 新旧价切换、峰/谷时段价、未知模型 None、别名兜底
2. 峰谷判定：北京时间 9-12 / 14-18 为峰
3. usage 规范化：cache 字段缺失时 miss=prompt 兜底、reasoning 提取
4. record_llm_usage：contextvar 归属、cost 落库定价、无用量不记录、异常不抛出
5. 统计查询：summary（分场景/按天/峰谷）、users 聚合、calls 明细

fixture 风格同 test_analytics_funnel.py：内存 SQLite + monkeypatch AsyncSessionLocal。
"""

from datetime import date, datetime, timezone

import pytest
from app.core.llmapi.usage_context import (
    get_llm_usage_context,
    reset_llm_usage_context,
    set_llm_usage_context,
)
from app.models.database import Base
from app.models.llm_usage import LlmUsageLog
from app.services import llm_usage_service as us_mod
from app.services.llm_usage_service import (
    LlmUsageStatsService,
    extract_usage_numbers,
    record_llm_usage,
)
from app.utils.llm_pricing import compute_cost, is_peak_time, parse_peak_windows
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

UTC = timezone.utc

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _setup_db(monkeypatch):
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(us_mod, "AsyncSessionLocal", _TestSessionLocal)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── 费率与峰谷 ─────────────────────────────────────────────


def test_peak_windows_parse():
    assert parse_peak_windows("09:00-12:00,14:00-18:00") == [(540, 720), (840, 1080)]


def test_is_peak_time():
    # 10:00 SH = 02:00 UTC → 峰；21:00 SH = 13:00 UTC → 谷
    assert is_peak_time(datetime(2026, 8, 17, 2, 0, tzinfo=UTC)) is True
    assert is_peak_time(datetime(2026, 8, 17, 13, 0, tzinfo=UTC)) is False
    # 边界：09:00 起算峰，12:00 起不再是峰
    assert is_peak_time(datetime(2026, 8, 17, 1, 0, tzinfo=UTC)) is True
    assert is_peak_time(datetime(2026, 8, 17, 4, 0, tzinfo=UTC)) is False


def test_compute_cost_old_flat_price():
    # 8-17 前 pro：命中 0.025 / 未命中 3 / 输出 6（无峰谷）
    cost, _ = compute_cost(
        "deepseek-v4-pro", 1_000_000, 1_000_000, 1_000_000, datetime(2026, 8, 16, 2, 0, tzinfo=UTC)
    )
    assert cost == pytest.approx(9.025)


def test_compute_cost_new_peak_offpeak():
    # 8-17 起 pro 峰：0.30 / 9.0 / 27.0
    cost, peak = compute_cost(
        "deepseek-v4-pro", 1_000_000, 1_000_000, 1_000_000, datetime(2026, 8, 17, 2, 0, tzinfo=UTC)
    )
    assert peak is True
    assert cost == pytest.approx(36.3)
    # 谷：0.15 / 4.5 / 13.5
    cost, peak = compute_cost(
        "deepseek-v4-pro", 1_000_000, 1_000_000, 1_000_000, datetime(2026, 8, 17, 13, 0, tzinfo=UTC)
    )
    assert peak is False
    assert cost == pytest.approx(18.15)


def test_compute_cost_flash_and_alias_and_unknown():
    cost, _ = compute_cost(
        "deepseek-v4-flash", 500_000, 500_000, 200_000, datetime(2026, 8, 17, 13, 0, tzinfo=UTC)
    )
    assert cost == pytest.approx(1.675)  # 0.5*0.05 + 0.5*1.5 + 0.2*4.5
    # 旧模型别名按 flash 价兜底
    cost_alias, _ = compute_cost(
        "deepseek-chat", 0, 1_000_000, 0, datetime(2026, 8, 17, 13, 0, tzinfo=UTC)
    )
    assert cost_alias == pytest.approx(1.5)
    # 未知模型 → None（不误计价）
    cost_none, _ = compute_cost(
        "some-unknown-model", 0, 1000, 1000, datetime(2026, 8, 17, 13, 0, tzinfo=UTC)
    )
    assert cost_none is None


# ── usage 规范化 ───────────────────────────────────────────


def test_extract_usage_numbers_with_cache_fields():
    nums = extract_usage_numbers(
        {
            "prompt_tokens": 100,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "completion_tokens": 50,
            "completion_tokens_details": {"reasoning_tokens": 30},
        }
    )
    assert nums == {
        "prompt_tokens": 100,
        "cache_hit_tokens": 80,
        "cache_miss_tokens": 20,
        "completion_tokens": 50,
        "reasoning_tokens": 30,
    }


def test_extract_usage_numbers_without_cache_fields():
    # 无缓存字段（Kimi/Qwen）→ 全部按未命中
    nums = extract_usage_numbers({"prompt_tokens": 100, "completion_tokens": 50})
    assert nums["cache_hit_tokens"] == 0
    assert nums["cache_miss_tokens"] == 100


def test_extract_usage_numbers_empty():
    assert extract_usage_numbers(None)["prompt_tokens"] == 0
    assert extract_usage_numbers({})["completion_tokens"] == 0


# ── contextvar ─────────────────────────────────────────────


def test_usage_context_set_get_reset():
    assert get_llm_usage_context() == {}
    tok = set_llm_usage_context(user_id="u1", session_id="s1", scene="chat")
    ctx = get_llm_usage_context()
    assert ctx["user_id"] == "u1" and ctx["scene"] == "chat"
    reset_llm_usage_context(tok)
    assert get_llm_usage_context() == {}


# ── 记录与查询 ─────────────────────────────────────────────


async def test_record_llm_usage_persists_with_context_and_cost():
    tok = set_llm_usage_context(
        user_id="u1", session_id="sess-1", activation_code="CODE-1", scene="chat"
    )
    await record_llm_usage(
        provider="deepseek",
        model="deepseek-v4-pro",
        usage={
            "prompt_tokens": 1000,
            "prompt_cache_hit_tokens": 800,
            "prompt_cache_miss_tokens": 200,
            "completion_tokens": 100,
        },
    )
    reset_llm_usage_context(tok)

    async with _TestSessionLocal() as db:
        row = (await db.execute(select(LlmUsageLog))).scalar_one()
    assert row.user_id == "u1"
    assert row.session_id == "sess-1"
    assert row.activation_code == "CODE-1"
    assert row.scene == "chat"
    assert row.cache_hit_tokens == 800
    assert row.cost_yuan is not None and row.cost_yuan > 0


async def test_record_llm_usage_skips_empty_usage():
    await record_llm_usage(provider="deepseek", model="deepseek-v4-pro", usage=None)
    await record_llm_usage(provider="deepseek", model="deepseek-v4-pro", usage={})
    async with _TestSessionLocal() as db:
        rows = (await db.execute(select(LlmUsageLog))).scalars().all()
    assert rows == []


async def test_record_llm_usage_without_context_scene_unknown():
    await record_llm_usage(
        provider="deepseek",
        model="deepseek-v4-flash",
        usage={"prompt_tokens": 500, "completion_tokens": 100},
    )
    async with _TestSessionLocal() as db:
        row = (await db.execute(select(LlmUsageLog))).scalar_one()
    assert row.scene == "unknown"
    assert row.user_id is None
    assert row.cache_miss_tokens == 500  # 无缓存字段按未命中兜底


async def _seed():
    tok = set_llm_usage_context(user_id="u1", activation_code="CODE-1", scene="chat")
    await record_llm_usage(
        provider="deepseek",
        model="deepseek-v4-pro",
        usage={"prompt_tokens": 1000, "prompt_cache_hit_tokens": 500,
               "prompt_cache_miss_tokens": 500, "completion_tokens": 200},
    )
    reset_llm_usage_context(tok)
    tok = set_llm_usage_context(user_id="u2", activation_code="CODE-2", scene="report")
    await record_llm_usage(
        provider="deepseek",
        model="deepseek-v4-pro",
        usage={"prompt_tokens": 20000, "prompt_cache_hit_tokens": 15000,
               "prompt_cache_miss_tokens": 5000, "completion_tokens": 3000},
    )
    reset_llm_usage_context(tok)


async def test_summary_aggregates_scene_day_peak():
    await _seed()
    s = await LlmUsageStatsService.get_summary(None, None)
    assert s["total"]["calls"] == 2
    assert s["total"]["cache_hit_rate"] == pytest.approx(15500 / 21000, rel=1e-3)
    scenes = {x["scene"]: x for x in s["by_scene"]}
    assert scenes["report"]["cost_yuan"] > scenes["chat"]["cost_yuan"]
    assert len(s["by_day"]) == 1  # 同一天
    assert "peak" in s and "off_peak" in s


async def test_users_aggregation_and_search():
    await _seed()
    res = await LlmUsageStatsService.get_users(None, None)
    assert res["total"] == 2
    # report 费用更高，排第一
    assert res["records"][0]["user_id"] == "u2"
    assert res["records"][0]["cost_yuan"] > 0
    res_q = await LlmUsageStatsService.get_users(None, None, q="CODE-1")
    assert res_q["total"] == 1
    assert res_q["records"][0]["activation_code"] == "CODE-1"


async def test_calls_detail_filter():
    await _seed()
    res = await LlmUsageStatsService.get_calls(None, None, scene="chat")
    assert res["total"] == 1
    assert res["records"][0]["scene"] == "chat"
    res_u = await LlmUsageStatsService.get_calls(None, None, user_id="u2")
    assert res_u["total"] == 1
    assert res_u["records"][0]["model"] == "deepseek-v4-pro"


async def test_date_range_validation():
    with pytest.raises(ValueError):
        await LlmUsageStatsService.get_summary(date(2026, 8, 10), date(2026, 8, 1))
    with pytest.raises(ValueError):
        await LlmUsageStatsService.get_summary(date(2025, 1, 1), date(2026, 8, 1))
