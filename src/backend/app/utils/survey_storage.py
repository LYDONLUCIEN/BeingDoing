"""
调研问卷存储工具

basic_info 以用户维度存储：data/user/{user_id}/basic_info.json（仅保留最新 1 份）
prior_context 以 report 维度存储：reports/{report_id}/prior_context_{phase}.txt

保留旧 session_id 接口用于迁移期回退。
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.utils.data_paths import get_user_data_dir

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


def _get_user_basic_info_path(user_id: str) -> Path:
    """用户级 basic_info 路径：data/user/{user_id}/basic_info.json"""
    root = get_user_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    user_dir = root / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "basic_info.json"


def save_basic_info_by_user(user_id: str, data: Dict[str, Any]) -> None:
    """
    按用户保存调研问卷（主入口，仅保留最新 1 份）。

    Args:
        user_id: 用户 ID
        data: 调研数据字典
    """
    path = _get_user_basic_info_path(user_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_basic_info_by_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    按用户加载调研问卷。

    Returns:
        调研数据字典，不存在或解析失败时返回 None
    """
    path = _get_user_basic_info_path(user_id)
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        return json.loads(content or "{}")
    except (json.JSONDecodeError, OSError):
        return None


def merge_basic_info_sources(
    sources: List[Dict[str, Any]], strategy: str = "A"
) -> Dict[str, Any]:
    """
    合并多个 basic_info 源。用于迁移时同一用户多份问卷合并。

    Args:
        sources: 多个 basic_info 字典列表（可按时间排序，0=最早）
        strategy: A=最新覆盖 B=并集(非空优先) C=交集(仅所有源都有该 key 且非空)

    Returns:
        合并后的 basic_info
    """
    if not sources:
        return {}
    if len(sources) == 1:
        return dict(sources[0] or {})
    strategy = (strategy or "A").strip().upper()
    if strategy == "A":
        return dict(sources[-1] or {})
    all_keys = set()
    for s in sources:
        if s:
            all_keys.update(s.keys())
    result: Dict[str, Any] = {}
    if strategy == "B":
        for k in all_keys:
            for s in reversed(sources):
                if s and k in s:
                    v = s[k]
                    if v is not None and v != "":
                        result[k] = v
                        break
    elif strategy == "C":
        for k in all_keys:
            vals = []
            for s in sources:
                if not s or k not in s:
                    break
                v = s[k]
                if v is None or v == "":
                    break
                vals.append(v)
            if len(vals) == len(sources):
                result[k] = vals[-1]
    return result


def _get_basic_info_path(session_id: str, base_dir: str) -> Path:
    """获取 basic_info.json 的存储路径（旧 session 维度，迁移期兼容）"""
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


def _get_prior_context_path_for_report(report_id: str, phase: str, reports_root: Path) -> Path:
    """report 维度 prior_context 路径：reports/{report_id}/prior_context_{phase}.txt"""
    root = Path(reports_root)
    report_dir = root / report_id
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / _PRIOR_CONTEXT_FILENAME.format(phase=phase)


def save_prior_context_for_report(
    report_id: str, phase: str, text: str, reports_root: str
) -> None:
    """
    按 report 保存上一轮咨询结果。

    Args:
        report_id: 报告 ID
        phase: 目标阶段（values/strengths/interests/purpose/rumination）
        text: 文本内容
        reports_root: reports 目录根路径（如 data/simple/reports）
    """
    path = _get_prior_context_path_for_report(report_id, phase, Path(reports_root))
    path.write_text(text, encoding="utf-8")


def load_prior_context_for_report(report_id: str, phase: str, reports_root: str) -> str:
    """
    按 report 加载上一轮咨询结果。purpose/rumination 会合并前置阶段。

    Returns:
        文本内容，找不到返回空字符串
    """
    root = Path(reports_root)
    report_dir = root / report_id
    filename = _PRIOR_CONTEXT_FILENAME.format(phase=phase)
    path = report_dir / filename
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8").strip()
            return _truncate_prior_context(text)
        except OSError:
            return ""

    if phase == "purpose":
        parts: List[str] = []
        for prev_phase in ("values", "strengths", "interests"):
            prev_path = report_dir / _PRIOR_CONTEXT_FILENAME.format(phase=prev_phase)
            if prev_path.exists():
                try:
                    text = prev_path.read_text(encoding="utf-8").strip()
                    if text:
                        parts.append(f"【{prev_phase} 阶段结果】\n{text}")
                except OSError:
                    pass
        if parts:
            return _truncate_prior_context("\n\n".join(parts))

    if phase == "rumination":
        phase_labels = {"values": "信念", "strengths": "禀赋", "interests": "热忱", "purpose": "使命"}
        parts = []
        for prev_phase in ("values", "strengths", "interests", "purpose"):
            prev_path = report_dir / _PRIOR_CONTEXT_FILENAME.format(phase=prev_phase)
            if prev_path.exists():
                try:
                    text = prev_path.read_text(encoding="utf-8").strip()
                    if text:
                        label = phase_labels.get(prev_phase, prev_phase)
                        parts.append(f"【{label} 阶段结果】\n{text}")
                except OSError:
                    pass
        if parts:
            return _truncate_prior_context("\n\n".join(parts))

    return ""


def save_prior_context(session_id: str, phase: str, text: str, base_dir: str) -> None:
    """
    保存某阶段的上一轮咨询结果文本。

    Args:
        session_id: 会话 ID
        phase: 目标阶段（存在 strengths 或 interests 等）
        text: 上传或自动收集的文本
        base_dir: 存储根目录
    """
    base = Path(base_dir)
    session_dir = base / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    filename = _PRIOR_CONTEXT_FILENAME.format(phase=phase)
    (session_dir / filename).write_text(text, encoding="utf-8")


PRIOR_CONTEXT_MAX_CHARS = 2000


def load_prior_context(session_id: str, phase: str, base_dir: str) -> str:
    """
    加载某阶段的上一轮咨询结果文本。
    总长度超过 PRIOR_CONTEXT_MAX_CHARS 时截断，避免 prompt 过长。

    默认加载规则：
      - strengths 阶段 → 先查 prior_context_strengths.txt；
        若无，则尝试从 values 阶段的对话文件自动生成摘要（暂返回空，由前端上传）
      - interests 阶段 → 查 prior_context_interests.txt

    Returns:
        文本内容，找不到返回空字符串
    """
    base = Path(base_dir)
    session_dir = base / session_id
    filename = _PRIOR_CONTEXT_FILENAME.format(phase=phase)
    path = session_dir / filename
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8").strip()
            return _truncate_prior_context(text)
        except OSError:
            return ""

    # purpose 阶段 → 合并 values, strengths, interests
    if phase == "purpose":
        parts: List[str] = []
        for prev_phase in ("values", "strengths", "interests"):
            prev_path = session_dir / _PRIOR_CONTEXT_FILENAME.format(phase=prev_phase)
            if prev_path.exists():
                try:
                    text = prev_path.read_text(encoding="utf-8").strip()
                    if text:
                        parts.append(f"【{prev_phase} 阶段结果】\n{text}")
                except OSError:
                    pass
        if parts:
            return _truncate_prior_context("\n\n".join(parts))

    # rumination 阶段 → 合并 values, strengths, interests, purpose
    if phase == "rumination":
        phase_labels = {"values": "信念", "strengths": "禀赋", "interests": "热忱", "purpose": "使命"}
        parts = []
        for prev_phase in ("values", "strengths", "interests", "purpose"):
            prev_path = session_dir / _PRIOR_CONTEXT_FILENAME.format(phase=prev_phase)
            if prev_path.exists():
                try:
                    text = prev_path.read_text(encoding="utf-8").strip()
                    if text:
                        label = phase_labels.get(prev_phase, prev_phase)
                        parts.append(f"【{label} 阶段结果】\n{text}")
                except OSError:
                    pass
        if parts:
            return _truncate_prior_context("\n\n".join(parts))

    return ""


def _truncate_prior_context(text: str) -> str:
    """截断 prior context，避免 prompt 过长"""
    if not text or len(text) <= PRIOR_CONTEXT_MAX_CHARS:
        return text
    return text[:PRIOR_CONTEXT_MAX_CHARS] + "\n\n[... 内容已截断 ...]"


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
