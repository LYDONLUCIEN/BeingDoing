"""
Rumination v4 e2e 集成测试（2026-08-06 版，ADR-0015；Mock LLM 跑完整流程）

覆盖场景:
1. 完整成功路径:创建 → 讨论(纯对话,无隐藏协议) → 用户填卡 → 确认+判定(done) → 终选 → 提交
2. 判定失败 → failed → 重试成功
3. 跳过路径:用户手动跳过,卡保留(可逆),不进终选
4. 聊/改即作废:再聊聊 / 修改卡 → 旧判定作废,需重新确认
5. 完成门槛:判定未完成 → 终选/提交被拦
6. 30 轮摘要触发(用 mock 计数)

见 docs/adr/0015-user-driven-card-async-balance-judge.md
"""
import pytest
from pathlib import Path
from typing import AsyncIterator, List

from app.core.llmapi import LLMMessage, LLMResponse
from app.services import rumination_v4_service as svc


# ── Mock LLM Provider ──────────────────────────────────────────────────
class MockLLMProvider:
    """可编程的 mock LLM:按预设的回复序列返回。"""

    def __init__(self, responses: List[str]):
        self.model = "mock-model"
        self.responses = list(responses)
        self.call_count = 0
        self.last_messages = None

    async def chat(self, messages, temperature=0.7, max_tokens=None, **kwargs) -> LLMResponse:
        self.last_messages = messages
        idx = min(self.call_count, len(self.responses) - 1)
        content = self.responses[idx]
        self.call_count += 1
        return LLMResponse(content=content, model=self.model, finish_reason="stop")

    async def chat_stream(self, messages, temperature=0.7, max_tokens=None, **kwargs) -> AsyncIterator[str]:
        idx = min(self.call_count, len(self.responses) - 1)
        content = self.responses[idx]
        self.call_count += 1
        for i in range(0, len(content), 20):
            yield content[i:i + 20]


@pytest.fixture
def tmp_reports(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def rid() -> str:
    return "e2e_report"


async def _confirm_and_judge(tmp_reports, rid, combo_id, llm):
    """确认 + 跑判定,返回最终 balance_analysis。"""
    _s, _c, started_at = svc.confirm_conclusion_card(tmp_reports, rid, combo_id)
    return await svc.run_balance_judge(tmp_reports, rid, combo_id, llm, started_at)


# ── 场景 1:完整成功路径 ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_full_happy_path_user_driven_card(tmp_reports, rid):
    """讨论 → 用户自己填卡 → 确认触发后台判定 → done → 终选 → 提交。"""
    state, combo = svc.create_combo(tmp_reports, rid, "音乐", ["创造表达", "解决问题"])
    combo_id = combo["combo_id"]

    # 模拟几轮纯文本对话(无任何隐藏块)
    state = svc.load_v4_state(tmp_reports, rid)
    svc.append_message(state, combo_id, "user", "我喜欢舞台")
    svc.append_message(state, combo_id, "assistant", "舞台最吸引你的是什么?")
    svc.append_message(state, combo_id, "user", "灯光亮起的那一刻,我觉得自己在创造价值")
    svc.save_v4_state(tmp_reports, rid, state)

    # AI 收尾引导填卡后,用户自己把结论写进卡(PATCH,不绕道 LLM)
    state, card = svc.patch_conclusion_card(tmp_reports, rid, combo_id,
        "成为一名面向都市青年的现场音乐策划人,用小型演出帮人重新连接现场")
    assert card["hypothesis"].startswith("成为一名")
    assert svc.find_combo(state, combo_id)["status"] == "discussing"  # 填写 ≠ 确认

    # 用户点「确认」→ concluded + analyzing → 后台判定 done
    judge_llm = MockLLMProvider(['{"balance_found": true, "balance_fail_reason": null}'])
    analysis = await _confirm_and_judge(tmp_reports, rid, combo_id, judge_llm)
    assert analysis["status"] == "done"
    assert analysis["balance_found"] is True
    # 判定输入包含组合 + hypothesis + 对话
    prompt_text = judge_llm.last_messages[0].content
    assert "音乐" in prompt_text and "创造表达" in prompt_text
    assert "现场音乐策划人" in prompt_text
    assert "灯光亮起的那一刻" in prompt_text

    state = svc.load_v4_state(tmp_reports, rid)
    combo = svc.find_combo(state, combo_id)
    assert combo["status"] == "concluded"
    assert combo["conclusion_card"]["balance_found"] is True
    assert svc.pending_judged_combo_ids(state) == []

    # 终选 + 提交
    svc.update_final_selection(tmp_reports, rid, [combo_id])
    state = svc.submit_final_selection(tmp_reports, rid)
    assert state["final_selection"]["submitted"] is True


# ── 场景 2:判定失败 → 重试 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_judge_failure_then_retry(tmp_reports, rid):
    svc.create_combo(tmp_reports, rid, "写作", ["掌控全局"])
    svc.patch_conclusion_card(tmp_reports, rid, "combo_1", "成为深度报道自由撰稿人")

    bad_llm = MockLLMProvider(["不是JSON", "还不是JSON"])
    analysis = await _confirm_and_judge(tmp_reports, rid, "combo_1", bad_llm)
    assert analysis["status"] == "failed"

    # 重试 = 再走一次 confirm + judge
    good_llm = MockLLMProvider(['{"balance_found": false, "balance_fail_reason": "收入路径不清晰"}'])
    analysis = await _confirm_and_judge(tmp_reports, rid, "combo_1", good_llm)
    assert analysis["status"] == "done"
    assert analysis["balance_found"] is False
    assert analysis["balance_fail_reason"] == "收入路径不清晰"


# ── 场景 3:跳过路径(卡保留、可逆、不进终选)────────────────────────────
@pytest.mark.asyncio
async def test_skip_keeps_card_and_excluded_from_final(tmp_reports, rid):
    svc.create_combo(tmp_reports, rid, "音乐", ["创造表达"])
    svc.patch_conclusion_card(tmp_reports, rid, "combo_1", "成为独立音乐人")
    judge_llm = MockLLMProvider(['{"balance_found": true}'])
    await _confirm_and_judge(tmp_reports, rid, "combo_1", judge_llm)

    state = svc.set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    combo = svc.find_combo(state, "combo_1")
    assert combo["user_skipped"] is True
    assert combo["conclusion_card"]["hypothesis"] == "成为独立音乐人"
    with pytest.raises(ValueError):
        svc.update_final_selection(tmp_reports, rid, ["combo_1"])

    # 可逆:跳过卡可重新确认(confirm 端点清除 user_skipped 并重判)
    state, combo, _started = svc.confirm_conclusion_card(tmp_reports, rid, "combo_1")
    assert combo["user_skipped"] is False
    assert combo["status"] == "concluded"


# ── 场景 4:聊/改即作废 ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_chat_or_edit_invalidates_judgement(tmp_reports, rid):
    svc.create_combo(tmp_reports, rid, "音乐", ["创造表达"])
    svc.patch_conclusion_card(tmp_reports, rid, "combo_1", "成为独立音乐人")
    judge_llm = MockLLMProvider(['{"balance_found": true}'])
    await _confirm_and_judge(tmp_reports, rid, "combo_1", judge_llm)

    # 4a. 再聊聊 → 判定作废 + reopen_feedback
    state = svc.set_combo_status(tmp_reports, rid, "combo_1", "discussing")
    combo = svc.find_combo(state, "combo_1")
    assert combo["balance_analysis"] is None
    assert combo["conclusion_card"]["balance_found"] is None
    assert combo.get("reopen_feedback")

    # 4b. 改卡 → 判定作废;若已确认还会退回 discussing
    judge_llm2 = MockLLMProvider(['{"balance_found": true}'])
    await _confirm_and_judge(tmp_reports, rid, "combo_1", judge_llm2)
    state, card = svc.patch_conclusion_card(tmp_reports, rid, "combo_1", "成为音乐教育者")
    combo = svc.find_combo(state, "combo_1")
    assert combo["balance_analysis"] is None
    assert combo["status"] == "discussing"
    # 作废后已退回 discussing,不再满足「已确认」条件,终选被拦
    with pytest.raises(ValueError, match="未确认结论卡"):
        svc.update_final_selection(tmp_reports, rid, ["combo_1"])


# ── 场景 5:完成门槛 ────────────────────────────────────────────────────
def test_final_gate_blocks_unjudged_concluded(tmp_reports, rid):
    svc.create_combo(tmp_reports, rid, "音乐", ["创造表达"])
    svc.patch_conclusion_card(tmp_reports, rid, "combo_1", "成为独立音乐人")
    # 确认后判定还在 analyzing
    state, combo, _ = svc.confirm_conclusion_card(tmp_reports, rid, "combo_1")
    assert svc.pending_judged_combo_ids(state) == ["combo_1"]
    with pytest.raises(ValueError, match="分析中"):
        svc.update_final_selection(tmp_reports, rid, ["combo_1"])
    with pytest.raises(ValueError, match="分析中"):
        svc.submit_final_selection(tmp_reports, rid)


# ── 场景 6:30 轮滚动摘要 ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_summary_triggered_every_30_rounds(tmp_reports, rid, monkeypatch):
    monkeypatch.setattr(svc, "SUMMARIZE_EVERY_N_ROUNDS", 2)  # 加速触发
    svc.create_combo(tmp_reports, rid, "音乐", ["创造表达"])
    state = svc.load_v4_state(tmp_reports, rid)
    for i in range(2):
        svc.append_message(state, "combo_1", "user", f"第{i+1}轮用户输入")
        svc.append_message(state, "combo_1", "assistant", f"第{i+1}轮回复")
    llm = MockLLMProvider(["这是一份摘要:用户喜欢舞台"])
    new_summary = await svc.maybe_summarize_combo(state, "combo_1", llm)
    assert new_summary == "这是一份摘要:用户喜欢舞台"
    assert state["combo_sessions"][0]["summary_last_round"] == 2
