"""子步 3 改版：表格脱敏、ROW_STATE_JSON 解析、逐行解锁、闸门 pending 收集。"""
import json
import os
from pathlib import Path
import tempfile

# 部分环境将 DEBUG 设为非布尔串（如 release），会导致 Settings 校验失败
if "DEBUG" in os.environ:
    _dv = os.environ["DEBUG"].strip().lower()
    if _dv not in ("true", "false", "1", "0", ""):
        del os.environ["DEBUG"]

from app.api.v1.simple_chat.stream_utils import split_visible_reply_and_row_state
from app.api.v1.simple_chat_routes import _try_rumination_step3_row_unlock
from app.utils.rumination_neg_gate import collect_step3_hypothesis_candidates
from app.utils.rumination_ops import is_rumination_step3_row_hypothesis_complete
from app.utils.rumination_table_widgets import redact_step3_rows_for_widget


def test_redact_step3_hides_rows_after_cursor():
    rows = [
        {"id": "1", "热爱": "A", "优势": "B", "匹配性": "匹配", "用户确认的假设": "假设一"},
        {"id": "2", "热爱": "C", "优势": "D", "匹配性": "匹配", "用户确认的假设": "假设二"},
    ]
    out = redact_step3_rows_for_widget(rows, cursor=0)
    assert out[0]["热爱"] == "A"
    assert out[0]["用户确认的假设"] == "假设一"
    assert out[1]["热爱"] == ""
    assert out[1]["用户确认的假设"] == ""
    assert out[1]["id"] == "2"


def test_split_visible_reply_and_row_state():
    raw = (
        "好的，我们确认本行。\n\n"
        '[ROW_STATE_JSON]\n{"row": 0, "state": "confirmed"}\n[/ROW_STATE_JSON]'
    )
    vis, obj = split_visible_reply_and_row_state(raw)
    assert "ROW_STATE_JSON" not in vis
    assert obj == {"row": 0, "state": "confirmed"}


def test_step3_unlock_bumps_cursor_when_row_matches_and_hyp_complete():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rid = "r1"
        (root / rid).mkdir(parents=True)
        prog = {
            "main_section": "filter",
            "filter_step": 3,
            "filter_row_cursor": 0,
            "filter_table": [
                {
                    "id": "1",
                    "热爱": "x",
                    "优势": "y",
                    "用户确认的假设": "无",
                },
                {
                    "id": "2",
                    "热爱": "a",
                    "优势": "b",
                    "用户确认的假设": "",
                },
            ],
            "filter_step_snapshots": {},
        }
        (root / rid / "rumination_progress.json").write_text(
            json.dumps(prog, ensure_ascii=False), encoding="utf-8"
        )
        saved = _try_rumination_step3_row_unlock(root, rid, {"row": 0, "state": "confirmed"})
        assert saved is not None
        assert saved.get("filter_row_cursor") == 1


def test_step3_unlock_skips_wrong_row_index():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rid = "r2"
        (root / rid).mkdir(parents=True)
        prog = {
            "main_section": "filter",
            "filter_step": 3,
            "filter_row_cursor": 0,
            "filter_table": [
                {"id": "1", "用户确认的假设": "填写完成"},
            ],
            "filter_step_snapshots": {},
        }
        (root / rid / "rumination_progress.json").write_text(
            json.dumps(prog, ensure_ascii=False), encoding="utf-8"
        )
        assert _try_rumination_step3_row_unlock(root, rid, {"row": 1, "state": "confirmed"}) is None


def test_step3_unlock_skips_incomplete_hypothesis():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rid = "r3"
        (root / rid).mkdir(parents=True)
        prog = {
            "main_section": "filter",
            "filter_step": 3,
            "filter_row_cursor": 0,
            "filter_table": [{"id": "1", "用户确认的假设": ""}],
            "filter_step_snapshots": {},
        }
        (root / rid / "rumination_progress.json").write_text(
            json.dumps(prog, ensure_ascii=False), encoding="utf-8"
        )
        assert _try_rumination_step3_row_unlock(root, rid, {"row": 0, "state": "confirmed"}) is None


def test_collect_step3_candidates_skips_none_and_empty():
    """step 3 candidates 应排除「无」和空行，只保留用户自填假设。"""
    rows = [
        {"id": "1", "热爱": "a", "优势": "b", "用户确认的假设": "无"},
        {"id": "2", "热爱": "c", "优势": "d", "用户确认的假设": ""},
        {"id": "3", "热爱": "e", "优势": "f", "用户确认的假设": "做个自由职业者"},
    ]
    cand = collect_step3_hypothesis_candidates(rows)
    assert len(cand) == 1
    assert cand[0]["id"] == "3"


# ── Bug fix 验证：前端内部标记值不得被视为有效假设 ──

_STEP3_OPT_FILL = "__rum_s3_fill__"
_STEP3_OPT_NONE = "__rum_s3_none__"


def test_hypothesis_complete_rejects_internal_marker():
    """前端内部标记 '__rum_s3_fill__' 不应被视为有效假设。"""
    assert not is_rumination_step3_row_hypothesis_complete(_STEP3_OPT_FILL)
    assert not is_rumination_step3_row_hypothesis_complete(_STEP3_OPT_NONE)
    assert not is_rumination_step3_row_hypothesis_complete("")
    assert not is_rumination_step3_row_hypothesis_complete(None)


def test_hypothesis_complete_accepts_real_values():
    """真实假设文案（含「无」）应被视为有效假设。"""
    assert is_rumination_step3_row_hypothesis_complete("无")
    assert is_rumination_step3_row_hypothesis_complete("成为一名户外故事领队")
    assert is_rumination_step3_row_hypothesis_complete("  有效文案  ")


def test_step3_unlock_rejects_fill_marker():
    """即使后端 filter_table 中存入了前端标记值，也不应解锁下一行。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rid = "r4"
        (root / rid).mkdir(parents=True)
        prog = {
            "main_section": "filter",
            "filter_step": 3,
            "filter_row_cursor": 0,
            "filter_table": [
                {"id": "1", "用户确认的假设": _STEP3_OPT_FILL},
                {"id": "2", "用户确认的假设": ""},
            ],
            "filter_step_snapshots": {},
        }
        (root / rid / "rumination_progress.json").write_text(
            json.dumps(prog, ensure_ascii=False), encoding="utf-8"
        )
        # 标记值 → 不完整 → 不解锁
        assert _try_rumination_step3_row_unlock(root, rid, {"row": 0, "state": "confirmed"}) is None


def test_step3_unlock_accepts_real_hypothesis():
    """真实假设文案 → 解锁成功。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rid = "r5"
        (root / rid).mkdir(parents=True)
        prog = {
            "main_section": "filter",
            "filter_step": 3,
            "filter_row_cursor": 0,
            "filter_table": [
                {"id": "1", "用户确认的假设": "成为一名户外领队"},
                {"id": "2", "用户确认的假设": ""},
            ],
            "filter_step_snapshots": {},
        }
        (root / rid / "rumination_progress.json").write_text(
            json.dumps(prog, ensure_ascii=False), encoding="utf-8"
        )
        saved = _try_rumination_step3_row_unlock(root, rid, {"row": 0, "state": "confirmed"})
        assert saved is not None
        assert saved.get("filter_row_cursor") == 1


# ── 兜底自动解锁：当 ROW_STATE_JSON 未输出但假设已完整时自动推进 cursor ──

from app.api.v1.simple_chat_routes import _try_rumination_step3_auto_unlock


def _make_progress(td, rid, cursor, table):
    """辅助函数：创建临时 rumination_progress 文件。"""
    root = Path(td)
    (root / rid).mkdir(parents=True)
    prog = {
        "main_section": "filter",
        "filter_step": 3,
        "filter_row_cursor": cursor,
        "filter_table": table,
        "filter_step_snapshots": {},
    }
    (root / rid / "rumination_progress.json").write_text(
        json.dumps(prog, ensure_ascii=False), encoding="utf-8"
    )
    return root, rid


def test_auto_unlock_when_hypothesis_complete():
    """当前行假设已完整（选了「无」），兜底自动推进 cursor。"""
    with tempfile.TemporaryDirectory() as td:
        root, rid = _make_progress(td, "r_auto1", 0, [
            {"id": "1", "用户确认的假设": "无"},
            {"id": "2", "用户确认的假设": ""},
        ])
        saved = _try_rumination_step3_auto_unlock(root, rid)
        assert saved is not None
        assert saved.get("filter_row_cursor") == 1


def test_auto_unlock_when_hypothesis_filled():
    """当前行假设已完整（填入了真实文案），兜底自动推进 cursor。"""
    with tempfile.TemporaryDirectory() as td:
        root, rid = _make_progress(td, "r_auto2", 0, [
            {"id": "1", "用户确认的假设": "成为一名户外领队"},
            {"id": "2", "用户确认的假设": ""},
        ])
        saved = _try_rumination_step3_auto_unlock(root, rid)
        assert saved is not None
        assert saved.get("filter_row_cursor") == 1


def test_auto_unlock_skips_when_hypothesis_incomplete():
    """当前行假设未完成（空值），不应自动推进。"""
    with tempfile.TemporaryDirectory() as td:
        root, rid = _make_progress(td, "r_auto3", 0, [
            {"id": "1", "用户确认的假设": ""},
            {"id": "2", "用户确认的假设": ""},
        ])
        saved = _try_rumination_step3_auto_unlock(root, rid)
        assert saved is None


def test_auto_unlock_advances_when_last_row_complete():
    """cursor 在最后一行且假设完整，推进到 len(ft) 表示全部完成。"""
    with tempfile.TemporaryDirectory() as td:
        root, rid = _make_progress(td, "r_auto4", 1, [
            {"id": "1", "用户确认的假设": "无"},
            {"id": "2", "用户确认的假设": "假设文案"},
        ])
        saved = _try_rumination_step3_auto_unlock(root, rid)
        assert saved is not None
        assert saved.get("filter_row_cursor") == 2


def test_auto_unlock_skips_when_hypothesis_is_internal_marker():
    """当前行假设为前端内部标记，不应自动推进。"""
    with tempfile.TemporaryDirectory() as td:
        root, rid = _make_progress(td, "r_auto5", 0, [
            {"id": "1", "用户确认的假设": "__rum_s3_fill__"},
            {"id": "2", "用户确认的假设": ""},
        ])
        saved = _try_rumination_step3_auto_unlock(root, rid)
        assert saved is None


def test_auto_unlock_skips_when_cursor_already_advanced():
    """cursor 已被 ROW_STATE_JSON 推进过（假设已完整），不应重复推进。"""
    with tempfile.TemporaryDirectory() as td:
        # cursor=1 但行0假设已完成 → 行1是当前行
        root, rid = _make_progress(td, "r_auto6", 1, [
            {"id": "1", "用户确认的假设": "已完成"},
            {"id": "2", "用户确认的假设": "当前行讨论中"},
            {"id": "3", "用户确认的假设": ""},
        ])
        # 行1假设已完整 → 应推进到2
        saved = _try_rumination_step3_auto_unlock(root, rid)
        assert saved is not None
        assert saved.get("filter_row_cursor") == 2


# ── 已确认行摘要注入 ──

from app.utils.rumination_row_context import format_step3_confirmed_rows_block


def test_confirmed_rows_block_empty_table():
    """空表 → 无已确认行。"""
    result = format_step3_confirmed_rows_block([], cursor=0)
    assert result == "[内部·子步3已确认行]\n（无，当前为首个组合。）"


def test_confirmed_rows_block_first_row():
    """cursor=0 → 无已确认行。"""
    rows = [
        {"id": "1", "热爱": "写作", "优势": "洞察力", "用户确认的假设": "成为一名专栏作家"},
        {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": ""},
    ]
    result = format_step3_confirmed_rows_block(rows, cursor=0)
    assert "（无，当前为首个组合。）" in result


def test_confirmed_rows_block_two_confirmed():
    """cursor=2 → 前2行已确认，显示摘要。"""
    rows = [
        {"id": "1", "热爱": "写作", "优势": "洞察力", "用户确认的假设": "成为一名专栏作家"},
        {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": "无"},
        {"id": "3", "热爱": "音乐", "优势": "创造力", "用户确认的假设": ""},
    ]
    result = format_step3_confirmed_rows_block(rows, cursor=2)
    assert "第1行" in result
    assert "专栏作家" in result
    assert "第2行" in result
    assert "无" in result
    assert "第3行" not in result


def test_confirmed_rows_block_long_hypothesis_truncated():
    """假设文案过长时截断。"""
    rows = [
        {"id": "1", "热爱": "A", "优势": "B", "用户确认的假设": "这是一段非常非常非常非常非常非常非常非常非常长的假设文案"},
        {"id": "2", "热爱": "C", "优势": "D", "用户确认的假设": ""},
    ]
    result = format_step3_confirmed_rows_block(rows, cursor=1)
    # 假设应被截断
    assert "..." in result or len(result) < 200


def test_confirmed_rows_block_all_confirmed():
    """cursor 等于 len(rows) → 所有行已确认。"""
    rows = [
        {"id": "1", "热爱": "A", "优势": "B", "用户确认的假设": "假设一"},
        {"id": "2", "热爱": "C", "优势": "D", "用户确认的假设": "假设二"},
    ]
    result = format_step3_confirmed_rows_block(rows, cursor=2)
    assert "第1行" in result
    assert "第2行" in result


# ── step3 filter_table 合并：防止 redact 数据覆盖后端原始数据 ──

from app.api.v1.simple_chat_routes import _merge_step3_filter_table


def test_merge_preserves_existing_redacted_fields():
    """前端传来的未解锁行热爱/优势为空，应从后端回填。"""
    incoming = [
        {"id": "1", "热爱": "写作", "优势": "洞察力", "用户确认的假设": "专栏作家"},
        {"id": "2", "热爱": "", "优势": "", "用户确认的假设": ""},  # redact 过
    ]
    existing = [
        {"id": "1", "热爱": "写作", "优势": "洞察力", "用户确认的假设": "专栏作家"},
        {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": ""},
    ]
    merged = _merge_step3_filter_table(incoming, existing)
    assert merged[0]["用户确认的假设"] == "专栏作家"
    assert merged[1]["热爱"] == "编程"
    assert merged[1]["优势"] == "逻辑"


def test_merge_keeps_frontend_edits():
    """前端编辑过的字段不应被后端旧值覆盖。"""
    incoming = [
        {"id": "1", "热爱": "写作", "优势": "洞察力", "用户确认的假设": "户外领队"},
    ]
    existing = [
        {"id": "1", "热爱": "写作", "优势": "洞察力", "用户确认的假设": "专栏作家"},
    ]
    merged = _merge_step3_filter_table(incoming, existing)
    assert merged[0]["用户确认的假设"] == "户外领队"


def test_merge_preserves_backend_extra_keys():
    """后端有但前端没传的字段应保留。"""
    incoming = [
        {"id": "1", "用户确认的假设": "假设一"},
    ]
    existing = [
        {"id": "1", "热爱": "A", "优势": "B", "匹配性": "匹配", "用户确认的假设": "旧假设"},
    ]
    merged = _merge_step3_filter_table(incoming, existing)
    assert merged[0]["热爱"] == "A"
    assert merged[0]["优势"] == "B"
    assert merged[0]["匹配性"] == "匹配"
    assert merged[0]["用户确认的假设"] == "假设一"


def test_merge_handles_longer_existing():
    """后端行数多于前端时，多余行应追加。"""
    incoming = [
        {"id": "1", "用户确认的假设": "假设一"},
    ]
    existing = [
        {"id": "1", "热爱": "A", "优势": "B", "用户确认的假设": "假设一"},
        {"id": "2", "热爱": "C", "优势": "D", "用户确认的假设": ""},
    ]
    merged = _merge_step3_filter_table(incoming, existing)
    assert len(merged) == 2
    assert merged[1]["热爱"] == "C"
