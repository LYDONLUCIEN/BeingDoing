"""
Admin Mock 数据管理

常态化存储的 mock 数据，用于：
- 管理员调试时可快速进入 rumination 等阶段，无需完成前四轮
- 可将 data 中任意 report 的 prior 数据保存为 mock，供后续复用
- Mock 存储于 data/admin_mock/
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.simple_activation_manager import get_simple_base_dir
from app.utils.report_registry import ReportRegistry, STEP_IDS
from app.utils.survey_storage import load_prior_context, save_prior_context

ADMIN_MOCK_DIR_NAME = "admin_mock"
MOCK_SESSION_ID = "admin_mock"

# 默认 prior context（rumination 会合并；rumination_ops 从「信念/禀赋/热忱 阶段结果」后提取关键词）
DEFAULT_PRIOR_TEMPLATES = {
    "values": "核心价值观关键词：成就感、成长、创造、关系、意义。用户确认完成。",
    "strengths": "核心优势：沟通表达、逻辑分析、团队协作、学习能力、问题解决。用户确认5个优势。",
    "interests": "兴趣方向：职业发展、心理学、写作、教育、科技、个人成长。用户确认完成。",
    "purpose": "使命：帮助他人找到职业方向，实现自我价值。希望持续影响他人成长。",
}


def get_admin_mock_dir() -> Path:
    """Mock 数据根目录：data/admin_mock/"""
    base = get_simple_base_dir()
    return base.parent / ADMIN_MOCK_DIR_NAME


def get_mock_prior_dir() -> Path:
    """Mock prior context 目录"""
    return get_admin_mock_dir() / "prior_context"


def get_record_template_path() -> Path:
    """record 模板路径"""
    return get_admin_mock_dir() / "record_template.json"


def _ensure_mock_structure(force_overwrite: bool = False) -> None:
    """确保 mock 目录和默认文件存在。force_overwrite=True 时覆盖已有文件。"""
    mock_dir = get_admin_mock_dir()
    mock_dir.mkdir(parents=True, exist_ok=True)
    prior_dir = get_mock_prior_dir()
    prior_dir.mkdir(parents=True, exist_ok=True)

    # 默认 record 模板：前四阶段都有 selected_session_id
    template_path = get_record_template_path()
    if not template_path.exists() or force_overwrite:
        steps = {}
        for sid in STEP_IDS:
            steps[sid] = {
                "step_id": sid,
                "selected_session_id": MOCK_SESSION_ID if sid != "rumination" else None,
                "locked": sid != "rumination",
                "session_ids": [MOCK_SESSION_ID] if sid != "rumination" else [],
                "updated_at": "2024-01-01T00:00:00Z",
            }
        template = {
            "report_id": "admin_mock_template",
            "activation_code": "MOCK",
            "user_id": "admin",
            "steps": steps,
            "status": "in_progress",
            "final_conclusion": None,
        }
        template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    # 默认 prior context 文件
    for phase, content in DEFAULT_PRIOR_TEMPLATES.items():
        f = prior_dir / f"prior_context_{phase}.txt"
        if not f.exists() or force_overwrite:
            f.write_text(content, encoding="utf-8")


def init_mock_force() -> Dict[str, Any]:
    """强制初始化/重置 mock 数据为默认模板，供 rumination 测试使用。"""
    _ensure_mock_structure(force_overwrite=True)
    return get_mock_info()


def load_mock_record_template() -> Optional[Dict[str, Any]]:
    """加载 record 模板"""
    _ensure_mock_structure()
    p = get_record_template_path()
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_mock_info() -> Dict[str, Any]:
    """获取 mock 数据信息"""
    _ensure_mock_structure()
    template = load_mock_record_template()
    prior_dir = get_mock_prior_dir()
    prior_files = []
    for f in prior_dir.glob("prior_context_*.txt"):
        prior_files.append(f.name)
    return {
        "exists": template is not None,
        "record_template_path": str(get_record_template_path()),
        "prior_files": sorted(prior_files),
    }


def apply_mock_to_activation(activation_code: str, registry: ReportRegistry) -> Dict[str, Any]:
    """
    将 mock 数据应用到指定激活码的 report。
    用于满足 lock_previous_step 要求，使 init rumination 不再报 400。
    """
    from app.utils.simple_activation_manager import SimpleActivationManager

    _ensure_mock_structure()
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code.strip().upper())
    if not rec:
        raise ValueError("激活码不存在")

    # 需要 user_id 来获取 report
    reports = [r for r in registry.list_reports() if (r.get("activation_code") or "").upper() == activation_code.upper()]
    if not reports:
        raise ValueError("该激活码尚未有 report，请先激活或跳步")
    report = reports[0]
    report_id = report.get("report_id")
    if not report_id:
        raise ValueError("report 无 report_id")

    session_id = rec.session_id or str(report_id)
    simple_base = get_simple_base_dir()
    session_dir = simple_base / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # 1. 应用 record 模板：为未完成的阶段设置 selected_session_id
    template = load_mock_record_template()
    applied_steps = []
    for step in ("values", "strengths", "interests", "purpose"):
        st = (report.get("steps") or {}).get(step, {})
        if st.get("selected_session_id"):
            continue
        try:
            registry.bind_session(report_id, step, MOCK_SESSION_ID)
            registry.select_session(report_id, step, MOCK_SESSION_ID)
            registry.lock_step(report_id, step)
            applied_steps.append(step)
        except ValueError:
            pass

    # 2. 复制 prior context 到激活码的 session 目录
    prior_dir = get_mock_prior_dir()
    copied_prior = []
    for f in prior_dir.glob("prior_context_*.txt"):
        dst = session_dir / f.name
        shutil.copy2(f, dst)
        copied_prior.append(f.name)

    return {
        "activation_code": activation_code,
        "report_id": report_id,
        "applied_steps": applied_steps,
        "copied_prior": copied_prior,
    }


def save_report_as_mock(
    activation_code: Optional[str] = None,
    report_id: Optional[str] = None,
    registry: Optional[ReportRegistry] = None,
) -> Dict[str, Any]:
    """
    将指定 report 的 prior 数据保存为 mock，供后续 apply 使用。
    可从 data 里任选一份历史数据替换现有 mock。
    """
    from app.utils.simple_activation_manager import SimpleActivationManager

    _ensure_mock_structure()
    reg = registry or ReportRegistry()
    manager = SimpleActivationManager()

    if report_id:
        report = reg.get_report_by_id(report_id)
    elif activation_code:
        reports = [r for r in reg.list_reports() if (r.get("activation_code") or "").upper() == activation_code.upper()]
        report = reports[0] if reports else None
    else:
        raise ValueError("需提供 activation_code 或 report_id")

    if not report:
        raise ValueError("未找到对应 report")

    rid = report.get("report_id")
    if not rid:
        raise ValueError("report 无 report_id")

    simple_base = get_simple_base_dir()
    prior_dir = get_mock_prior_dir()
    prior_dir.mkdir(parents=True, exist_ok=True)

    # prior context 按 activation.session_id 存于 data/simple/{session_id}/
    ac = (report.get("activation_code") or "").strip()
    rec = manager.get_activation(ac) if ac else None
    session_id = rec.session_id if rec else None

    saved = []
    steps = report.get("steps") or {}
    for phase in ("values", "strengths", "interests", "purpose"):
        text = ""
        if session_id:
            text = load_prior_context(session_id, phase, str(simple_base))
        if not text.strip():
            st = steps.get(phase, {})
            sess_id = st.get("selected_session_id")
            if sess_id:
                text = load_prior_context(sess_id, phase, str(simple_base))
        if not text.strip():
            st = steps.get(phase, {})
            sess_id = st.get("selected_session_id")
            if sess_id:
                conv_file = simple_base / "reports" / rid / f"{phase}__{sess_id}.json"
                if conv_file.exists():
                    try:
                        data = json.loads(conv_file.read_text(encoding="utf-8"))
                        msgs = data.get("messages") or []
                        parts = [str(m["content"])[:500] for m in msgs if m.get("role") == "assistant" and m.get("content")]
                        if parts:
                            text = "\n\n".join(parts)
                    except Exception:
                        pass
        if text.strip():
            dst = prior_dir / f"prior_context_{phase}.txt"
            dst.write_text(text[:8000], encoding="utf-8")
            saved.append(phase)
        else:
            # 无内容时保留默认模板
            default = DEFAULT_PRIOR_TEMPLATES.get(phase, "")
            if default:
                dst = prior_dir / f"prior_context_{phase}.txt"
                dst.write_text(default, encoding="utf-8")

    # 更新 record 模板
    steps = report.get("steps") or {}
    template = {
        "report_id": "admin_mock_template",
        "activation_code": "MOCK",
        "user_id": "admin",
        "steps": {},
        "status": "in_progress",
        "final_conclusion": None,
    }
    for sid in STEP_IDS:
        st = (steps.get(sid) or {}).copy()
        if isinstance(st.get("session_ids"), list):
            st["session_ids"] = list(st["session_ids"])
        st.setdefault("step_id", sid)
        st.setdefault("selected_session_id", MOCK_SESSION_ID if sid != "rumination" else None)
        st.setdefault("locked", sid != "rumination")
        st.setdefault("session_ids", [MOCK_SESSION_ID] if sid != "rumination" else [])
        template["steps"][sid] = st
    get_record_template_path().write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "report_id": rid,
        "activation_code": report.get("activation_code"),
        "saved_prior_phases": saved,
    }
