"""
Rumination v4 e2e 集成测试(用 Mock LLM,跑完整流程)

覆盖场景:
1. 完整成功路径:矩阵 → 创建 → 讨论 → 出卡(双信号都全)→ 确认 → 第 8 步选择 → 提交
2. 兜底路径:LLM 忘了输出 <<CONCLUSION_READY>>(只有 visible 话术)→ 触发 fallback
3. 跳过路径:用户手动跳过,卡保留(可逆),不进终选
4. 多优势 hypothesis 分字典形态
5. 30 轮摘要触发(用 mock 计数)

见 wiki/开发文档/0707-tag1.6.0.md
"""
import json
import pytest
from pathlib import Path
from typing import AsyncIterator, List
from unittest.mock import AsyncMock, MagicMock

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
        # 简单按字 chunk
        for i in range(0, len(content), 20):
            yield content[i:i + 20]


@pytest.fixture
def tmp_reports(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def rid() -> str:
    return "e2e_report"


# ── 场景 1:完整成功路径(双信号齐全)──────────────────────────────────
@pytest.mark.asyncio
async def test_full_happy_path_with_dual_signals(tmp_reports, rid, monkeypatch):
    """LLM 完整输出双信号 → 正常出卡 → 用户确认 → 第 8 步。"""
    # 创建 combo
    state, combo = svc.create_combo(tmp_reports, rid, "音乐", ["创造表达", "解决问题"])
    combo_id = combo["combo_id"]

    # Mock LLM 第一轮:收集 motivation
    llm = MockLLMProvider([
        # 第一轮回复:更新 motivation
        "能告诉我具体是什么吸引你吗?\n```tool\n"
        '{"tool":"update_field","field":"motivation","value":"我喜欢舞台的光"}\n```',
        # 第二轮回复:出结论卡(双信号齐全)
        "太好了!结合你说的,\n<<CONCLUSION_READY>>\n"
        "```tool\n"
        '{"tool":"save_conclusion_card","fields":{"hypothesis":"音乐+创造能让我成为独特创作者","motivation":"我喜欢舞台的光","work_purposes":["发现","成长"],"passion_mark":"忍不住想做","timing_mark":"现在","balance_found":true}}\n```\n'
        "- 方向:音乐+创造,成为独特创作者\n- 它与你的热爱和优势都搭\n我已经把这次探索整理成了结论卡,你看看有没有要调整的",
    ])

    # 模拟用户第一轮
    state = svc.load_v4_state(tmp_reports, rid)
    svc.append_message(state, combo_id, "user", "我喜欢舞台")
    svc.save_v4_state(tmp_reports, rid, state)

    msgs, _ = svc.build_chat_messages(find_combo(state, combo_id), "我喜欢舞台")
    resp = await llm.chat(msgs)
    visible, tools = svc.parse_tool_blocks(resp.content)
    signals = svc.detect_conclusion_signals(resp.content)
    for tc in tools:
        svc.apply_tool_call(state, combo_id, tc)
    svc.append_message(state, combo_id, "assistant", visible)
    svc.save_v4_state(tmp_reports, rid, state)

    # 第一轮后:motivation 已收集,未出卡
    c1 = find_combo(state, combo_id)
    assert c1["fields_collected"]["motivation"] == "我喜欢舞台的光"
    assert c1["conclusion_card"] is None

    # 模拟用户第二轮
    svc.append_message(state, combo_id, "user", "是的")
    svc.save_v4_state(tmp_reports, rid, state)
    msgs, _ = svc.build_chat_messages(find_combo(state, combo_id), "是的")
    resp = await llm.chat(msgs)
    visible, tools = svc.parse_tool_blocks(resp.content)
    signals = svc.detect_conclusion_signals(resp.content)
    card_event = None
    for tc in tools:
        card, err = svc.apply_tool_call(state, combo_id, tc)
        if card:
            card_event = card
    svc.append_message(state, combo_id, "assistant", visible)
    svc.save_v4_state(tmp_reports, rid, state)

    # 第二轮后:出卡(草案,不锁定),双信号齐全,无 fallback
    assert signals["hidden"] is True
    assert signals["visible"] is True
    assert card_event is not None
    assert card_event["hypothesis"] == "音乐+创造能让我成为独特创作者"
    assert card_event["balance_found"] is True
    c2 = find_combo(state, combo_id)
    # 2026-07-27 交互口径:出卡不锁,用户确认才置 concluded
    assert c2["status"] == "discussing"
    assert c2["conclusion_card"]["hypothesis"].startswith("音乐+创造")

    # 用户确认 → concluded 进终选
    state = svc.set_combo_status(tmp_reports, rid, combo_id, "concluded")
    assert find_combo(state, combo_id)["status"] == "concluded"
    # 第 8 步选择 + 提交
    state = svc.update_final_selection(tmp_reports, rid, [combo_id])
    state = svc.submit_final_selection(tmp_reports, rid)
    assert state["final_selection"]["submitted"] is True
    assert state["main_section"] == "end"


# ── 场景 2:兜底(LLM 忘了 <<CONCLUSION_READY>>)───────────────────────
@pytest.mark.asyncio
async def test_fallback_when_llm_forgets_hidden_marker(tmp_reports, rid):
    """LLM 输出了 visible 话术但忘了 hidden 标记 → fallback 生成结论卡。"""
    state, combo = svc.create_combo(tmp_reports, rid, "写作", ["掌控全局"])
    combo_id = combo["combo_id"]

    # 主 LLM:只输出了 visible,没输出 hidden
    main_llm = MockLLMProvider([
        "好的,我们继续。\n```tool\n"
        '{"tool":"update_field","field":"hypothesis","value":"我假设写作能让我表达自己"}\n```',
        "很好,我已经把这次探索整理成了结论卡,你确认一下",  # 注意:无 <<CONCLUSION_READY>>
    ])
    # 兜底 LLM(独立 conclusion prompt):返回 JSON(含 balance 字段)
    fallback_llm = MockLLMProvider([
        '{"hypothesis":"我假设写作+掌控能让我成为有影响力的作者","motivation":"表达欲","work_purposes":["成长"],"passion_mark":"忍不住想做","timing_mark":"未来","balance_found":false,"balance_fail_reason":"当下投入难启动"}'
    ])

    # 第一轮:收集 hypothesis
    svc.append_message(state, combo_id, "user", "我想写作")
    svc.save_v4_state(tmp_reports, rid, state)
    msgs, _ = svc.build_chat_messages(find_combo(state, combo_id), "我想写作")
    resp = await main_llm.chat(msgs)
    visible, tools = svc.parse_tool_blocks(resp.content)
    for tc in tools:
        svc.apply_tool_call(state, combo_id, tc)
    svc.append_message(state, combo_id, "assistant", visible)
    svc.save_v4_state(tmp_reports, rid, state)

    # 第二轮:有 visible 话术,无 hidden 标记
    svc.append_message(state, combo_id, "user", "继续")
    svc.save_v4_state(tmp_reports, rid, state)
    msgs, _ = svc.build_chat_messages(find_combo(state, combo_id), "继续")
    resp = await main_llm.chat(msgs)
    signals = svc.detect_conclusion_signals(resp.content)
    visible, tools = svc.parse_tool_blocks(resp.content)
    for tc in tools:
        svc.apply_tool_call(state, combo_id, tc)
    svc.append_message(state, combo_id, "assistant", visible)
    svc.save_v4_state(tmp_reports, rid, state)

    # 触发兜底(主对话无 save_conclusion_card tool call)
    assert signals["visible"] is True
    assert signals["hidden"] is False
    assert not tools  # 没 save tool
    # 检查主对话确实没出卡
    assert find_combo(state, combo_id)["conclusion_card"] is None

    # 调兜底
    fallback_card = await svc.fallback_generate_conclusion(
        find_combo(state, combo_id), fallback_llm
    )
    assert fallback_card is not None
    assert fallback_card["hypothesis"].startswith("我假设写作")
    assert fallback_card["balance_found"] is False
    assert fallback_card["balance_fail_reason"] == "当下投入难启动"
    # 写入
    apply_tc = {"tool": "save_conclusion_card", "fields": {
        "hypothesis": fallback_card["hypothesis"],
    }}
    card, err = svc.apply_tool_call(state, combo_id, apply_tc)
    assert err is None
    assert card["hypothesis"].startswith("我假设写作")


# ── 场景 3:用户跳过(卡保留+可逆)──────────────────────────────────────
def test_user_skips_keeps_card(tmp_reports, rid):
    """实施口径 §1-新4:跳过不清卡,置 user_skipped;跳过的卡不进终选。"""
    state, combo = svc.create_combo(tmp_reports, rid, "教学", ["解决问题"])
    combo_id = combo["combo_id"]
    # 先出一张卡再跳过
    svc.apply_tool_call(state, combo_id, {
        "tool": "save_conclusion_card", "fields": {"hypothesis": "我假设教学能让我影响更多人"}
    })
    svc.save_v4_state(tmp_reports, rid, state)
    # 跳过
    state = svc.set_combo_status(tmp_reports, rid, combo_id, "abandoned")
    c = find_combo(state, combo_id)
    assert c["status"] == "abandoned"
    assert c["user_skipped"] is True
    assert c["conclusion_card"] is not None  # 卡内容保留
    # abandoned 不能进 final_selection
    with pytest.raises(ValueError):
        svc.update_final_selection(tmp_reports, rid, [combo_id])
    # 跳过可逆:恢复 concluded 后可进终选
    state = svc.set_combo_status(tmp_reports, rid, combo_id, "concluded")
    assert find_combo(state, combo_id)["user_skipped"] is False
    state = svc.update_final_selection(tmp_reports, rid, [combo_id])
    assert state["final_selection"]["selected_combo_ids"] == [combo_id]


# ── 场景 4:多优势 hypothesis 分字典 ────────────────────────────────────
def test_multi_strength_dict_hypothesis(tmp_reports, rid):
    state, combo = svc.create_combo(tmp_reports, rid, "音乐", ["创造表达", "解决问题", "掌控全局"])
    combo_id = combo["combo_id"]
    hyp_dict = {
        "创造表达": "让我成为创作者",
        "解决问题": "让我成为修复者",
        "掌控全局": "让我成为领导者",
    }
    card, err = svc.apply_tool_call(state, combo_id, {
        "tool": "save_conclusion_card", "fields": {"hypothesis": hyp_dict}
    })
    assert err is None
    assert isinstance(card["hypothesis"], dict)
    assert card["hypothesis"]["创造表达"] == "让我成为创作者"


# ── 场景 5:30 轮摘要触发 ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_summary_triggered_at_30_rounds(tmp_reports, rid):
    from app.services.rumination_v4_service import SUMMARIZE_EVERY_N_ROUNDS
    state, combo = svc.create_combo(tmp_reports, rid, "音乐", ["创造表达"])
    combo_id = combo["combo_id"]
    # 塞 30 条 user 消息
    state = svc.load_v4_state(tmp_reports, rid)
    for i in range(SUMMARIZE_EVERY_N_ROUNDS):
        svc.append_message(state, combo_id, "user", f"第 {i+1} 轮用户输入")
        svc.append_message(state, combo_id, "assistant", f"第 {i+1} 轮回复")
    svc.save_v4_state(tmp_reports, rid, state)

    summarizer_llm = MockLLMProvider(["这是用户与引导师关于音乐+创造的对话摘要。用户多次提到舞台与表达欲。"])

    state = svc.load_v4_state(tmp_reports, rid)
    new_summary = await svc.maybe_summarize_combo(state, combo_id, summarizer_llm)
    assert new_summary is not None
    assert "舞台" in new_summary or "音乐" in new_summary
    combo_obj = find_combo(state, combo_id)
    assert combo_obj["summary"] == new_summary
    assert combo_obj["summary_last_round"] == SUMMARIZE_EVERY_N_ROUNDS


# ── 场景 6:SSE 流式隐藏块过滤(回归:标记/tool 块泄漏到聊天气泡)────────
def test_stream_hidden_blocks_never_leak_across_chunks():
    """combo-chat SSE 流式阶段:<<CONCLUSION_READY>> / ```tool 块 / [STEP3_HYP_JSON] 块
    即使被流式 chunk 任意拆开,也不得出现在推给前端的 chunk 增量里。"""
    from app.services.rumination_v4_service import STREAM_HIDDEN_BLOCK_MARKERS
    # 直接按文件路径加载,避免触发 simple_chat 包 __init__ 的连锁导入
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "stream_utils",
        Path(__file__).resolve().parents[2] / "src/backend/app/api/v1/simple_chat/stream_utils.py",
    )
    _su = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_su)
    build_stream_hidden_block_filter = _su.build_stream_hidden_block_filter

    visible_head = "我明白了。这件事的核心回报是自我成长和认知突破。\n\n"
    visible_tail = "我已经把这次探索整理成了结论卡,你可以看看有没有需要调整的地方。"
    hidden = (
        "<<CONCLUSION_READY>>\n```tool\n"
        '{"tool":"save_conclusion_card","fields":{"hypothesis":"做一个持续性的深度人物观察项目","balance_found":true}}\n```'
    )
    full = visible_head + visible_tail + "\n\n" + hidden

    # 多种切块粒度都必须零泄漏(1 字符粒度最苛刻,模拟标记被拆散)
    for step in (1, 3, 5, 20):
        f = build_stream_hidden_block_filter(block_markers=STREAM_HIDDEN_BLOCK_MARKERS)
        out = ""
        for i in range(0, len(full), step):
            out += f(full[: i + step])
        assert "<<CONCLUSION_READY>>" not in out
        assert "save_conclusion_card" not in out
        assert "```tool" not in out
        assert out == visible_head + visible_tail + "\n\n"

    # chips 隐藏块同样不泄漏
    t = "选一个方向:\n[STEP3_HYP_JSON]{" + '"candidates":["abc"]' + "}[/STEP3_HYP_JSON]"
    f = build_stream_hidden_block_filter(block_markers=STREAM_HIDDEN_BLOCK_MARKERS)
    out = ""
    for i in range(0, len(t), 2):
        out += f(t[: i + 2])
    assert "STEP3_HYP_JSON" not in out
    assert "candidates" not in out
    assert out.startswith("选一个方向:")


# ── 辅助 ───────────────────────────────────────────────────────────────
def find_combo(state, cid):
    return svc.find_combo(state, cid)
