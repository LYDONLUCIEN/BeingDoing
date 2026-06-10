"""neg gate 简化架构测试：一次性注入所有条目，LLM 自行逐条讨论。"""

from app.utils.rumination_neg_gate import (
    build_injection_zh,
    build_neg_all_done_injection,
    build_neg_progress_header,
    collect_step2_mismatches,
    collect_step3_hypothesis_candidates,
    collect_step5_should_do,
    collect_step6_future,
    refresh_neg_state_injection,
    user_wants_neg_advance,
)


class TestNegGateSimpleInjection:
    def test_injection_includes_all_items(self):
        """一次性注入所有待讨论条目，而非逐条。"""
        rows = []
        for i in range(3):
            rows.append(
                {
                    "id": str(i + 1),
                    "热爱": f"热{i+1}",
                    "优势": f"优{i+1}",
                    "匹配性": "不匹配",
                }
            )
        items = collect_step2_mismatches(rows)
        inj = build_injection_zh(2, "mismatch", items, False)
        # 应包含所有 3 条
        assert "热1" in inj
        assert "热2" in inj
        assert "热3" in inj
        assert "共 3 条" in inj

    def test_injection_no_protocol_markers(self):
        """不再包含 [NEG_ITEM_DONE] 协议标记。"""
        rows = [
            {"id": "1", "热爱": "感官创作", "优势": "建立关联", "匹配性": "不匹配"},
        ]
        items = collect_step2_mismatches(rows)
        inj = build_injection_zh(2, "mismatch", items, False)
        assert "NEG_ITEM_DONE" not in inj
        assert "机器协议" not in inj

    def test_injection_guides_natural_transition(self):
        """注入文案应引导 LLM 自然过渡而非协议标记。"""
        rows = [
            {"id": "1", "热爱": "感官创作", "优势": "建立关联", "匹配性": "不匹配"},
        ]
        items = collect_step2_mismatches(rows)
        inj = build_injection_zh(2, "mismatch", items, False)
        assert "逐条讨论" in inj or "逐条" in inj
        assert "结束讨论" in inj

    def test_injection_style_guard_one_question(self):
        """style_guard 仍保留一次一问约束。"""
        rows = [
            {"id": "1", "热爱": "感官创作", "优势": "建立关联", "匹配性": "不匹配"},
        ]
        items = collect_step2_mismatches(rows)
        inj = build_injection_zh(2, "mismatch", items, False)
        assert "一个问号" in inj or "一个问题" in inj

    def test_empty_items_returns_all_done(self):
        """空条目列表返回 all_done 注入。"""
        inj = build_neg_all_done_injection()
        assert "全部" in inj and "结束讨论" in inj


class TestNegGateRefreshState:
    def test_refresh_rebuilds_injection(self):
        """refresh_neg_state_injection 正常重建 injection。"""
        neg = {
            "status": "exploring",
            "step": 2,
            "kind": "mismatch",
            "items": [
                {"id": "1", "热爱": "热1", "优势": "优1", "label": "热1 vs 优1"},
                {"id": "2", "热爱": "热2", "优势": "优2", "label": "热2 vs 优2"},
            ],
            "current_index": 0,
            "llm_failed": False,
            "injection_zh": "",
        }
        refreshed = refresh_neg_state_injection(neg)
        assert refreshed["injection_zh"]
        assert "热1" in refreshed["injection_zh"]
        assert "热2" in refreshed["injection_zh"]


class TestUserAdvanceIntent:
    def test_user_wants_neg_advance_always_false(self):
        """简化架构下不再依赖程序检测用户意图。"""
        assert not user_wants_neg_advance("这条聊完了，下一条吧")
        assert not user_wants_neg_advance("我们看下一条")


class TestStep5Collect:
    def test_collect_should_do(self):
        """step 5 收集「应该做」行。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "写小说", "工作目的": "表达", "激情标记": "应该做"},
            {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": "做软件", "工作目的": "创造", "激情标记": "忍不住想做"},
            {"id": "3", "热爱": "音乐", "优势": "听力", "用户确认的假设": "做音频", "工作目的": "连接", "激情标记": "应该做"},
        ]
        items = collect_step5_should_do(rows)
        assert len(items) == 2
        assert items[0]["id"] == "1"
        assert items[1]["id"] == "3"

    def test_collect_should_do_label_shows_hypothesis(self):
        """step 5 label 应显示假设文本（字段名修复验证）。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "当个自由作家", "工作目的": "表达", "激情标记": "应该做"},
        ]
        items = collect_step5_should_do(rows)
        assert "当个自由作家" in items[0]["label"]
        assert "假设「当个自由作家」" in items[0]["label"]

    def test_collect_all_positive_returns_empty(self):
        """全选「忍不住想做」时不应收集到条目。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "写小说", "激情标记": "忍不住想做"},
            {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": "做软件", "激情标记": "忍不住想做"},
        ]
        items = collect_step5_should_do(rows)
        assert len(items) == 0


class TestStep6Collect:
    def test_collect_future(self):
        """step 6 收集「未来」行。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "写小说", "激情标记": "忍不住想做", "现实标记": "未来"},
            {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": "做软件", "激情标记": "忍不住想做", "现实标记": "现在"},
        ]
        items = collect_step6_future(rows)
        assert len(items) == 1
        assert items[0]["id"] == "1"

    def test_collect_future_label_shows_hypothesis(self):
        """step 6 label 应显示假设文本（字段名修复验证）。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "开个写作工作室", "激情标记": "忍不住想做", "现实标记": "未来"},
        ]
        items = collect_step6_future(rows)
        assert "开个写作工作室" in items[0]["label"]


class TestStep3CandidatesOnly:
    def test_candidates_excludes_none(self):
        """step 3 hypothesis_candidates 应排除「无」和空行。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "无"},
            {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": ""},
            {"id": "3", "热爱": "音乐", "优势": "听力", "用户确认的假设": "做个播客"},
        ]
        items = collect_step3_hypothesis_candidates(rows)
        assert len(items) == 1
        assert items[0]["id"] == "3"

    def test_candidates_label_shows_hypothesis(self):
        """step 3 candidates label 应显示假设文本（字段名修复验证）。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "做个自由作家"},
        ]
        items = collect_step3_hypothesis_candidates(rows)
        assert "做个自由作家" in items[0]["label"]

    def test_all_none_returns_empty(self):
        """全部选「无」时 candidates 为空，gate 不应触发。"""
        rows = [
            {"id": "1", "热爱": "创作", "优势": "写作", "用户确认的假设": "无"},
            {"id": "2", "热爱": "编程", "优势": "逻辑", "用户确认的假设": "无"},
        ]
        items = collect_step3_hypothesis_candidates(rows)
        assert len(items) == 0
