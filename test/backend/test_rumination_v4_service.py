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


def test_set_combo_status_abandoned_clears_card(tmp_reports, rid, state_with_two_combos):
    state = set_combo_status(tmp_reports, rid, "combo_1", "abandoned")
    c1 = find_combo(state, "combo_1")
    assert c1["status"] == "abandoned"
    assert c1["conclusion_card"] is None
    assert c1["fields_collected"]["hypothesis"] is None


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
    assert c["status"] == "concluded"


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
    text = f"好的,{CONCLUSION_READY_MARKER}\n现在我为你总结了 2 个假设,你可以选择其中一个"
    s = detect_conclusion_signals(text)
    assert s["hidden"] is True
    assert s["visible"] is True


def test_detect_conclusion_signals_only_visible_triggers_fallback():
    """有 visible 话术但无 hidden 标记 → 触发兜底。"""
    text = "现在我为你总结了 2 个假设,你可以选择其中一个"
    s = detect_conclusion_signals(text)
    assert s["hidden"] is False
    assert s["visible"] is True


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
    msgs, sys_prompt = build_chat_messages(c, "下一句", values_list=["发现"])
    assert msgs[0].role == "system"
    assert "音乐" in msgs[0].content
    # 摘要注入
    assert any("历史对话摘要" in m.content for m in msgs if m.role == "system")
    # 最后是用户最新输入
    assert msgs[-1].role == "user"
    assert msgs[-1].content == "下一句"
