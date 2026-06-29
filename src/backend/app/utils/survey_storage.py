"""
调研问卷存储工具

basic_info 以用户维度存储：data/user/{user_id}/basic_info.json（仅保留最新 1 份）
prior_context 以 report 维度存储：reports/{report_id}/prior_context_{phase}.txt

各维度**已确认结论卡**另存统一快照：reports/{report_id}/dimension_conclusions.json
供 prior_block 与 purpose 阶段 values_info 等统一读取；缺失时回退 legacy txt。

保留旧 session_id 接口用于迁移期回退。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.domain.conclusion_card_goals import cap_strengths_keywords_list
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


def _basic_info_has_content(data: Dict[str, Any]) -> bool:
    """判断 basic_info 是否包含有效内容（不止空壳）"""
    if not data or not isinstance(data, dict):
        return False
    meaningful_keys = {"gender", "age", "nickname", "career_status", "industry", "position"}
    for k in meaningful_keys:
        v = data.get(k)
        if v is not None and v != "":
            return True
    return False


async def save_basic_info_by_user(user_id: str, data: Dict[str, Any]) -> None:
    """
    按用户保存调研问卷（主入口，仅保留最新 1 份）。
    同步更新数据库 user_profiles 表，确保 admin 面板能正确展示。

    数据一致性策略：**先 DB 后 JSON**。
    - DB 是 admin / 列表查询的真实数据源，必须先成功；
    - JSON 文件作为本地缓存（供 prompt 拼接 / load_basic_info_by_user 读取）；
    - DB 失败时直接 raise，JSON 不写，让上层 API 返回错误、前端可重试；
    - DB 成功后 JSON 写失败也 raise（保证两者最终一致，不出现「DB 有 JSON 无」的中间态）。

    修复历史 bug：原实现用 loop.create_task 后台异步写库且 except: pass 吞掉异常，
    导致 UserProfile 表可能不更新 → admin /admin/users 查不到老用户已填 profile。

    Args:
        user_id: 用户 ID
        data: 调研数据字典

    Raises:
        Exception: DB 或 JSON 写入失败时向上冒泡，调用方应感知并返回错误。
    """
    from app.core.database.user_db import UserDB
    from app.models.database import AsyncSessionLocal

    gender = data.get("gender") if data else None
    profile_completed = _basic_info_has_content(data) if data else False

    # 1) 先写数据库（source of truth）
    async with AsyncSessionLocal() as db:
        user_db = UserDB(db)
        await user_db.update_user_profile(
            user_id=user_id,
            gender=gender,
            profile_completed=profile_completed,
        )

    # 2) DB 成功后再写 JSON 缓存（保持一致性；失败也 raise，避免不一致）
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


def merge_basic_info_sources(sources: List[Dict[str, Any]], strategy: str = "A") -> Dict[str, Any]:
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

# 四维结论卡统一快照（仅含 values/strengths/interests/purpose）
DIMENSION_CONCLUSIONS_FILENAME = "dimension_conclusions.json"
DIMENSION_PHASE_IDS: Tuple[str, ...] = ("values", "strengths", "interests", "purpose")
DIMENSION_LABEL_CN: Dict[str, str] = {
    "values": "价值观",
    "strengths": "优势",
    "interests": "热爱",
    "purpose": "使命",
}
# 合并多阶段结论文本时的上限（略高于单文件 PRIOR_CONTEXT_MAX_CHARS）
PRIOR_UNIFIED_MAX_CHARS = 4800


def _get_prior_context_path_for_report(report_id: str, phase: str, reports_root: Path) -> Path:
    """report 维度 prior_context 路径：reports/{report_id}/prior_context_{phase}.txt"""
    root = Path(reports_root)
    report_dir = root / report_id
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / _PRIOR_CONTEXT_FILENAME.format(phase=phase)


def save_prior_context_for_report(report_id: str, phase: str, text: str, reports_root: str) -> None:
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


def _dimension_conclusions_path(report_id: str, reports_root: str) -> Path:
    return Path(reports_root) / report_id / DIMENSION_CONCLUSIONS_FILENAME


def load_dimension_conclusions(report_id: str, reports_root: str) -> Dict[str, Dict[str, Any]]:
    """加载 report 下已确认的四维结论卡快照（按 phase 键）。"""
    path = _dimension_conclusions_path(report_id, reports_root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for k in DIMENSION_PHASE_IDS:
        v = raw.get(k)
        if isinstance(v, dict) and v:
            out[k] = v
    return out


def merge_dimension_conclusion_record(
    report_id: str, phase_step: str, conclusion: Dict[str, Any], reports_root: str
) -> None:
    """将某维已确认结论写入/更新 dimension_conclusions.json（整文件重写）。"""
    if phase_step not in DIMENSION_PHASE_IDS:
        return
    if not isinstance(conclusion, dict):
        return
    cur = load_dimension_conclusions(report_id, reports_root)
    cur[phase_step] = dict(conclusion)
    path = _dimension_conclusions_path(report_id, reports_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: cur[k] for k in DIMENSION_PHASE_IDS if k in cur}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def format_conclusion_prior_block(phase_step: str, conclusion: Dict[str, Any]) -> str:
    """单维结论文本块（与 thread/complete 写入 prior 的格式一致）。"""
    summary = (conclusion.get("summary") or conclusion.get("ai_summary") or "").strip()
    keywords = conclusion.get("keywords") or []
    if isinstance(keywords, list):
        kw_for_prior = (
            cap_strengths_keywords_list(keywords) if phase_step == "strengths" else keywords
        )
        kw_text = "、".join(str(k) for k in kw_for_prior)
    else:
        kw_text = str(keywords)
    prior_text = f"{summary}\n关键词：{kw_text}".strip() if (summary or kw_text) else ""
    if not prior_text:
        return ""
    label = DIMENSION_LABEL_CN.get(phase_step, phase_step)
    return f"【{label} 阶段结果】\n{prior_text}"


def _prior_phases_before(phase: str) -> List[str]:
    """当前阶段之前应注入 prompt 的维度顺序列表。"""
    if phase == "values":
        return []
    if phase == "strengths":
        return ["values"]
    if phase == "interests":
        return ["values", "strengths"]
    if phase == "purpose":
        return ["values", "strengths", "interests"]
    if phase == "rumination":
        return list(DIMENSION_PHASE_IDS)
    return []


def _truncate_prior_unified(text: str) -> str:
    if not text or len(text) <= PRIOR_UNIFIED_MAX_CHARS:
        return text
    return text[: PRIOR_UNIFIED_MAX_CHARS - 36] + "\n\n[... 前置阶段结论已截断 ...]"


def build_prior_context_from_dimension_store(
    report_id: str, current_phase: str, reports_root: str
) -> str:
    """从 dimension_conclusions.json 拼接当前阶段所需的全部前置维结论。"""
    needed = _prior_phases_before(current_phase)
    if not needed:
        return ""
    store = load_dimension_conclusions(report_id, reports_root)
    parts: List[str] = []
    for p in needed:
        block = format_conclusion_prior_block(p, store.get(p) or {})
        if block:
            parts.append(block)
    if not parts:
        return ""
    return _truncate_prior_unified("\n\n".join(parts))


def build_values_info_for_prompt(report_id: str, reports_root: str, *, max_chars: int = 960) -> str:
    """
    purpose 阶段注入：关键词 + 与 keywords 对齐的 keyword_notes（含义），供模型理解；
    系统提示仍要求对用户口述时只列关键词。
    """
    store = load_dimension_conclusions(report_id, reports_root)
    vc = store.get("values")
    if not isinstance(vc, dict):
        return ""
    kws_in = vc.get("keywords") or []
    if not isinstance(kws_in, list):
        return ""
    kws = [str(x).strip() for x in kws_in if str(x).strip()]
    if not kws:
        return ""
    notes_in = vc.get("keyword_notes")
    notes: List[str] = []
    if isinstance(notes_in, list):
        notes = [str(x).strip() for x in notes_in]
    pieces: List[str] = []
    for i, kw in enumerate(kws):
        note = notes[i] if i < len(notes) else ""
        if note:
            pieces.append(f"{kw}（用户对该词的说明：{note}）")
        else:
            pieces.append(kw)
    s = "、".join(pieces)
    if len(s) > max_chars:
        return s[: max_chars - 1] + "…"
    return s


def load_prior_context_for_report(report_id: str, phase: str, reports_root: str) -> str:
    """
    按 report 加载上一轮咨询结果。purpose/rumination 会合并前置阶段。

    Returns:
        文本内容，找不到返回空字符串
    """
    unified = build_prior_context_from_dimension_store(report_id, phase, reports_root)
    if unified.strip():
        return unified

    root = Path(reports_root)
    report_dir = root / report_id
    filename = _PRIOR_CONTEXT_FILENAME.format(phase=phase)
    path = report_dir / filename
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return _truncate_prior_context(text)
        except OSError:
            pass

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
        phase_labels = dict(DIMENSION_LABEL_CN)
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
        phase_labels = dict(DIMENSION_LABEL_CN)
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
