"""Markdown 测试清单解析器

将 - [ ] / - [x] 格式的待测清单解析为结构化 TestItem 列表。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from common.models import TestItem
from common.task_mapping import classify_item, get_test_file


# ── 正则 ─────────────────────────────────────────────────────────────
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)")
_CHECKBOX_RE = re.compile(r"^-\s+\[([ xX])\]\s+(.*)")
_TASK_ID_RE = re.compile(r"\*\*\(([A-Z]-\d+(?:,\s*[A-Z]-\d+)*)\)\*\*")
_PRIORITY_TABLE_ROW_RE = re.compile(r"\|\s*\*?\*?(P[0-2])\*?\*?\s*\|")
_PRIORITY_TABLE_END_RE = re.compile(r"^\|[-|]+\|$")

# ── 优先级表格中的 section → priority 映射 ──────────────────────────
_PRIORITY_SECTION_RE = re.compile(r"\*\*([^*]+)\*\*")


def parse_checklist(filepath: str) -> Tuple[str, List[TestItem], dict]:
    """解析 MD 清单文件。

    Returns:
        (title, items, priority_map)
        priority_map: dict[section_text, priority] 从优先级表格解析
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    title = ""
    category = ""
    section = ""
    items: List[TestItem] = []
    priority_map: dict[str, str] = {}
    in_priority_table = False
    current_priority = ""

    for line in lines:
        stripped = line.strip()

        # ── 标题 ────────────────────────────────────────────────────
        m_heading = _HEADING_RE.match(stripped)
        if m_heading:
            level = len(m_heading.group(1))
            text = m_heading.group(2).strip()
            if level == 1 and not title:
                title = text
                continue
            if level == 2:
                category = text
                section = ""
                continue
            if level == 3:
                section = text
                continue
            continue

        # ── 优先级表格检测 ──────────────────────────────────────────
        if _PRIORITY_TABLE_ROW_RE.search(stripped):
            in_priority_table = True
            m = _PRIORITY_TABLE_ROW_RE.search(stripped)
            if m:
                current_priority = m.group(1)
            # 同一行提取 section 名
            # 格式: | **P0** | 一、功能 | 或 | **P0** | **一、功能** |
            # 去掉匹配到的优先级和管道符，找剩余的粗体文本
            line_without_prio = stripped
            if m:
                line_without_prio = line_without_prio.replace(m.group(0), "", 1)
            # 找粗体 section
            m_sec = _PRIORITY_SECTION_RE.search(line_without_prio)
            if m_sec:
                sec_text = m_sec.group(1).strip()
                if current_priority and sec_text not in (current_priority, "P0", "P1", "P2"):
                    priority_map[sec_text] = current_priority
            # 如果没有粗体 section，取第二个管道列的非空文本
            if not m_sec and current_priority:
                parts = [p.strip() for p in line_without_prio.split("|")]
                parts = [p for p in parts if p and p != "-"]  # 去掉分隔行
                if len(parts) >= 1:
                    # 第一个非优先级的部分作为 section
                    for p in parts:
                        p_clean = p.strip().replace("*", "")
                        if p_clean and p_clean != current_priority:
                            priority_map[p_clean] = current_priority
                            break
            continue
        if in_priority_table:
            if _PRIORITY_TABLE_END_RE.match(stripped):
                # 表格下面的描述行，可能含 section 名
                continue
            # 解析表格中 section 名（粗体部分）
            m_section = _PRIORITY_SECTION_RE.search(stripped)
            if m_section:
                sec_text = m_section.group(1).strip()
                if current_priority:
                    priority_map[sec_text] = current_priority
            # 非粗体行忽略（继续读下一行找 section）
            if not stripped.startswith("|"):
                in_priority_table = False
            continue

        # ── checkbox 项 ────────────────────────────────────────────
        m_cb = _CHECKBOX_RE.match(stripped)
        if not m_cb:
            continue

        checked = m_cb.group(1).lower() == "x"
        body = m_cb.group(2).strip()

        # 提取 task ID
        m_tid = _TASK_ID_RE.search(body)
        if not m_tid:
            continue

        task_ids_str = m_tid.group(1)
        task_ids = [tid.strip() for tid in task_ids_str.split(",")]

        # 描述 = checkbox 文本去掉 task ID 标注
        description = body[: m_tid.start()].strip()
        if not description:
            # task ID 在行首，描述在后面
            description = body[m_tid.end():].strip()

        if not description:
            continue

        # 判定类型
        item_type = classify_item(task_ids, description)
        test_file = get_test_file(task_ids)

        # 优先级
        priority = _resolve_priority(section, category, priority_map)

        # 初始状态
        status = "passed" if checked else "pending"

        items.append(TestItem(
            task_ids=task_ids,
            description=description,
            section=section,
            category=category,
            item_type=item_type,
            priority=priority,
            status=status,
            test_file=test_file,
        ))

    # ── 第二轮：回填优先级（优先级表格在清单末尾，解析时 checkbox 先于表格） ─
    if priority_map:
        for it in items:
            if not it.priority:
                it.priority = _resolve_priority(it.section, it.category, priority_map)

    return title, items, priority_map


def _resolve_priority(section: str, category: str, priority_map: dict) -> str:
    """从优先级映射表匹配当前 section/category 的优先级"""
    if not priority_map:
        return ""
    # 精确匹配 section
    if section and section in priority_map:
        return priority_map[section]
    # 精确匹配 category
    if category and category in priority_map:
        return priority_map[category]
    # 模糊匹配：section 包含在 key 中
    for key, pri in priority_map.items():
        if section and key in section:
            return pri
        if category and key in category:
            return pri
    return ""
