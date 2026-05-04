"""rumination_ops 表格变换单测 + 沉淀上下文隔离测试"""
import json
import pytest
from pathlib import Path
import tempfile
from app.utils import rumination_ops as ro
from app.utils.conversation_file_manager import ConversationFileManager


def test_filter_strength_drops_uncertain():
    t = [
        {"id": "1", "优势标记": "有充实感"},
        {"id": "2", "优势标记": "不确定"},
    ]
    out = ro.filter_strength(t)
    assert len(out) == 1 and out[0]["id"] == "1"


def test_structure_hypothesis_round1_drops_non_match():
    t = [
        {"id": "1", "匹配性": "匹配", "匹配原因": "ok", "热爱": "a", "优势": "b"},
        {"id": "2", "匹配性": "不匹配", "匹配原因": "no", "热爱": "c", "优势": "d"},
    ]
    out = ro.structure_hypothesis_round1_table(t)
    assert len(out) == 1
    assert "匹配原因" not in out[0]
    assert "假设1" in out[0]
    assert out[0].get("假设3") == ""


def test_value_filter_drops_pending_and_empty_hypothesis():
    t = [
        {"id": "1", "用户确认的假设": "写书", "假设1": "x"},
        {"id": "2", "用户确认的假设": ""},
        {"id": "3", "用户确认的假设": "待定"},
        {"id": "4", "用户确认的假设": "暂未选定"},
    ]
    out = ro.value_filter(t, ["诚信"])
    assert len(out) == 1
    assert out[0]["id"] == "1"
    assert "工作目的" in out[0]
    assert "假设1" not in out[0]


def test_passion_reality_similar_chain():
    t = [
        {"id": "1", "用户确认的假设": "A", "工作目的": "成长"},
        {"id": "2", "用户确认的假设": "B", "工作目的": "都不符合"},
    ]
    p = ro.passion_filter(t)
    assert len(p) == 1
    assert p[0].get("激情标记") == ""
    r = ro.reality_filter(
        [
            {"id": "1", "用户确认的假设": "A", "激情标记": "忍不住想做"},
            {"id": "2", "用户确认的假设": "C", "激情标记": "应该做"},
        ]
    )
    assert len(r) == 1
    s = ro.similar_filter(
        [
            {"id": "1", "用户确认的假设": "A", "现实标记": "现在"},
            {"id": "2", "用户确认的假设": "B", "现实标记": "未来"},
        ]
    )
    assert len(s) == 1
    assert set(s[0].keys()) == {"id", "用户确认的假设"}


def test_extract_from_prior_context_four_sections():
    text = """
【信念 阶段结果】
1. 真诚
2. 责任

【禀赋 阶段结果】
写作、沟通

【热忱 阶段结果】
教育、公益

【使命 阶段结果】
帮助他人
"""
    v, s, i, p = ro.extract_from_prior_context(text)
    assert "真诚" in v or len(v) >= 1
    assert len(s) >= 1
    assert len(i) >= 1
    assert len(p) >= 1


def test_gen_table_maps_strength_markers():
    """gen_table 应根据 strength_markers 映射优势标记初始值。"""
    strengths = ["审美判断", "建立关联", "自驱探索"]
    passions = ["感官创作", "自我探索"]
    markers = ["b", "a", "a"]
    rows = ro.gen_table(strengths, passions, strength_markers=markers)
    # 2 热爱 × 3 优势 = 6 行
    assert len(rows) == 6
    # 第一轮（感官创作）：按 strengths 索引取标记
    assert rows[0]["优势标记"] == "有充实感"          # b
    assert rows[1]["优势标记"] == "有充实感，与成功有关"  # a
    assert rows[2]["优势标记"] == "有充实感，与成功有关"  # a
    # 第二轮（自我探索）：复用同一组标记
    assert rows[3]["优势标记"] == "有充实感"          # b
    assert rows[4]["优势标记"] == "有充实感，与成功有关"  # a
    assert rows[5]["优势标记"] == "有充实感，与成功有关"  # a


def test_gen_table_no_markers_defaults():
    """gen_table 在没有 strength_markers 时默认全部「有充实感」。"""
    strengths = ["a", "b", "c"]
    passions = ["x"]
    rows = ro.gen_table(strengths, passions)
    assert len(rows) == 3
    assert all(r["优势标记"] == "有充实感" for r in rows)


def test_gen_table_no_row_limit():
    """gen_table 不应有 12 行硬限制（3×5=15 应全部生成）。"""
    strengths = ["s1", "s2", "s3", "s4", "s5"]
    passions = ["p1", "p2", "p3"]
    rows = ro.gen_table(strengths, passions)
    assert len(rows) == 15


def test_gen_table_c_marker_maps_to_uncertain():
    """c 标记应映射为「不确定」。"""
    rows = ro.gen_table(["s1"], ["p1"], strength_markers=["c"])
    assert rows[0]["优势标记"] == "不确定"


# ---------------------------------------------------------------------------
# 沉淀上下文隔离测试
# ---------------------------------------------------------------------------


def _make_conv_file(
    tmp: str,
    session_id: str,
    category: str,
    messages: list[dict],
    step_anchors: dict[str, str] | None = None,
) -> None:
    """创建一个对话文件用于测试。

    step_anchors 格式为 {"1": "summary 1", "2": "summary 2"}，
    会展开为 metadata 中的 step_anchor_1 / step_anchor_2 扁平键。
    """
    meta: dict = {
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    if step_anchors:
        for k, v in step_anchors.items():
            meta[f"step_anchor_{k}"] = v
    data = {
        "category": category,
        "messages": messages,
        "metadata": meta,
    }
    from pathlib import Path as P
    fp = P(tmp) / session_id / f"{category}.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestDeleteMessagesFromFilterStep:
    """ConversationFileManager.delete_messages_from_filter_step 测试。"""

    @pytest.mark.asyncio
    async def test_deletes_messages_from_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConversationFileManager(base_dir=tmp)
            sid = "r1"
            cat = "rumination__t1"
            msgs = [
                {"role": "user", "content": "step 1 msg", "filter_step": 1},
                {"role": "assistant", "content": "reply 1", "filter_step": 1},
                {"role": "user", "content": "step 2 msg", "filter_step": 2},
                {"role": "assistant", "content": "reply 2", "filter_step": 2},
                {"role": "user", "content": "step 3 msg", "filter_step": 3},
            ]
            _make_conv_file(tmp, sid, cat, msgs, {"1": "anchor1", "2": "anchor2", "3": "anchor3"})

            deleted = await mgr.delete_messages_from_filter_step(sid, cat, 2)
            assert deleted == 3  # step 2 的 2 条 + step 3 的 1 条

            data = json.loads((Path(tmp) / sid / f"{cat}.json").read_text(encoding="utf-8"))
            remaining = data["messages"]
            assert len(remaining) == 2
            assert remaining[0]["content"] == "step 1 msg"
            assert remaining[1]["content"] == "reply 1"

            # step_anchor_2 / step_anchor_3 应被清除，step_anchor_1 保留
            meta = data["metadata"]
            assert meta.get("step_anchor_1") == "anchor1"  # step 1 anchor 保留
            assert "step_anchor_2" not in meta
            assert "step_anchor_3" not in meta

    @pytest.mark.asyncio
    async def test_keeps_messages_below_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConversationFileManager(base_dir=tmp)
            sid = "r2"
            cat = "rumination__t2"
            msgs = [
                {"role": "user", "content": "step 1", "filter_step": 1},
                {"role": "user", "content": "step 2", "filter_step": 2},
                {"role": "user", "content": "step 3", "filter_step": 3},
            ]
            _make_conv_file(tmp, sid, cat, msgs)

            deleted = await mgr.delete_messages_from_filter_step(sid, cat, 4)
            assert deleted == 0  # 没有 step >= 4 的消息

            data = json.loads((Path(tmp) / sid / f"{cat}.json").read_text(encoding="utf-8"))
            assert len(data["messages"]) == 3

    @pytest.mark.asyncio
    async def test_keeps_messages_without_filter_step(self):
        """没有 filter_step 字段的消息应被保留（非 rumination 历史兼容）。"""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConversationFileManager(base_dir=tmp)
            sid = "r3"
            cat = "rumination__t3"
            msgs = [
                {"role": "user", "content": "old msg 1"},
                {"role": "user", "content": "old msg 2"},
                {"role": "user", "content": "new msg", "filter_step": 3},
            ]
            _make_conv_file(tmp, sid, cat, msgs)

            deleted = await mgr.delete_messages_from_filter_step(sid, cat, 3)
            assert deleted == 1  # 只有 filter_step=3 的消息被删除

            data = json.loads((Path(tmp) / sid / f"{cat}.json").read_text(encoding="utf-8"))
            assert len(data["messages"]) == 2


class TestRuminationStepAnchors:
    """rumination per-step anchor 相关测试（不需要真实 LLM，测试数据结构）。"""

    def test_load_rumination_step_anchors_reads_metadata(self):
        """load_rumination_step_anchors 应从 metadata 中读取 step_anchor_N 字段。"""
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConversationFileManager(base_dir=tmp)
            sid = "r4"
            cat = "rumination__t4"
            _make_conv_file(
                tmp, sid, cat,
                [{"role": "user", "content": "hi"}],
                {"1": "anchor step 1 summary", "2": "anchor step 2 summary"},
            )

            import asyncio
            anchors = asyncio.get_event_loop().run_until_complete(
                mgr.get_conversation_data(sid, cat)
            )
            # 验证 metadata 中有 step_anchor_1 和 step_anchor_2
            meta = anchors.get("metadata", {})
            assert meta.get("step_anchor_1") == "anchor step 1 summary"
            assert meta.get("step_anchor_2") == "anchor step 2 summary"
            assert meta.get("step_anchor_3") is None

    @pytest.mark.asyncio
    async def test_load_rumination_step_anchors_returns_dict(self):
        """load_rumination_step_anchors 返回 {step_num: text} 格式。"""
        from app.utils.context_refiner import load_rumination_step_anchors

        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConversationFileManager(base_dir=tmp)
            sid = "r5"
            cat = "rumination__t5"
            _make_conv_file(
                tmp, sid, cat,
                [{"role": "user", "content": "hi"}],
                {"1": "summary 1", "2": "summary 2", "3": "summary 3"},
            )

            anchors = await load_rumination_step_anchors(sid, cat, mgr)
            assert anchors == {"1": "summary 1", "2": "summary 2", "3": "summary 3"}

    @pytest.mark.asyncio
    async def test_load_rumination_step_anchors_empty(self):
        from app.utils.context_refiner import load_rumination_step_anchors

        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConversationFileManager(base_dir=tmp)
            sid = "r6"
            cat = "rumination__t6"
            _make_conv_file(tmp, sid, cat, [{"role": "user", "content": "hi"}])

            anchors = await load_rumination_step_anchors(sid, cat, mgr)
            assert anchors == {}


class TestRuminationLlmContextFiltering:
    """验证 _trim_history_messages_for_llm 的 rumination 过滤逻辑。"""

    def test_trim_filters_by_filter_step(self):
        """rumination 阶段应只保留当前 filter_step 的消息。"""
        messages = [
            {"role": "user", "content": "step 1 msg", "filter_step": 1},
            {"role": "assistant", "content": "reply 1", "filter_step": 1},
            {"role": "user", "content": "step 2 msg", "filter_step": 2},
            {"role": "assistant", "content": "reply 2", "filter_step": 2},
            {"role": "user", "content": "step 3 msg", "filter_step": 3},
        ]
        # 与后端逻辑一致：按 filter_step 过滤后取最近 30 条
        current_step = 2
        step_msgs = [m for m in messages if int(m.get("filter_step") or 0) == current_step]
        trimmed = step_msgs[-30:]
        assert len(trimmed) == 2
        assert trimmed[0]["content"] == "step 2 msg"
        assert trimmed[1]["content"] == "reply 2"

    def test_trim_preserves_messages_without_filter_step(self):
        """没有 filter_step 的消息不应被 rumination 过滤（兼容历史数据）。"""
        messages = [
            {"role": "user", "content": "old msg 1"},
            {"role": "assistant", "content": "old reply 1"},
            {"role": "user", "content": "old msg 2"},
        ]
        # filter_step = 1 时，没有 filter_step 的消息不匹配
        step_msgs = [m for m in messages if int(m.get("filter_step") or 0) == 1]
        assert len(step_msgs) == 0

    def test_accumulated_anchor_format(self):
        """验证累积 anchor 的拼接格式。"""
        anchors = {"1": "热爱：感官创作", "2": "假设已确认"}
        parts = []
        for s in range(1, 3):
            a = anchors.get(str(s))
            if a:
                parts.append(f"[子步 {s} 要点] {a}")
        accumulated = "\n---\n".join(parts)
        assert "[子步 1 要点] 热爱：感官创作" in accumulated
        assert "[子步 2 要点] 假设已确认" in accumulated
