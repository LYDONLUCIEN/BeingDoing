"""对话输入框焦点恢复测试 — 验证用 useEffect 而非 requestAnimationFrame 恢复焦点"""

import re
from pathlib import Path

CHAT_PAGE = (
    Path(__file__).resolve().parents[2]
    / "src" / "frontend"
    / "app" / "(main)" / "explore" / "chat" / "[phase]"
    / "page.tsx"
)


def test_no_requestAnimationFrame_for_focus():
    """不应使用 requestAnimationFrame 恢复输入框焦点（有时序问题）"""
    content = CHAT_PAGE.read_text(encoding="utf-8")
    # 不应有 "requestAnimationFrame" 和 "inputRef" 和 "focus" 同时出现
    has_raf_focus = bool(
        re.search(r'requestAnimationFrame\s*\([^)]*\bfocus\b', content)
        or re.search(r'requestAnimationFrame[\s\S]{0,200}\.focus\(\)', content)
    )
    assert not has_raf_focus, "page.tsx 不应使用 requestAnimationFrame 恢复焦点"


def test_use_effect_for_focus_restoration():
    """应有 useEffect 监听 sending 状态来恢复焦点"""
    content = CHAT_PAGE.read_text(encoding="utf-8")
    # 用逐行解析找到包含 sending 和 focus 的 useEffect 块
    lines = content.split("\n")
    in_effect = False
    effect_buffer: list[str] = []
    for line in lines:
        if "useEffect" in line and "(" in line:
            in_effect = True
            effect_buffer = [line]
            brace_depth = line.count("{") - line.count("}")
            if brace_depth <= 0:
                in_effect = False
        elif in_effect:
            effect_buffer.append(line)
            brace_depth = brace_depth + line.count("{") - line.count("}")
            if brace_depth <= 0:
                in_effect = False
                eff_text = "\n".join(effect_buffer)
                if "sending" in eff_text and ".focus()" in eff_text:
                    return  # 找到了，测试通过
                effect_buffer = []
    assert False, (
        "应有 useEffect 监听 sending 并调用 inputRef.current?.focus()"
    )
