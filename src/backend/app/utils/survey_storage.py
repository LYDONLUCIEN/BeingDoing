"""
调研问卷存储工具

为 simple（激活码）和 complex（session）两种模式提供统一的 basic_info 存取。
- Simple: data/simple/{session_id}/basic_info.json
- Complex: data/conversations/{session_id}/basic_info.json
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List

# 调研字段到中文标签的映射（用于 format_basic_info_for_prompt）
SURVEY_LABELS: Dict[str, str] = {
    "nickname": "昵称",
    "gender": "性别",
    "age": "年龄",
    "education_school": "院校",
    "education_degree": "学历",
    "education_major": "专业",
    "city": "长期生活的城市",
    "family_status": "家庭生活状态",
    "family_affects_career": "家庭生活状态是否影响职业选择",
    "career_status": "职业状态",
    "industry": "行业",
    "position": "岗位",
    "work_years_total": "累计工作年限",
    "work_history": "分别在哪儿工作",
    "company_types": "企业类型",
    "salary_level": "薪资待遇水平",
    "core_needs": "核心诉求/困扰/目标",
    "core_needs_other": "核心诉求（其他补充）",
    "past_consultation": "过往咨询经历",
}


def _get_basic_info_path(session_id: str, base_dir: str) -> Path:
    """获取 basic_info.json 的存储路径"""
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    session_dir = base / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / "basic_info.json"


def save_basic_info(session_id: str, data: Dict[str, Any], base_dir: str) -> None:
    """
    保存调研问卷数据到 basic_info.json

    Args:
        session_id: 会话 ID
        data: 调研数据字典
        base_dir: 存储根目录（data/simple 或 data/conversations）
    """
    path = _get_basic_info_path(session_id, base_dir)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_basic_info(session_id: str, base_dir: str) -> Optional[Dict[str, Any]]:
    """
    从 basic_info.json 加载调研数据

    Returns:
        调研数据字典，不存在或解析失败时返回 None
    """
    path = _get_basic_info_path(session_id, base_dir)
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(content or "{}")
    except (json.JSONDecodeError, OSError):
        return None


_PRIOR_CONTEXT_FILENAME = "prior_context_{phase}.txt"


def save_prior_context(session_id: str, phase: str, text: str, base_dir: str) -> None:
    """
    保存某阶段的上一轮咨询结果文本。

    Args:
        session_id: 会话 ID
        phase: 目标阶段（存在 strengths 或 interests_goals 等）
        text: 上传或自动收集的文本
        base_dir: 存储根目录
    """
    base = Path(base_dir)
    session_dir = base / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = _PRIOR_CONTEXT_FILENAME.format(phase=phase)
    (session_dir / filename).write_text(text, encoding="utf-8")


def load_prior_context(session_id: str, phase: str, base_dir: str) -> str:
    """
    加载某阶段的上一轮咨询结果文本。

    默认加载规则：
      - strengths 阶段 → 先查 prior_context_strengths.txt；
        若无，则尝试从 values 阶段的对话文件自动生成摘要（暂返回空，由前端上传）
      - interests_goals 阶段 → 先查 prior_context_interests_goals.txt；
        若无，则尝试 prior_context_strengths.txt 作为 fallback

    Returns:
        文本内容，找不到返回空字符串
    """
    base = Path(base_dir)
    session_dir = base / session_id
    filename = _PRIOR_CONTEXT_FILENAME.format(phase=phase)
    path = session_dir / filename
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    # interests_goals fallback → 尝试 strengths 结果
    if phase in ("interests_goals", "interests", "goals"):
        fallback = session_dir / _PRIOR_CONTEXT_FILENAME.format(phase="strengths")
        if fallback.exists():
            try:
                return fallback.read_text(encoding="utf-8").strip()
            except OSError:
                pass

    # purpose 阶段 → 合并所有前序阶段的 prior context
    if phase == "purpose":
        parts: List[str] = []
        for prev_phase in ("values", "strengths", "interests_goals"):
            prev_path = session_dir / _PRIOR_CONTEXT_FILENAME.format(phase=prev_phase)
            if prev_path.exists():
                try:
                    text = prev_path.read_text(encoding="utf-8").strip()
                    if text:
                        parts.append(f"【{prev_phase} 阶段结果】\n{text}")
                except OSError:
                    pass
        if parts:
            return "\n\n".join(parts)

    return ""


def format_basic_info_for_prompt(data: Optional[Dict[str, Any]]) -> str:
    """
    将调研数据格式化为可放入提示词的文本。

    Args:
        data: 调研数据字典

    Returns:
        格式化后的文本，若无数据返回「暂无」
    """
    if not data:
        return "暂无"

    lines: List[str] = []
    for key, label in SURVEY_LABELS.items():
        value = data.get(key)
        if value is None or value == "":
            continue
        if isinstance(value, list):
            value = "、".join(str(v) for v in value)
        lines.append(f"{label}：{value}")

    if not lines:
        return "暂无"
    return "\n".join(lines)
