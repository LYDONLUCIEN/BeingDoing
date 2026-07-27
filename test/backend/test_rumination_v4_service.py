"""
Rumination v4 service 单元测试

覆盖:
- 数据模型(default_state / new_combo_session / next_combo_id)
- CRUD(create / find / list / delete / patch / set_status)
- tool call 协议(parse_tool_blocks / apply_tool_call / detect_conclusion_signals)
- final_selection(校验 1-3 + has_card)
- 多优势 hypothesis(整体 vs 分优势字典)
- 兜底前置条件(hypothesis 必填校验)

见 wiki/开发文档/0707-tag1.6.0.md
"""
import json
import pytest
from pathlib import Path

from app.services.rumination_v4_service import (
    CONCLUSION_READY_MARKER,
    apply_tool_call,
    append_message,
    build_chat_messages,
    default_state,
    delete_combo,
    detect_conclusion_signals,
    extract_hyp_candidates,
    fallback_generate_conclusion,
    find_combo,
    list_combos,
    load_v4_state,
    new_combo_session,
    next_combo_id,
    parse_tool_blocks,
    patch_conclusion_card,
    save_v4_state,
    set_active_combo,
    set_combo_status,
    submit_final_selection,
    update_final_selection,
)


# ── fixtures ───────────────────────────────────────────────────────────
@pytest.fixture
def tmp_reports(tmp_path: Path) -> Path:
    """临时 reports_root。"""
    return tmp_path


@pytest.fixture
def rid() -> str:
    return "test_report_001"


@pytest.fixture
def state_with_two_combos(tmp_reports: Path, rid: str) -> dict:
    """构造含 2 个 combo_session 的 state(combo_1 已出卡,combo_2 讨论中)。"""
    state = default_state()
    c1 = new_combo_session("combo_1", "音乐", ["创造表达", "解决问题"])
    c1["fields_collected"] = {
        "motivation": "我喜欢舞台",
        "hypothesis": "我假设音乐+创造能让我成为独特创作者",
        "work_purposes": ["发现", "成长"],
        "passion_mark": "忍不住想做",
        "timing_mark": "现在",
    }
    c1["conclusion_card"] = {
        **c1["fields_collected"],
        "created_at": "2026-07-07T10:00:00Z",
        "updated_at": "2026-07-07T10:00:00Z",
    }
    c1["status"] = "concluded"
    c2 = new_combo_session("combo_2", "写作", ["掌控全局"])
    c2["status"] = "discussing"
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
    assert s["active_combo_id"] is None
    assert s["final_selection"]["submitted"] is False


def test_new_combo_session_defaults():
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    assert c["combo_id"] == "combo_1"
    assert c["passion"] == "音乐"
    assert c["strengths"] == ["创造表达"]
    assert c["status"] == "discussing"
    assert c["messages"] == []
    assert c["summary"] is None
    assert c["conclusion_card"] is None
    assert all(v is None for v in c["fields_collected"].values())


def test_next_combo_id_increments():
    s = default_state()
    assert next_combo_id(s) == "combo_1"
    s["combo_sessions"] = [new_combo_session("combo_1", "a", ["b"])]
    assert next_combo_id(s) == "combo_2"
    s["combo_sessions"].append(new_combo_session("combo_5", "c", ["d"]))
    assert next_combo_id(s) == "combo_6"  # 取最大 + 1


# ── CRUD 测试 ──────────────────────────────────────────────────────────
def test_create_combo_sets_active_and_id(tmp_reports, rid):
    from app.services.rumination_v4_service import create_combo
    state, combo = create_combo(tmp_reports, rid, "音乐", ["创造表达", "解决问题"])
    assert combo["combo_id"] == "combo_1"
    assert state["active_combo_id"] == "combo_1"
    assert state["main_section"] == "combo_session"
    # 再创建一个
    state, combo2 = create_combo(tmp_reports, rid, "音乐", ["创造表达"])  # 相同子集允许重复
    assert combo2["combo_id"] == "combo_2"
    assert state["active_combo_id"] == "combo_2"


def test_delete_combo_removes_messages_and_converges_final_selection(tmp_reports, rid, state_with_two_combos):
    # 把 combo_1 加入 final_selection
    state = update_final_selection(tmp_reports, rid, ["combo_1"])
    assert state["final_selection"]["selected_combo_ids"] == ["combo_1"]
    # 删 combo_1
    state = delete_combo(tmp_reports, rid, "combo_1")
    assert find_combo(state, "combo_1") is None
    # final_selection 自动收敛
    assert "combo_1" not in state["final_selection"]["selected_combo_ids"]
    # active 指向剩下的 combo_2
    assert state["active_combo_id"] == "combo_2"


def test_delete_last_combo_returns_to_matrix(tmp_reports, rid):
    from app.services.rumination_v4_service import create_combo
    create_combo(tmp_reports, rid, "音乐", ["创造表达"])
    state = delete_combo(tmp_reports, rid, "combo_1")
    assert state["active_combo_id"] is None
    assert state["main_section"] == "matrix"


def test_delete_nonexistent_raises(tmp_reports, rid, state_with_two_combos):
    with pytest.raises(ValueError, match="combo_id 不存在"):
        delete_combo(tmp_reports, rid, "combo_xxx")


def test_set_active_combo(tmp_reports, rid, state_with_two_combos):
    state = set_active_combo(tmp_reports, rid, "combo_1")
    assert state["active_combo_id"] == "combo_1"


def test_set_combo_status_abandoned_keeps_card_and_marks_skipped(tmp_reports, rid, state_with_two_combos):
    """实施口径 §1-新4:跳过不再清卡,仅置 user_skipped=True;恢复 concluded 可逆。"""
    state = set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    c1 = find_combo(state, "combo_1")
    assert c1["status"] == "abandoned"
    assert c1["user_skipped"] is True
    # 卡内容保留
    assert c1["conclusion_card"] is not None
    assert c1["conclusion_card"]["hypothesis"] == "我假设音乐+创造能让我成为独特创作者"
    assert c1["fields_collected"]["hypothesis"] is not None
    # 跳过可逆:再点确认恢复 concluded,清除 user_skipped
    state = set_combo_status(tmp_reports, rid, "combo_1", "concluded")
    c1 = find_combo(state, "combo_1")
    assert c1["status"] == "concluded"
    assert c1["user_skipped"] is False


def test_set_combo_status_abandoned_excluded_from_final_selection(tmp_reports, rid, state_with_two_combos):
    """跳过的卡不进终选(即使卡内容保留)。"""
    set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    with pytest.raises(ValueError):
        update_final_selection(tmp_reports, rid, ["combo_1"])


# ── tool call 协议测试 ─────────────────────────────────────────────────
def test_parse_tool_blocks_extracts_update_field():
    text = '你好!\n```tool\n{"tool":"update_field","field":"motivation","value":"我喜欢舞台"}\n```\n感谢分享'
    cleaned, tools = parse_tool_blocks(text)
    assert "```tool" not in cleaned
    assert len(tools) == 1
    assert tools[0]["tool"] == "update_field"
    assert tools[0]["field"] == "motivation"


def test_parse_tool_blocks_multiple_tools():
    text = (
        '回复\n'
        '```tool\n{"tool":"update_field","field":"motivation","value":"x"}\n```\n'
        '中间\n'
        '```tool\n{"tool":"save_conclusion_card","fields":{"hypothesis":"y"}}\n```'
    )
    cleaned, tools = parse_tool_blocks(text)
    assert len(tools) == 2
    assert tools[1]["tool"] == "save_conclusion_card"


def test_parse_tool_blocks_invalid_json_skipped():
    text = '回复\n```tool\n{not valid json}\n```'
    cleaned, tools = parse_tool_blocks(text)
    assert tools == []
    assert "```tool" not in cleaned


def test_apply_update_field_transparent():
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    state["combo_sessions"] = [c]
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "update_field", "field": "motivation", "value": "我喜欢舞台"
    })
    assert err is None
    assert card is None  # 透明,无事件
    assert c["fields_collected"]["motivation"] == "我喜欢舞台"


def test_apply_save_conclusion_card_requires_hypothesis():
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    state["combo_sessions"] = [c]
    # hypothesis 未填 → 拒绝
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card", "fields": {"motivation": "x"}
    })
    assert err is not None
    assert "hypothesis" in err
    assert card is None


def test_apply_save_conclusion_card_with_hypothesis_string():
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达", "解决问题"])
    state["combo_sessions"] = [c]
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card",
        "fields": {
            "hypothesis": "我假设这个组合能让我成为创作者",
            "motivation": "舞台吸引我",
            "work_purposes": ["发现", "成长"],
            "passion_mark": "忍不住想做",
            "timing_mark": "现在",
        },
    })
    assert err is None
    assert card is not None
    assert card["hypothesis"] == "我假设这个组合能让我成为创作者"
    # 2026-07-27 交互口径:出卡 = 草案,不强制 concluded;确认动作走 set_combo_status
    assert c["status"] == "discussing"


def test_apply_save_conclusion_card_with_dict_hypothesis():
    """多优势 → hypothesis 可为 dict。"""
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达", "解决问题"])
    state["combo_sessions"] = [c]
    hyp_dict = {"创造表达": "假设1", "解决问题": "假设2"}
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card", "fields": {"hypothesis": hyp_dict}
    })
    assert err is None
    assert card["hypothesis"] == hyp_dict


def test_detect_conclusion_signals_both():
    text = f"好的,{CONCLUSION_READY_MARKER}\n我已经把这次探索整理成了结论卡,你看看有没有要改的"
    s = detect_conclusion_signals(text)
    assert s["hidden"] is True
    assert s["visible"] is True


def test_detect_conclusion_signals_only_visible_triggers_fallback():
    """有 visible 锚点话术但无 hidden 标记 → 触发兜底。"""
    text = "我把咱们聊的内容整理成了结论卡,确认一下?"
    s = detect_conclusion_signals(text)
    assert s["hidden"] is False
    assert s["visible"] is True


def test_detect_conclusion_signals_old_phrase_deprecated():
    """旧句式「现在我为你总结了 N 个假设」已废弃,不再视为可见信号。"""
    text = "现在我为你总结了 2 个假设,你可以选择其中一个"
    s = detect_conclusion_signals(text)
    assert s["hidden"] is False
    assert s["visible"] is False


def test_detect_conclusion_signals_neither():
    text = "你能再说具体一点吗?"
    s = detect_conclusion_signals(text)
    assert s["hidden"] is False
    assert s["visible"] is False


# ── patch 结论卡(用户直接编辑)────────────────────────────────────────
def test_patch_conclusion_card_user_edit(tmp_reports, rid, state_with_two_combos):
    state, card = patch_conclusion_card(tmp_reports, rid, "combo_1", {
        "hypothesis": "改后的假设"
    })
    assert card["hypothesis"] == "改后的假设"
    assert card["motivation"] == "我喜欢舞台"  # 其他字段保留


def test_patch_conclusion_card_rejects_empty_hypothesis(tmp_reports, rid, state_with_two_combos):
    with pytest.raises(ValueError, match="hypothesis"):
        patch_conclusion_card(tmp_reports, rid, "combo_1", {"hypothesis": ""})


def test_patch_conclusion_card_rejects_abandoned(tmp_reports, rid, state_with_two_combos):
    set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    with pytest.raises(ValueError, match="abandoned"):
        patch_conclusion_card(tmp_reports, rid, "combo_1", {"hypothesis": "x"})


# ── final_selection 测试 ───────────────────────────────────────────────
def test_final_selection_requires_1_to_3(tmp_reports, rid, state_with_two_combos):
    with pytest.raises(ValueError):
        update_final_selection(tmp_reports, rid, [])
    with pytest.raises(ValueError):
        update_final_selection(tmp_reports, rid, ["combo_1", "combo_2", "combo_3", "combo_4"])  # combo_2/3 无卡


def test_final_selection_requires_has_card(tmp_reports, rid, state_with_two_combos):
    # combo_2 没有 conclusion_card → 拒绝
    with pytest.raises(ValueError):
        update_final_selection(tmp_reports, rid, ["combo_2"])


def test_final_selection_submit_locks(tmp_reports, rid, state_with_two_combos):
    update_final_selection(tmp_reports, rid, ["combo_1"])
    state = submit_final_selection(tmp_reports, rid)
    assert state["final_selection"]["submitted"] is True
    assert state["main_section"] == "end"


# ── load/save IO 测试 ──────────────────────────────────────────────────
def test_load_v4_state_ignores_v3_data(tmp_reports, rid):
    """v3 数据(schema_version=3)被忽略,返回默认 v4 state。"""
    path = tmp_reports / rid / "rumination_progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    v3_data = {"schema_version": 3, "filter_step": 5, "combo_conclusions": {"02": {"text": "x"}}}
    path.write_text(json.dumps(v3_data), encoding="utf-8")
    state = load_v4_state(tmp_reports, rid)
    assert state["schema_version"] == 4
    assert state["combo_sessions"] == []
    # 不破坏 v3 数据
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 3


def test_save_load_round_trip(tmp_reports, rid, state_with_two_combos):
    loaded = load_v4_state(tmp_reports, rid)
    assert len(loaded["combo_sessions"]) == 2
    assert loaded["active_combo_id"] == "combo_2"


# ── build_chat_messages 测试 ───────────────────────────────────────────
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
    # 摘要注入
    assert any("历史对话摘要" in m.content for m in msgs if m.role == "system")
    # 最后是用户最新输入
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "下一句"


def test_build_chat_messages_omits_values_block_when_empty():
    """values_keywords 为 None → prompt 省略价值观关键词注入块(禁固定词兜底)。"""
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    msgs, sys_prompt = build_chat_messages(c, "你好", user_context="", values_keywords=None)
    assert "用户在价值观阶段确认的关键词" not in sys_prompt
    # 传真实关键词 → 块出现
    _, sys_prompt2 = build_chat_messages(c, "你好", user_context="", values_keywords=["发现"])
    assert "用户在价值观阶段确认的关键词：发现" in sys_prompt2


# ── 平衡点字段与再评估闸(实施口径 §1-新5 / §2.2)───────────────────────────
def test_update_field_accepts_balance_fields():
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    state["combo_sessions"] = [c]
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "update_field", "field": "balance_found", "value": False
    })
    assert err is None
    _, err = apply_tool_call(state, "combo_1", {
        "tool": "update_field", "field": "balance_fail_reason", "value": "投入过大,当下难启动"
    })
    assert err is None
    assert c["fields_collected"]["balance_found"] is False
    assert c["fields_collected"]["balance_fail_reason"] == "投入过大,当下难启动"


def test_hypothesis_change_via_update_field_resets_balance():
    """hypothesis 变更 → balance_found / balance_fail_reason 置 None(再评估闸)。"""
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["fields_collected"]["hypothesis"] = "旧假设"
    c["fields_collected"]["balance_found"] = True
    state["combo_sessions"] = [c]
    apply_tool_call(state, "combo_1", {
        "tool": "update_field", "field": "hypothesis", "value": "新假设"
    })
    assert c["fields_collected"]["hypothesis"] == "新假设"
    assert c["fields_collected"]["balance_found"] is None
    assert c["fields_collected"]["balance_fail_reason"] is None


def test_hypothesis_unchanged_keeps_balance():
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    c["fields_collected"]["hypothesis"] = "同一个假设"
    c["fields_collected"]["balance_found"] = True
    state["combo_sessions"] = [c]
    apply_tool_call(state, "combo_1", {
        "tool": "update_field", "field": "hypothesis", "value": "同一个假设"
    })
    assert c["fields_collected"]["balance_found"] is True


def test_save_conclusion_card_includes_balance_and_reset_on_hyp_change():
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    state["combo_sessions"] = [c]
    # 首次出卡:带 balance
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card",
        "fields": {"hypothesis": "假设A", "balance_found": True},
    })
    assert err is None
    assert card["balance_found"] is True
    assert card["balance_fail_reason"] is None
    # 换 hypothesis 且未显式给 balance_found → 重置为 None
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card",
        "fields": {"hypothesis": "假设B"},
    })
    assert err is None
    assert card["hypothesis"] == "假设B"
    assert card["balance_found"] is None
    assert card["balance_fail_reason"] is None
    # 换 hypothesis 但同时显式给出 balance_found → 保留 AI 的新评估
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card",
        "fields": {
            "hypothesis": "假设C",
            "balance_found": False,
            "balance_fail_reason": "价值观不一致",
        },
    })
    assert err is None
    assert card["balance_found"] is False
    assert card["balance_fail_reason"] == "价值观不一致"


def test_patch_conclusion_card_hypothesis_change_resets_balance(tmp_reports, rid, state_with_two_combos):
    state = load_v4_state(tmp_reports, rid)
    c1 = find_combo(state, "combo_1")
    c1["conclusion_card"]["balance_found"] = True
    c1["conclusion_card"]["balance_fail_reason"] = None
    save_v4_state(tmp_reports, rid, state)
    state, card = patch_conclusion_card(tmp_reports, rid, "combo_1", {"hypothesis": "改后的假设"})
    assert card["hypothesis"] == "改后的假设"
    assert card["balance_found"] is None
    assert card["balance_fail_reason"] is None


def test_combo_meta_includes_user_skipped(tmp_reports, rid, state_with_two_combos):
    metas = list_combos(load_v4_state(tmp_reports, rid))
    by_id = {m["combo_id"]: m for m in metas}
    assert by_id["combo_1"]["user_skipped"] is False
    set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    metas = list_combos(load_v4_state(tmp_reports, rid))
    by_id = {m["combo_id"]: m for m in metas}
    assert by_id["combo_1"]["user_skipped"] is True


# ── chips 候选隐藏块解析(实施口径 §2.4)─────────────────────────────────────
def test_extract_hyp_candidates_parses_and_strips_block():
    text = (
        "我为你准备了两条候选,点一条我们继续聊:\n"
        "[STEP3_HYP_JSON]\n"
        '{"candidates": ["开设一家面向都市青年的手工陶艺工作室,定期开课教学",'
        ' "加入一家生活方式品牌公司担任陶艺课程设计师,开发系列产品"]}\n'
        "[/STEP3_HYP_JSON]"
    )
    visible, candidates = extract_hyp_candidates(text)
    assert "[STEP3_HYP_JSON]" not in visible
    assert "我为你准备了两条候选" in visible
    assert len(candidates) == 2
    assert candidates[0].startswith("开设一家")


def test_extract_hyp_candidates_filters_short_and_invalid():
    """过短(<10字)候选被滤除;非法 JSON 块仅剥离不出候选。"""
    text = '[STEP3_HYP_JSON]{"candidates": ["设计师", ""]}[/STEP3_HYP_JSON]回复正文'
    visible, candidates = extract_hyp_candidates(text)
    assert candidates == []
    assert "[STEP3_HYP_JSON]" not in visible
    text2 = "[STEP3_HYP_JSON]{bad json}[/STEP3_HYP_JSON]正文"
    visible2, candidates2 = extract_hyp_candidates(text2)
    assert candidates2 == []
    assert visible2 == "正文"


def test_extract_hyp_candidates_empty_text():
    visible, candidates = extract_hyp_candidates("")
    assert visible == ""
    assert candidates == []


# ── 2026-07-27 交互口径:出卡不锁 / 确认才锁 / 再聊聊反馈注入 ──────────
def test_reopen_feedback_injected_and_cleared(tmp_path):
    """已确认 →「再聊聊」(discussing):写入 reopen_feedback 并注入 LLM 上下文;
    AI 重新 save_conclusion_card 迭代后自动清除;确认闭环也清除。"""
    from app.services.rumination_v4_service import (
        apply_tool_call,
        build_chat_messages,
        find_combo,
        load_v4_state,
        new_combo_session,
        default_state,
        save_v4_state,
        set_combo_status,
    )

    rid = "reopen_report"
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    state["combo_sessions"] = [c]
    save_v4_state(tmp_path, rid, state)

    # 1) LLM 出草案卡:状态仍是 discussing(不锁)
    state = load_v4_state(tmp_path, rid)
    card, err = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card",
        "fields": {"hypothesis": "我假设音乐+创造能让我成为独特创作者"},
    })
    assert err is None and card is not None
    assert find_combo(state, "combo_1")["status"] == "discussing"
    save_v4_state(tmp_path, rid, state)

    # 2) 草案期 build_chat_messages 注入当前草案
    msgs, _ = build_chat_messages(find_combo(state, "combo_1"), "再帮我想想")
    sys_texts = [m.content for m in msgs if m.role == "system"]
    draft_note = [t for t in sys_texts if "当前结论草案" in t]
    assert draft_note, "草案期应注入当前结论草案"
    assert "我假设音乐+创造能让我成为独特创作者" in draft_note[0]
    assert "再聊聊" not in draft_note[0]  # 无 reopen_feedback 时不带不满意话术

    # 3) 用户确认 → concluded:不再注入草案
    state = set_combo_status(tmp_path, rid, "combo_1", "concluded")
    msgs, _ = build_chat_messages(find_combo(state, "combo_1"), "好")
    assert not [m for m in msgs if m.role == "system" and "当前结论草案" in m.content]

    # 4) 用户点「再聊聊」→ discussing:写入并注入 reopen_feedback
    state = set_combo_status(tmp_path, rid, "combo_1", "discussing")
    combo = find_combo(state, "combo_1")
    assert combo.get("reopen_feedback")
    msgs, _ = build_chat_messages(combo, "我觉得还差点意思")
    fb_note = [m.content for m in msgs if m.role == "system" and "再聊聊" in m.content]
    assert fb_note, "再聊聊后应注入不满意反馈"
    assert "哪里不合适" in fb_note[0]

    # 5) AI 迭代重出卡 → reopen_feedback 清除,但草案注入保留
    card2, err2 = apply_tool_call(state, "combo_1", {
        "tool": "save_conclusion_card",
        "fields": {"hypothesis": "我假设音乐+创造+教学能让我成为独特创作者"},
    })
    assert err2 is None
    assert combo.get("reopen_feedback") is None
    assert combo["status"] == "discussing"  # 仍不锁
    msgs, _ = build_chat_messages(combo, "嗯")
    notes = [m.content for m in msgs if m.role == "system" and "当前结论草案" in m.content]
    assert notes and "教学" in notes[0] and "再聊聊" not in notes[0]

    # 6) 再次确认闭环
    save_v4_state(tmp_path, rid, state)
    state = set_combo_status(tmp_path, rid, "combo_1", "concluded")
    assert find_combo(state, "combo_1").get("reopen_feedback") is None


def test_build_chat_messages_skips_empty_messages(tmp_path):
    """历史 tool-only 轮次落盘的空 assistant 消息不得进入 LLM 上下文(防污染/空气泡后遗症)。"""
    from app.services.rumination_v4_service import (
        build_chat_messages,
        find_combo,
        new_combo_session,
        default_state,
        append_message,
        save_v4_state,
        load_v4_state,
    )

    rid = "empty_msg_report"
    state = default_state()
    c = new_combo_session("combo_1", "音乐", ["创造表达"])
    state["combo_sessions"] = [c]
    append_message(state, "combo_1", "user", "我喜欢舞台")
    append_message(state, "combo_1", "assistant", "说说看,舞台最吸引你的是什么?")
    append_message(state, "combo_1", "user", "灯光亮起的那一刻")
    append_message(state, "combo_1", "assistant", "")  # 历史空气泡
    save_v4_state(tmp_path, rid, state)

    state = load_v4_state(tmp_path, rid)
    msgs, _ = build_chat_messages(find_combo(state, "combo_1"), "继续说")
    conv = [(m.role, m.content) for m in msgs if m.role in ("user", "assistant")]
    assert all(content.strip() for _, content in conv)
    assert ("assistant", "") not in conv
    # 有效消息保留
    assert ("user", "我喜欢舞台") in conv
    assert ("assistant", "说说看,舞台最吸引你的是什么?") in conv
