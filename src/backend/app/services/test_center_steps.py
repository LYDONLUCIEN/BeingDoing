"""将明确中文步骤编译为可检查的浏览器动作；不生成或执行任意代码。"""

import re

PAGES = {
    "首页": "/",
    "关于页面": "/about",
    "注册页面": "/auth/register",
    "个人空间": "/dashboard",
    "价值观对话": "/explore/chat/values?code=FIXTURE",
    "沉淀对话": "/explore/chat/rumination?code=FIXTURE",
}


def compile_ui(body, fixture, issues):
    if fixture not in {"home", "chat", "rumination", "account"}:
        issues.append("当前模板没有可组合的浏览器场景，请选择首页、聊天、沉淀或个人空间")
    steps = []
    for text in body["inputs"]:
        navigate = re.fullmatch(r"打开[：:]?\s*(.+)", text)
        if navigate and navigate[1] in PAGES:
            steps.append({"action": "navigate", "value": PAGES[navigate[1]]})
            continue
        action = re.fullmatch(r"(点击|输入消息|填写|按键)[：:]\s*(.+)", text, re.S)
        if action:
            kind, value = action[1], action[2].strip()
            if kind == "填写" and "=" in value:
                label, content = value.split("=", 1)
                if label.strip():
                    steps.append(
                        {
                            "action": "fill",
                            "label": label.strip(),
                            "value": content.strip(),
                        }
                    )
                    continue
            elif kind == "按键" and value in {"Enter", "Escape", "Tab"}:
                steps.append({"action": "key", "value": value})
                continue
            elif kind in {"点击", "输入消息"}:
                steps.append({"action": "click" if kind == "点击" else "message", "value": value})
                continue
        issues.append(
            f"未支持的操作：{text}；可用打开首页、点击：按钮名、填写：字段名 = 内容、输入消息：内容"
        )
    if not steps or steps[0]["action"] != "navigate":
        issues.append("第一步需要打开一个已支持的页面")
    checks = []
    for original in body["assertions"]:
        match = re.fullmatch(r"第([1-9][0-9]*)步[：:]\s*(.+)", original, re.S)
        step, text = (int(match[1]), match[2]) if match else (len(steps), original)
        if not 1 <= step <= len(steps):
            issues.append(f"断言引用不存在的步骤：{original}")
            continue
        if text == "页面无横向溢出":
            checks.append({"step": step, "type": "no_overflow"})
            continue
        match = re.fullmatch(
            r"(应显示|不应显示|按钮禁用|按钮可用|应跳转|输入应为)[：:]\s*(.+)",
            text,
            re.S,
        )
        if match and (match[1] != "应跳转" or re.fullmatch(r"/[a-zA-Z0-9/_-]*", match[2])):
            checks.append(
                {
                    "step": step,
                    "type": {
                        "应显示": "visible",
                        "不应显示": "hidden",
                        "按钮禁用": "disabled",
                        "按钮可用": "enabled",
                        "应跳转": "url",
                        "输入应为": "input_value",
                    }[match[1]],
                    "value": match[2].strip(),
                }
            )
        else:
            issues.append(f"未支持的断言：{original}")
    return {
        "targets": ["scenario"],
        "fixture": fixture,
        "steps": steps,
        "ui_checks": checks,
        "timeout": 600,
    }
