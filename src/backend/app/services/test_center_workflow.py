"""测试中心业务回放语法；只编排已有产品动作，不接受 URL、路径或代码。"""

import re

PHASES = ("values", "strengths", "interests", "purpose", "rumination")
METADATA_FIELDS = {
    "conclusion_state",
    "conclusion_draft",
    "conclusion_final",
    "conclusion_feedback",
    "thread_completed",
    "conclusion_shown_at_turn",
    "conclusion_reject_baseline_user_count",
    "purpose_progress",
}


def compile_workflow(body, context, issues):
    spec = context["spec"] if context else {}
    phase = spec.get("phase")
    v4 = phase == "rumination"
    if not spec.get("workflow_seed"):
        issues.append(
            "业务回放需要结构化状态起点；请重新预览或填写 workflow_seed，不能从提示词文字猜测状态"
        )
    steps = []
    for text in body["inputs"]:
        match = re.fullmatch(r"(发送消息|填写结论)[：:]\s*(.+)", text, re.S)
        if match and (match[1] == "发送消息" or v4):
            steps.append(
                {
                    "action": "message" if match[1] == "发送消息" else "card",
                    "value": match[2].strip(),
                }
            )
            continue
        actions = {"确认结论": "confirm", "再聊聊": "reopen"}
        actions.update(
            {"跳过组合": "skip", "选入终选": "select", "提交终选": "submit"}
            if v4
            else {"请求结论": "request"}
        )
        if text in actions:
            steps.append({"action": actions[text]})
        else:
            issues.append(f"当前阶段不支持的业务操作：{text}")
    checks = []
    choices = {
        "接口状态": ("http", r"[1-5][0-9]{2}"),
        "组合状态": ("combo_status", r"discussing|concluded|abandoned"),
        "判定状态": ("analysis_status", r"none|analyzing|done|failed"),
        "结论状态": ("conclusion_state", r"none|pending|confirmed|rejected"),
        "线程完成": ("completed", r"是|否"),
        "阶段锁定": ("locked", r"是|否"),
        "终选提交": ("submitted", r"是|否"),
        "结论包含": ("card_contains", r".+"),
        "摘要包含": ("summary_contains", r".+"),
        "报告包含": ("report_contains", r".+"),
        "回复包含": ("contains", r".+"),
        "回复不包含": ("excludes", r".+"),
        "语义": ("semantic", r".+"),
    }
    for text in body["assertions"]:
        scope = re.fullmatch(r"第([1-9][0-9]*)步[：:]\s*(.+)", text, re.S)
        if not scope or not 1 <= int(scope[1]) <= len(steps):
            issues.append(f"业务断言需指定有效步骤：{text}")
            continue
        step, criterion = int(scope[1]), scope[2].strip()
        if criterion == "回复非空":
            checks.append({"step": step, "type": "nonempty"})
            continue
        match = re.fullmatch(r"([^：:]+)[：:]\s*(.+)", criterion, re.S)
        entry = choices.get(match[1]) if match else None
        if not entry or not re.fullmatch(entry[1], match[2], re.S):
            issues.append(f"不支持的业务断言：{text}")
            continue
        kind, value = entry[0], match[2]
        if (
            not v4 and kind in {"combo_status", "analysis_status", "submitted", "report_contains"}
        ) or (v4 and kind in {"conclusion_state", "completed"}):
            issues.append(f"当前阶段没有此状态：{text}")
            continue
        checks.append({"step": step, "type": kind, "value": value})
    for step in range(1, len(steps) + 1):
        if not any(c["step"] == step for c in checks):
            issues.append(f"第 {step} 步缺少断言")
    return {"steps": steps, "checks": checks}


def maximum_calls(definition, phase):
    """包括现行产品的重试、判定、结论生成和后台摘要；预留上界不是已发生费用。"""
    costs = (
        {"message": 2, "confirm": 2, "submit": 8}
        if phase == "rumination"
        else {"message": 12, "request": 8, "confirm": 2, "reopen": 0}
    )
    return sum(
        costs.get(s["action"], 0)
        + sum(c["type"] == "semantic" and c["step"] == i + 1 for c in definition["checks"])
        for i, s in enumerate(definition["steps"])
    )
