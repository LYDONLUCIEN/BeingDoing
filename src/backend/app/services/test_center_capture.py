"""从 dev 调试工作区读取当前对话起点，返回待人工脱敏的预览，不改写业务状态。"""

import json
import re
from pathlib import Path

from app.services.test_center_ai import ContextSpec
from app.services.test_center_workflow import PHASES


def read_object(path, root, observed):
    """只读既有文件，不使用会创建目录的加载入口。"""
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ValueError("上下文文件路径越界")
    if not path.exists():
        observed[path] = None
        return {}
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("上下文文件无效或过大")
    observed[path] = path.read_bytes()
    value = json.loads(observed[path])
    if not isinstance(value, dict):
        raise ValueError("上下文数据必须为对象")
    return value


def workflow_seed(root, folder, rec, report, phase, metadata, observed):
    from app.utils.data_paths import get_user_data_dir
    from app.utils.id_codec import IDCodec

    user_root = get_user_data_dir()
    uid = getattr(rec, "owner_user_id", None) or getattr(rec, "owner_email", None)
    basic = read_object(user_root / uid / "basic_info.json", user_root, observed) if uid else {}
    if not basic:
        basic = read_object(
            root / IDCodec.activation_session_id_from_rec(rec) / "basic_info.json", root, observed
        )
    conclusions = read_object(folder / "dimension_conclusions.json", folder, observed)
    return {
        "completed_phases": [
            p
            for p in PHASES[: PHASES.index(phase)]
            if report.get("steps", {}).get(p, {}).get("locked")
        ],
        "basic_info": basic,
        "conclusions": {
            p: c for p, c in conclusions.items() if p in PHASES[:-1] and isinstance(c, dict)
        },
        "thread_metadata": metadata,
        "anchor": report.get("steps", {}).get(phase, {}).get("anchor_summary") or {},
    }


def preview(body):
    from app.api.v1 import simple_chat_routes as chat
    from app.utils import simple_activation_manager as storage
    from app.utils.admin_savepoints import _find_report_for_activation
    from app.utils.report_registry import ReportRegistry

    code = body["activation_code"].strip().upper()
    phase, thread_id = body["phase"], body["thread_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", thread_id):
        raise ValueError("线程/组合 ID 格式无效")
    base = storage.get_simple_test_base_dir().resolve()
    rec = storage.SimpleActivationManager(base_dir=str(base)).get_activation(code)
    if not rec or not storage.is_debug_workspace_record(rec):
        raise ValueError("只允许读取已存在的 dev 调试工作区激活码")
    relative = getattr(rec, "workspace_root", None) or getattr(rec, "sandbox_root", None) or ""
    root = (base / relative).resolve()
    if not root.is_relative_to(base) or not root.is_dir():
        raise ValueError("调试工作区数据根无效")
    registry = ReportRegistry(base_dir=str(root))
    report = _find_report_for_activation(registry, code, rec)
    if not report:
        raise ValueError("未找到调试报告")
    rid = report["report_id"]
    folder = (root / "reports" / rid).resolve()
    if not folder.is_relative_to(root / "reports") or not folder.is_dir():
        raise ValueError("报告数据根无效")
    path = folder / (
        "rumination_v4_progress.json" if phase == "rumination" else f"{phase}__{thread_id}.json"
    )
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("目标对话不存在或大小超限")
    before = path.read_bytes()
    data = json.loads(before)
    observed = {path: before}
    # 预览同一次读取得到的结构化状态；后续校验文件变化，不把文字背景当作业务状态。
    report = read_object(folder / "record.json", folder, observed)
    metadata = {}
    spec = {
        "name": body["name"],
        "phase": phase,
        "thread_id": thread_id,
        "source": "debug_workspace",
    }
    if phase == "rumination":
        from app.api.v1.rumination_v4_routes import _build_user_context

        combo = next(
            (c for c in data.get("combo_sessions", []) if c.get("combo_id") == thread_id),
            None,
        )
        if (
            not combo
            or combo.get("status") != "discussing"
            or (combo.get("balance_analysis") or {}).get("status") == "analyzing"
        ):
            raise ValueError("请选择未锁定、未分析中的 v4 组合")
        selected = {
            k: combo[k]
            for k in (
                "combo_id",
                "passion",
                "strengths",
                "status",
                "summary",
                "summary_last_round",
                "reopen_feedback",
            )
            if k in combo and combo[k] is not None
        }
        selected["messages"] = clean_messages(combo.get("messages", []))
        selected["conclusion_card"] = {
            "hypothesis": (combo.get("conclusion_card") or {}).get("hypothesis") or ""
        }
        context, values = _build_user_context(root / "reports", rid, rec, code)
        spec.update(combo=selected, user_context=context, values_keywords=values or [])
    else:
        from app.domain.conclusion_card_payload import build_conclusion_state_injection
        from app.utils.purpose_progress import (
            build_progress_injection,
            normalize_progress,
        )

        meta = data.get("metadata") or {}
        state = chat._read_conclusion_meta(meta)
        if state.get("thread_completed") or state.get("state") in {
            "pending",
            "confirmed",
        }:
            raise ValueError(
                "该线程处于确认/锁定流程，请用业务用例测试状态转换；单轮提示词回放需可继续对话的起点"
            )
        anchor = chat.load_anchor_for_phase(rid, phase, str(root))
        feedback = state.get("feedback") or ""
        count = sum(m.get("role") == "user" for m in data.get("messages", []))
        baseline = int(meta.get("conclusion_reject_baseline_user_count") or count)
        metadata = {
            "conclusion_state": state.get("state") or "none",
            "conclusion_draft": state.get("draft"),
            "conclusion_final": state.get("final"),
            "conclusion_feedback": feedback,
            "thread_completed": bool(state.get("thread_completed")),
            "conclusion_shown_at_turn": state.get("shown_at"),
            "conclusion_reject_baseline_user_count": baseline,
            **(
                {"purpose_progress": normalize_progress(meta.get("purpose_progress"))}
                if phase == "purpose"
                else {}
            ),
        }
        spec.update(
            messages=clean_messages(chat._trim_history_messages_for_llm(data.get("messages", []))),
            question_bank=meta.get("question_bank") or "",
            basic_info=chat._load_basic_info_from_activation(code),
            prior_context=chat._load_prior_context_from_activation(code, phase, report),
            values_info=chat._values_info_for_phase(phase, report, str(root / "reports")),
            anchor_text=chat.format_anchor_for_prompt(anchor),
            purpose_progress_injection=(
                build_progress_injection(normalize_progress(meta.get("purpose_progress")))
                if phase == "purpose"
                else ""
            ),
            conclusion_state_injection=build_conclusion_state_injection(
                phase,
                state.get("state") or "none",
                draft=state.get("draft"),
                feedback=feedback,
                turns_since_reject=max(0, count + 1 - baseline),
            ),
        )
    spec["workflow_seed"] = workflow_seed(root, folder, rec, report, phase, metadata, observed)
    for file, content in observed.items():
        if (file.read_bytes() if file.exists() else None) != content:
            raise ValueError("上下文正在更新，请等待当前回复结束后重新读取")
    return ContextSpec.model_validate(spec).model_dump()


def clean_messages(messages):
    return [
        {"role": m["role"], "content": m.get("content") or ""}
        for m in messages
        if m.get("role") in {"user", "assistant", "system"}
    ]
