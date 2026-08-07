"""
Rumination v4 service 单元测试（2026-08-06 版，ADR-0015：用户主导结论卡 + 独立后台判定）

覆盖:
- 数据模型(default_state / new_combo_session / next_combo_id / 旧数据 normalize)
- CRUD(create / find / list / delete / patch / set_status)
- 结论卡用户主导:patch(首填/改即作废/禁清空/分析中拒绝)
- 确认与判定:confirm_conclusion_card / run_balance_judge(mock LLM) / orphan sweep
- 完成门槛:pending_judged_combo_ids / final_selection 双保险
- build_chat_messages(摘要/结论卡注入/reopen_feedback)

已删除协议的测试(tool/chips/双信号/兜底)随 ADR-0015 一并移除。
"""
import asyncio
import json
import pytest
from pathlib import Path

from app.core.llmapi import LLMResponse
from app.services.rumination_v4_service import (
    append_message,
    build_chat_messages,
    confirm_conclusion_card,
    default_state,
    delete_combo,
    find_combo,
    invalidate_balance_analysis,
    is_analyzing,
    list_combos,
    load_v4_state,
    new_combo_session,
    next_combo_id,
    patch_conclusion_card,
    pending_judged_combo_ids,
    run_balance_judge,
    save_v4_state,
    set_active_combo,
    set_combo_status,
    submit_final_selection,
    sweep_orphan_analysis,
    update_final_selection,
)


# ── Mock LLM ───────────────────────────────────────────────────────────
class MockLLM:
    """可编程 mock LLM:按预设回复序列返回;chat_stream 不可用(本文件不需要)。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.last_messages = None

    async def chat(self, messages, temperature=0.7, max_tokens=None, **kwargs) -> LLMResponse:
        self.last_messages = messages
        idx = min(self.call_count, len(self.responses) - 1)
        content = self.responses[idx]
        self.call_count += 1
        if isinstance(content, Exception):
            raise content
        return LLMResponse(content=content, model="mock", finish_reason="stop")


# ── fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def tmp_reports(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def rid() -> str:
    return "test_report_001"


def _make_judged_combo(combo_id="combo_1", balance_found=True):
    """构造一个已确认且判定完成的 combo。"""
    c = new_combo_session(combo_id, "音乐", ["创造表达", "解决问题"])
    c["conclusion_card"] = {
        "hypothesis": "我假设音乐+创造能让我成为独特创作者",
        "balance_found": balance_found,
        "balance_fail_reason": None if balance_found else "投入过大",
        "created_at": "2026-08-06T10:00:00Z",
        "updated_at": "2026-08-06T10:00:00Z",
    }
    c["status"] = "concluded"
    c["balance_analysis"] = {
        "status": "done",
        "balance_found": balance_found,
        "balance_fail_reason": None if balance_found else "投入过大",
        "started_at": "2026-08-06T10:00:00Z",
        "finished_at": "2026-08-06T10:00:01Z",
        "error": None,
    }
    return c


@pytest.fixture
def state_with_two_combos(tmp_reports: Path, rid: str) -> dict:
    """combo_1 已确认+判定完成;combo_2 讨论中(无卡)。"""
    state = default_state()
    c1 = _make_judged_combo()
    c2 = new_combo_session("combo_2", "写作", ["掌控全局"])
    state["combo_sessions"] = [c1, c2]
    state["active_combo_id"] = "combo_2"
    state["main_section"] = "combo_session"
    save_v4_state(tmp_reports, rid, state)
    return state


# ── 数据模型测试 ───────────────────────────────────────────────────────
def test_default_state_schema():
    s = default_state()
    assert s["schema_version"] == 4
    assert s["main_section"] == "matrix"
    assert s["combo_sessions"] == []
    assert s["final_selection"]["submitted"] is False


def test_new_combo_session_defaults():
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    assert c["status"] == "discussing"
    assert c["messages"] == []
    assert c["conclusion_card"] is None
    assert c["balance_analysis"] is None
    assert "fields_collected" not in c  # ADR-0015 废弃


def test_next_combo_id_increments():
    s = default_state()
    assert next_combo_id(s) == "combo_1"
    s["combo_sessions"] = [new_combo_session("combo_1", "a", ["b"])]
    assert next_combo_id(s) == "combo_2"
    s["combo_sessions"].append(new_combo_session("combo_5", "c", ["d"]))
    assert next_combo_id(s) == "combo_6"


def test_normalize_cleans_legacy_fields(tmp_reports, rid):
    """旧数据:fields_collected 删除、conclusion_card 多余字段瘦身、补 balance_analysis。"""
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["fields_collected"] = {"motivation": "x", "hypothesis": "y"}
    c["conclusion_card"] = {
        "hypothesis": "旧假设",
        "motivation": "x",
        "work_purposes": ["发现"],
        "passion_mark": "忍不住想做",
        "timing_mark": "现在",
        "balance_found": True,
        "balance_fail_reason": None,
        "created_at": "t",
        "updated_at": "t",
    }
    c.pop("balance_analysis")
    state["combo_sessions"] = [c]
    save_v4_state(tmp_reports, rid, state)
    loaded = load_v4_state(tmp_reports, rid)
    lc = find_combo(loaded, "combo_1")
    assert "fields_collected" not in lc
    assert lc["balance_analysis"] is None
    card = lc["conclusion_card"]
    assert set(card.keys()) == {
        "hypothesis", "balance_found", "balance_fail_reason", "created_at", "updated_at"
    }
    assert card["hypothesis"] == "旧假设"


# ── CRUD 测试 ──────────────────────────────────────────────────────────
def test_create_combo_sets_active_and_id(tmp_reports, rid):
    from app.services.rumination_v4_service import create_combo
    state, combo = create_combo(tmp_reports, rid, "音乐", ["创造表达", "解决问题"])
    assert combo["combo_id"] == "combo_1"
    assert state["active_combo_id"] == "combo_1"
    state, combo2 = create_combo(tmp_reports, rid, "音乐", ["创造表达"])
    assert combo2["combo_id"] == "combo_2"


def test_delete_combo_removes_and_converges(tmp_reports, rid, state_with_two_combos):
    state = update_final_selection(tmp_reports, rid, ["combo_1"])
    assert state["final_selection"]["selected_combo_ids"] == ["combo_1"]
    state = delete_combo(tmp_reports, rid, "combo_1")
    assert find_combo(state, "combo_1") is None
    assert "combo_1" not in state["final_selection"]["selected_combo_ids"]
    assert state["active_combo_id"] == "combo_2"


def test_delete_nonexistent_raises(tmp_reports, rid, state_with_two_combos):
    with pytest.raises(ValueError, match="combo_id 不存在"):
        delete_combo(tmp_reports, rid, "combo_xxx")


def test_set_active_combo(tmp_reports, rid, state_with_two_combos):
    state = set_active_combo(tmp_reports, rid, "combo_1")
    assert state["active_combo_id"] == "combo_1"


def test_set_combo_status_abandoned_keeps_card(tmp_reports, rid, state_with_two_combos):
    """跳过不清卡,仅置 user_skipped;跳过卡不进终选。"""
    state = set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    c1 = find_combo(state, "combo_1")
    assert c1["status"] == "abandoned"
    assert c1["user_skipped"] is True
    assert c1["conclusion_card"]["hypothesis"]
    with pytest.raises(ValueError):
        update_final_selection(tmp_reports, rid, ["combo_1"])


def test_set_status_concluded_requires_done_analysis(tmp_reports, rid):
    """ADR-0015:concluded 必须有已完成判定,否则拒绝(引导走 confirm 端点)。"""
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["conclusion_card"] = {
        "hypothesis": "假设", "balance_found": None, "balance_fail_reason": None,
        "created_at": "t", "updated_at": "t",
    }
    state["combo_sessions"] = [c]
    save_v4_state(tmp_reports, rid, state)
    with pytest.raises(ValueError, match="confirm"):
        set_combo_status(tmp_reports, rid, "combo_1", "concluded")


def test_reopen_invalidates_analysis(tmp_reports, rid, state_with_two_combos):
    """再聊聊(concluded → discussing):作废旧判定 + 写 reopen_feedback。"""
    state = set_combo_status(tmp_reports, rid, "combo_1", "discussing")
    c1 = find_combo(state, "combo_1")
    assert c1["status"] == "discussing"
    assert c1["balance_analysis"] is None
    assert c1["conclusion_card"]["balance_found"] is None
    assert c1.get("reopen_feedback")


# ── patch 结论卡(用户主导)────────────────────────────────────────────
def test_patch_creates_card_from_scratch(tmp_reports, rid, state_with_two_combos):
    """空卡槽首次填写:从无到有创建卡。"""
    state, card = patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    assert card["hypothesis"] == "我想成为专栏作家"
    assert card["balance_found"] is None
    combo = find_combo(state, "combo_2")
    assert combo["status"] == "discussing"  # 填写 ≠ 确认


def test_patch_rejects_empty_hypothesis(tmp_reports, rid, state_with_two_combos):
    with pytest.raises(ValueError, match="不可清空"):
        patch_conclusion_card(tmp_reports, rid, "combo_1", "   ")


def test_patch_rejects_abandoned(tmp_reports, rid, state_with_two_combos):
    set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    with pytest.raises(ValueError, match="abandoned"):
        patch_conclusion_card(tmp_reports, rid, "combo_1", "x")


def test_patch_change_invalidates_and_reverts_status(tmp_reports, rid, state_with_two_combos):
    """改即作废:清判定;已确认卡退回 discussing。"""
    state, card = patch_conclusion_card(tmp_reports, rid, "combo_1", "改后的假设方向")
    assert card["hypothesis"] == "改后的假设方向"
    assert card["balance_found"] is None
    combo = find_combo(state, "combo_1")
    assert combo["balance_analysis"] is None
    assert combo["status"] == "discussing"


def test_patch_same_text_keeps_analysis(tmp_reports, rid, state_with_two_combos):
    """文本未变:不作废、不退状态。"""
    same = "我假设音乐+创造能让我成为独特创作者"
    state, card = patch_conclusion_card(tmp_reports, rid, "combo_1", same)
    combo = find_combo(state, "combo_1")
    assert combo["balance_analysis"]["status"] == "done"
    assert combo["status"] == "concluded"


def test_patch_rejects_while_analyzing(tmp_reports, rid, state_with_two_combos):
    state = load_v4_state(tmp_reports, rid)
    c2 = find_combo(state, "combo_2")
    c2["balance_analysis"] = {"status": "analyzing", "started_at": "t"}
    save_v4_state(tmp_reports, rid, state)
    with pytest.raises(ValueError, match="分析中"):
        patch_conclusion_card(tmp_reports, rid, "combo_2", "新假设")


# ── 确认与判定 ─────────────────────────────────────────────────────────
def test_confirm_sets_concluded_and_analyzing(tmp_reports, rid, state_with_two_combos):
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    state, combo, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")
    assert combo["status"] == "concluded"
    assert combo["user_skipped"] is False
    analysis = combo["balance_analysis"]
    assert analysis["status"] == "analyzing"
    assert analysis["started_at"] == started_at


def test_confirm_rejects_empty_card(tmp_reports, rid, state_with_two_combos):
    with pytest.raises(ValueError, match="结论卡为空"):
        confirm_conclusion_card(tmp_reports, rid, "combo_2")


def test_confirm_rejects_double_click(tmp_reports, rid, state_with_two_combos):
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    confirm_conclusion_card(tmp_reports, rid, "combo_2")
    with pytest.raises(ValueError, match="请勿重复点击"):
        confirm_conclusion_card(tmp_reports, rid, "combo_2")


@pytest.mark.asyncio
async def test_run_balance_judge_done_true(tmp_reports, rid, state_with_two_combos):
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    _s, _c, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")
    llm = MockLLM(['{"balance_found": true, "balance_fail_reason": null}'])
    analysis = await run_balance_judge(tmp_reports, rid, "combo_2", llm, started_at)
    assert analysis["status"] == "done"
    assert analysis["balance_found"] is True
    assert analysis["balance_fail_reason"] is None
    state = load_v4_state(tmp_reports, rid)
    combo = find_combo(state, "combo_2")
    assert combo["conclusion_card"]["balance_found"] is True


@pytest.mark.asyncio
async def test_run_balance_judge_done_false_with_reason(tmp_reports, rid, state_with_two_combos):
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    _s, _c, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")
    llm = MockLLM(['{"balance_found": false, "balance_fail_reason": "需要大量前期资金投入"}'])
    analysis = await run_balance_judge(tmp_reports, rid, "combo_2", llm, started_at)
    assert analysis["status"] == "done"
    assert analysis["balance_found"] is False
    assert analysis["balance_fail_reason"] == "需要大量前期资金投入"


@pytest.mark.asyncio
async def test_run_balance_judge_non_false_clears_reason(tmp_reports, rid, state_with_two_combos):
    """规范化:非 false 时 fail_reason 强制置 None;非法 balance_found → null。"""
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    _s, _c, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")
    llm = MockLLM(['{"balance_found": "yes", "balance_fail_reason": "扯淡理由"}'])
    analysis = await run_balance_judge(tmp_reports, rid, "combo_2", llm, started_at)
    assert analysis["status"] == "done"
    assert analysis["balance_found"] is None
    assert analysis["balance_fail_reason"] is None


@pytest.mark.asyncio
async def test_run_balance_judge_bad_json_retries_then_done(tmp_reports, rid, state_with_two_combos):
    """坏 JSON → 自动重试 1 次 → 第 2 次成功。"""
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    _s, _c, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")
    llm = MockLLM(["不是JSON", '{"balance_found": true}'])
    analysis = await run_balance_judge(tmp_reports, rid, "combo_2", llm, started_at)
    assert analysis["status"] == "done"
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_run_balance_judge_double_failure(tmp_reports, rid, state_with_two_combos):
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    _s, _c, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")
    llm = MockLLM([RuntimeError("boom"), RuntimeError("boom")])
    analysis = await run_balance_judge(tmp_reports, rid, "combo_2", llm, started_at)
    assert analysis["status"] == "failed"
    assert analysis["error"]
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_run_balance_judge_discards_when_combo_deleted(tmp_reports, rid, state_with_two_combos):
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    _s, _c, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")

    class DeletingLLM(MockLLM):
        async def chat(self, messages, **kw):
            delete_combo(tmp_reports, rid, "combo_2")  # 判定期间用户删了 combo
            return await super().chat(messages, **kw)

    llm = DeletingLLM(['{"balance_found": true}'])
    analysis = await run_balance_judge(tmp_reports, rid, "combo_2", llm, started_at)
    assert analysis["status"] == "failed"
    assert find_combo(load_v4_state(tmp_reports, rid), "combo_2") is None


@pytest.mark.asyncio
async def test_run_balance_judge_uses_summary_when_present(tmp_reports, rid, state_with_two_combos):
    """判定输入:有摘要 = 摘要 + 摘要后消息(超长压缩)。"""
    patch_conclusion_card(tmp_reports, rid, "combo_2", "我想成为专栏作家")
    state = load_v4_state(tmp_reports, rid)
    c2 = find_combo(state, "combo_2")
    c2["summary"] = "早期聊了很多价值观"
    c2["summary_last_round"] = 1
    append_message(state, "combo_2", "user", "第一轮")  # 被摘要覆盖
    # 重新构造:消息顺序 user(第一轮) 在 summary_last_round=1 之前
    save_v4_state(tmp_reports, rid, state)
    _s, _c, started_at = confirm_conclusion_card(tmp_reports, rid, "combo_2")
    llm = MockLLM(['{"balance_found": true}'])
    await run_balance_judge(tmp_reports, rid, "combo_2", llm, started_at)
    prompt_text = llm.last_messages[0].content
    assert "早期对话摘要" in prompt_text
    assert "早期聊了很多价值观" in prompt_text


def test_sweep_orphan_analysis_marks_failed(tmp_reports, rid, state_with_two_combos):
    """analyzing 但无存活任务(进程重启/断连) → failed(可重试)。"""
    state = load_v4_state(tmp_reports, rid)
    c2 = find_combo(state, "combo_2")
    c2["balance_analysis"] = {"status": "analyzing", "started_at": "t", "error": None}
    save_v4_state(tmp_reports, rid, state)
    state = load_v4_state(tmp_reports, rid)
    changed = sweep_orphan_analysis(state, rid)
    assert changed is True
    assert find_combo(state, "combo_2")["balance_analysis"]["status"] == "failed"


def test_sweep_keeps_live_task(tmp_reports, rid, state_with_two_combos):
    """有存活任务的 analyzing 不被 sweep。"""
    from app.services.rumination_v4_service import register_analysis_task, unregister_analysis_task
    state = load_v4_state(tmp_reports, rid)
    c2 = find_combo(state, "combo_2")
    c2["balance_analysis"] = {"status": "analyzing", "started_at": "t"}
    save_v4_state(tmp_reports, rid, state)

    async def _never():
        await asyncio.sleep(100)

    loop = asyncio.new_event_loop()
    task = loop.create_task(_never())
    register_analysis_task(rid, "combo_2", task)
    try:
        state = load_v4_state(tmp_reports, rid)
        changed = sweep_orphan_analysis(state, rid)
        assert changed is False
        assert find_combo(state, "combo_2")["balance_analysis"]["status"] == "analyzing"
    finally:
        task.cancel()
        unregister_analysis_task(rid, "combo_2", task)
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        loop.close()


# ── 完成门槛(ADR-0015)─────────────────────────────────────────────────
def test_pending_judged_combo_ids(tmp_reports, rid, state_with_two_combos):
    """仅已确认卡参与检查;done → 空;analyzing/无记录 → 列出。"""
    state = load_v4_state(tmp_reports, rid)
    assert pending_judged_combo_ids(state) == []  # combo_1 已 done
    c1 = find_combo(state, "combo_1")
    c1["balance_analysis"] = {"status": "analyzing", "started_at": "t"}
    assert pending_judged_combo_ids(state) == ["combo_1"]
    c1["balance_analysis"] = None
    assert pending_judged_combo_ids(state) == ["combo_1"]
    # 跳过卡不参与
    c1["user_skipped"] = True
    assert pending_judged_combo_ids(state) == []


def test_final_selection_blocked_by_pending_analysis(tmp_reports, rid, state_with_two_combos):
    state = load_v4_state(tmp_reports, rid)
    c1 = find_combo(state, "combo_1")
    c1["balance_analysis"] = {"status": "analyzing", "started_at": "t"}
    save_v4_state(tmp_reports, rid, state)
    with pytest.raises(ValueError, match="分析中"):
        update_final_selection(tmp_reports, rid, ["combo_1"])
    with pytest.raises(ValueError, match="分析中"):
        submit_final_selection(tmp_reports, rid)


def test_final_selection_submit_ok_when_all_done(tmp_reports, rid, state_with_two_combos):
    update_final_selection(tmp_reports, rid, ["combo_1"])
    state = submit_final_selection(tmp_reports, rid)
    assert state["final_selection"]["submitted"] is True
    assert state["main_section"] == "end"


def test_final_selection_requires_has_card(tmp_reports, rid, state_with_two_combos):
    with pytest.raises(ValueError):
        update_final_selection(tmp_reports, rid, ["combo_2"])  # 无卡


# ── build_chat_messages ────────────────────────────────────────────────
def test_build_chat_messages_includes_summary_and_recent():
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["summary"] = "用户曾提到喜欢舞台"
    c["messages"] = [
        {"role": "assistant", "content": "你好"},
        {"role": "user", "content": "我想聊音乐"},
        {"role": "assistant", "content": "为什么?"},
        {"role": "user", "content": "我喜欢舞台"},
    ]
    msgs, sys_prompt = build_chat_messages(
        c, "下一句", user_context="【基本资料】\n年龄: 30", values_keywords=["发现"]
    )
    assert msgs[0].role == "system"
    assert "音乐" in msgs[0].content
    assert "基本资料" in msgs[0].content
    assert "发现" in msgs[0].content
    assert any("历史对话摘要" in m.content for m in msgs if m.role == "system")
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "下一句"


def test_build_chat_messages_omits_values_block_when_empty():
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    _, sys_prompt = build_chat_messages(c, "你好", user_context="", values_keywords=None)
    assert "用户在价值观阶段确认的关键词" not in sys_prompt
    _, sys_prompt2 = build_chat_messages(c, "你好", user_context="", values_keywords=["发现"])
    assert "用户在价值观阶段确认的关键词：发现" in sys_prompt2


def test_build_chat_messages_injects_user_card_note():
    """结论卡现状注入(用户本人填写,AI 只读);concluded 时不注入。"""
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["conclusion_card"] = {
        "hypothesis": "我假设音乐+创造能让我成为独特创作者",
        "balance_found": None, "balance_fail_reason": None,
        "created_at": "t", "updated_at": "t",
    }
    msgs, _ = build_chat_messages(c, "再帮我想想")
    notes = [m.content for m in msgs if m.role == "system" and "当前结论卡" in m.content]
    assert notes and "我假设音乐+创造能让我成为独特创作者" in notes[0]
    c["status"] = "concluded"
    msgs, _ = build_chat_messages(c, "好")
    assert not [m for m in msgs if m.role == "system" and "当前结论卡" in m.content]


def test_build_chat_messages_injects_reopen_feedback():
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["conclusion_card"] = {
        "hypothesis": "假设", "balance_found": None, "balance_fail_reason": None,
        "created_at": "t", "updated_at": "t",
    }
    c["reopen_feedback"] = "用户选择「再聊聊」,觉得哪里不合适"
    msgs, _ = build_chat_messages(c, "我觉得还差点意思")
    fb = [m.content for m in msgs if m.role == "system" and "再聊聊" in m.content]
    assert fb


def test_build_chat_messages_skips_empty_messages():
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["messages"] = [
        {"role": "user", "content": "我喜欢舞台"},
        {"role": "assistant", "content": ""},  # 历史空气泡
        {"role": "assistant", "content": "说说看?"},
    ]
    msgs, _ = build_chat_messages(c, "继续说")
    conv = [(m.role, m.content) for m in msgs if m.role in ("user", "assistant")]
    assert all(content.strip() for _, content in conv)


def test_combo_meta_includes_balance_analysis(tmp_reports, rid, state_with_two_combos):
    metas = list_combos(load_v4_state(tmp_reports, rid))
    by_id = {m["combo_id"]: m for m in metas}
    assert by_id["combo_1"]["balance_analysis"]["status"] == "done"
    assert by_id["combo_2"]["balance_analysis"] is None
