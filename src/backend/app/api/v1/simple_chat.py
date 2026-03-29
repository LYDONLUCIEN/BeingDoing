"""
简单模式对话 API

特点：
- 不使用 LangGraph
- 通过一个较长的 system_prompt + 历史消息，分模块（values/strengths/interests）引导用户
- 会话由「激活码」标识，对话历史保存在 data/simple 下
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence, Tuple
import asyncio
import json
import random
import logging
import re

from fastapi import APIRouter, HTTPException, Query, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.core.llmapi.factory import create_llm_provider
from app.api.v1.auth import get_current_user, _is_debug_admin
from app.config.settings import settings
from app.core.knowledge.loader import KnowledgeLoader
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    ActivationStatus,
    bind_session_id_for_ensure_report,
    get_effective_simple_root,
    get_activation_manager_for_code,
    get_activation_with_manager,
)
from app.utils.sandbox_fork import assert_sandbox_not_expired
from app.utils.conversation_file_manager import ConversationFileManager
from app.core.dimension_completion_checker import (
    check_dimension_complete,
)
from app.services.analytics_service import AnalyticsService
from app.utils.report_registry import ReportRegistry, STEP_IDS, STEP_ORDER
from app.utils.rumination_progress import (
    load_rumination_progress,
    save_rumination_progress,
)
from app.utils.rumination_ops import (
    build_prior_keywords_summary,
    extract_from_prior_context,
    filter_match,
    filter_strength,
    gen_table,
    generate_hypotheses_round2_table,
    generate_hypotheses_round3_finalize,
    merge_row_by_id,
    passion_filter,
    reality_filter,
    similar_filter,
    structure_hypothesis_round1_table,
    value_filter,
)
from app.utils.rumination_hypothesis_service import fill_hypothesis_columns_for_table
from app.utils.rumination_table_widgets import (
    build_table_widget_payload,
    slice_rows_for_display,
)
from app.utils.context_refiner import (
    refine_and_save_anchor,
    format_anchor_for_prompt,
    load_anchor_for_phase,
)
from app.utils.survey_storage import (
    save_basic_info_by_user,
    load_basic_info_by_user,
    load_basic_info,
    format_basic_info_for_prompt,
    save_prior_context_for_report,
    load_prior_context_for_report,
    load_prior_context,
)
from app.domain.prompts import get_simple_chat_system_prompt
from app.utils.admin_policy import is_admin_debug_policy_enabled
from app.utils.admin_prompt_lab import resolve_simple_chat_prompt_override
from app.utils.admin_policy import is_admin_sandbox_enabled
from app.utils.super_admin import is_super_admin_user
from jinja2 import Environment

# 每阶段随机抽取的题目数量
SIMPLE_QUESTION_SAMPLE_SIZE = 6
# 发送给 LLM 的历史消息最大轮数（减少 token、加快响应）
MAX_HISTORY_TURNS = 30
# 并发 LLM 调用限制（0=不限制）
_LLM_SEM = None
PENDING_JUDGE_TIMEOUT_SECONDS = 20
CONCLUSION_GEN_TIMEOUT_SECONDS = 25
PENDING_HEARTBEAT_SECONDS = 2.0
CONCLUSION_STATE_NONE = "none"
CONCLUSION_STATE_PENDING = "pending"
CONCLUSION_STATE_CONFIRMED = "confirmed"
CONCLUSION_STATE_REJECTED = "rejected"


def _get_llm_semaphore():
    global _LLM_SEM
    if _LLM_SEM is None:
        n = getattr(settings, "LLM_MAX_CONCURRENT", 0) or 0
        _LLM_SEM = asyncio.Semaphore(n) if n > 0 else None
    return _LLM_SEM


def _resolve_provider_and_key_for_vip(vip_level: int) -> tuple[str, Optional[str], Optional[str]]:
    """按 vip_level 解析 provider/api_key/base_url。"""
    level = 1 if vip_level not in (1, 2) else vip_level
    if level == 2:
        provider = (getattr(settings, "LLM_VIP2_PROVIDER", "kimi") or "kimi").lower()
        if provider == "qwen":
            return (
                "qwen",
                getattr(settings, "QWEN_API_KEY", None),
                getattr(settings, "QWEN_BASE_URL", None),
            )
        return (
            "kimi",
            getattr(settings, "KIMI_API_KEY", None),
            getattr(settings, "KIMI_BASE_URL", None),
        )

    provider = (getattr(settings, "LLM_VIP1_PROVIDER", "deepseek") or "deepseek").lower()
    if provider == "deepseek":
        return ("deepseek", getattr(settings, "DEEPSEEK_API_KEY", None), settings.LLM_BASE_URL)
    if provider == "openai":
        return ("openai", getattr(settings, "OPENAI_API_KEY", None), settings.LLM_BASE_URL)
    return (provider, getattr(settings, "DEEPSEEK_API_KEY", None), settings.LLM_BASE_URL)


def _to_non_reasoning_model(model: str) -> str:
    """
    将推理模型名转换为对话模型名。
    示例：deepseek-reasoner -> deepseek-chat
    """
    m = (model or "").strip()
    if not m:
        return "deepseek-chat"
    if "reasoner" in m.lower():
        return re.sub(r"reasoner", "chat", m, flags=re.IGNORECASE)
    return m


def _to_reasoning_model(model: str) -> str:
    """
    将对话模型名转换为推理模型名。
    示例：deepseek-chat -> deepseek-reasoner
    """
    m = (model or "").strip()
    if not m:
        return "deepseek-reasoner"
    if "reasoner" in m.lower():
        return m
    if "chat" in m.lower():
        return re.sub(r"chat", "reasoner", m, flags=re.IGNORECASE)
    return "deepseek-reasoner"


def _get_dialogue_llm_provider(vip_level: int = 1):
    """
    普通对话使用非思考模型；结论卡生成链路再使用推理模型。
    """
    llm = get_default_llm_provider(vip_level=vip_level)
    model = (getattr(llm, "model", "") or "").lower()
    if "reasoner" not in model:
        return llm
    provider, api_key, base_url = _resolve_provider_and_key_for_vip(vip_level)
    dialog_model = _to_non_reasoning_model(getattr(llm, "model", "") or "deepseek-chat")
    try:
        return create_llm_provider(
            provider=provider,
            model=dialog_model,
            api_key=api_key,
            base_url=base_url,
        )
    except Exception:
        # 降级：保持可用性，避免因切换失败阻断主对话
        return llm


def _get_reasoning_llm_provider(vip_level: int = 1):
    """
    结论判定/结论卡生成使用推理模型；普通对话用 _get_dialogue_llm_provider。
    """
    llm = get_default_llm_provider(vip_level=vip_level)
    model = (getattr(llm, "model", "") or "").lower()
    if "reasoner" in model:
        return llm
    provider, api_key, base_url = _resolve_provider_and_key_for_vip(vip_level)
    reasoning_model = _to_reasoning_model(getattr(llm, "model", "") or "deepseek-reasoner")
    try:
        return create_llm_provider(
            provider=provider,
            model=reasoning_model,
            api_key=api_key,
            base_url=base_url,
        )
    except Exception:
        return llm


router = APIRouter(prefix="/simple-chat", tags=["简单模式对话"])
logger = logging.getLogger(__name__)


def _trigger_anchor_refiner(
    report_id: str,
    phase: str,
    category: str,
    conv_manager: ConversationFileManager,
    storage_root: str,
    dimension_conclusion: Optional[dict] = None,
    round_count: Optional[int] = None,
    vip_level: int = 1,
) -> None:
    """后台触发锚点摘要提炼（不阻塞）"""
    prior = load_anchor_for_phase(report_id, phase, storage_root)

    async def _run():
        try:
            await refine_and_save_anchor(
                report_id=report_id,
                phase=phase,
                category=category,
                conv_manager=conv_manager,
                base_dir=storage_root,
                dimension_conclusion=dimension_conclusion,
                prior_anchor=prior,
                round_count=round_count,
                vip_level=vip_level,
            )
        except Exception as e:
            logger.warning("anchor refiner failed: %s", e)

    asyncio.create_task(_run())


async def _get_or_create_thread_question_bank(
    conv_manager: ConversationFileManager,
    session_id: str,
    category: str,
    phase_step: str,
) -> str:
    """线程级固定 question_bank：首次生成并写入 metadata，后续复用。"""
    if phase_step == "rumination":
        conv_data = await conv_manager.get_conversation_data(session_id, category)
        meta = conv_data.get("metadata") or {}
        qb = meta.get("question_bank")
        qb_phase = meta.get("question_bank_phase")
        if isinstance(qb, str) and qb_phase == phase_step:
            return qb
        qb = ""
        try:
            await conv_manager.update_metadata(
                session_id,
                category,
                {"question_bank": qb, "question_bank_phase": phase_step},
            )
        except Exception:
            pass
        return qb

    conv_data = await conv_manager.get_conversation_data(session_id, category)
    meta = conv_data.get("metadata") or {}
    qb = meta.get("question_bank")
    qb_phase = meta.get("question_bank_phase")
    if isinstance(qb, str) and qb.strip() and qb_phase == phase_step:
        return qb

    qb = _get_random_questions_for_phase(phase_step)
    try:
        await conv_manager.update_metadata(
            session_id,
            category,
            {
                "question_bank": qb,
                "question_bank_phase": phase_step,
            },
        )
    except Exception:
        # 仅优化项，失败时降级为本次使用，不影响主流程
        pass
    return qb


async def _append_note_json(
    conv_manager: ConversationFileManager,
    session_id: str,
    category: str,
    note_type: str,
    payload: Dict,
) -> None:
    """
    写入线程级额外结论文件（{report_id}/{category}__note/note.json），避免与主对话记录混写。
    """
    # 额外文件路径：{report_id}/{category}__note/note.json
    note_category = f"{category}__note/note"

    def _do(fp: Path) -> None:
        now = datetime.utcnow().isoformat() + "Z"
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {
                "session_id": session_id,
                "category": note_category,
                "notes": [],
                "metadata": {"created_at": now, "updated_at": now, "total_notes": 0},
            }
        notes = data.get("notes") or []
        notes.append(
            {
                "id": f"note_{len(notes) + 1}",
                "type": note_type,
                "payload": payload,
                "created_at": now,
            }
        )
        data["notes"] = notes
        meta = data.setdefault("metadata", {})
        meta["updated_at"] = now
        meta["total_notes"] = len(notes)
        fp.parent.mkdir(parents=True, exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))

    await conv_manager._with_file_lock(session_id, note_category, _do)


def _read_conclusion_meta(meta: Dict) -> Dict:
    """
    统一读取结论状态（优先新字段，兼容旧字段）。
    新字段：
      - conclusion_state: none|pending|confirmed|rejected
      - conclusion_draft: 待确认草案
      - conclusion_final: 最终结论
      - conclusion_feedback: 否定反馈
    """
    meta = meta or {}
    state = (meta.get("conclusion_state") or "").strip().lower()
    draft = meta.get("conclusion_draft")
    final = meta.get("conclusion_final")
    feedback = meta.get("conclusion_feedback")

    if not isinstance(draft, dict):
        legacy_draft = meta.get("pending_conclusion")
        draft = legacy_draft if isinstance(legacy_draft, dict) else None
    if not isinstance(final, dict):
        legacy_final = meta.get("dimension_conclusion")
        final = legacy_final if isinstance(legacy_final, dict) else None
    if not isinstance(feedback, str):
        legacy_rej = meta.get("pending_last_rejected") or {}
        fb = legacy_rej.get("feedback")
        feedback = fb if isinstance(fb, str) else ""

    if state not in {
        CONCLUSION_STATE_NONE,
        CONCLUSION_STATE_PENDING,
        CONCLUSION_STATE_CONFIRMED,
        CONCLUSION_STATE_REJECTED,
    }:
        if meta.get("thread_completed") and final:
            state = CONCLUSION_STATE_CONFIRMED
        elif draft:
            state = CONCLUSION_STATE_PENDING
        elif feedback:
            state = CONCLUSION_STATE_REJECTED
        else:
            state = CONCLUSION_STATE_NONE

    return {
        "state": state,
        "draft": draft,
        "final": final,
        "feedback": feedback or "",
        "thread_completed": bool(meta.get("thread_completed")),
        "shown_at": meta.get("conclusion_shown_at_turn"),
    }


def _normalize_draft_for_dimension_card(draft: Dict) -> Dict:
    """将 STATE_JSON draft 规范为与结论卡 API 一致的结构，供前端展示与落盘。"""
    summary = (draft.get("summary") or draft.get("ai_summary") or "").strip()
    raw_kw = draft.get("keywords") or []
    if not isinstance(raw_kw, list):
        raw_kw = []
    keywords = [str(k).strip() for k in raw_kw if str(k).strip()]
    if not summary:
        summary = "请先确认以下总结是否准确。"
    fa = draft.get("final_answer")
    if not (isinstance(fa, str) and fa.strip()):
        fa = ", ".join(keywords) if keywords else summary
    return {
        "summary": summary,
        "keywords": keywords,
        "ai_summary": summary,
        "dimension_goal": (draft.get("dimension_goal") or "").strip(),
        "final_answer": fa,
    }


def _build_conclusion_meta_update(
    *,
    state: str,
    draft: Optional[Dict] = None,
    final: Optional[Dict] = None,
    feedback: Optional[str] = None,
    shown_at: Optional[int] = None,
    thread_completed: Optional[bool] = None,
) -> Dict:
    """写入统一结论状态，同时镜像旧字段做兼容。"""
    is_confirmed = state == CONCLUSION_STATE_CONFIRMED
    is_pending = state == CONCLUSION_STATE_PENDING
    is_rejected = state == CONCLUSION_STATE_REJECTED
    update = {
        "conclusion_state": state,
        "conclusion_draft": draft if is_pending else None,
        "conclusion_final": final if final else None,
        "conclusion_feedback": (feedback or "") if is_rejected else "",
        "thread_completed": (is_confirmed if thread_completed is None else bool(thread_completed)),
        # 旧字段兼容
        "pending_status": (
            "awaiting_confirmation"
            if is_pending
            else "confirmed"
            if is_confirmed
            else "rejected"
            if is_rejected
            else "none"
        ),
        "pending_conclusion": draft if is_pending else None,
        "dimension_conclusion": final if final else None,
        "pending_last_rejected": {"feedback": feedback or ""} if is_rejected else {},
    }
    if shown_at is not None:
        update["conclusion_shown_at_turn"] = shown_at
    return update


def _write_anchor_from_conclusion(
    report_id: str,
    phase_step: str,
    storage_root: str,
    conclusion: Optional[Dict],
) -> None:
    """
    结论卡确认后，直接将结论写成最新锚点（同时保留常规异步锚点提炼机制）。
    """
    if not isinstance(conclusion, dict):
        return
    summary = (conclusion.get("summary") or conclusion.get("ai_summary") or "").strip()
    keywords = conclusion.get("keywords") or []
    kw_text = "、".join([str(k).strip() for k in keywords if str(k).strip()][:10])
    goals = summary
    if kw_text:
        goals = f"{summary}\n关键词：{kw_text}".strip()
    if not goals:
        return
    try:
        registry = ReportRegistry(base_dir=storage_root)
        registry.update_step_anchor_summary(
            report_id,
            phase_step,
            {
                "goals": goals,
                "personality": "",
                "style": "",
                "conflicts": "",
            },
        )
    except Exception:
        pass


def _skip_expired_for_debug(rec, user: Optional[dict]) -> bool:
    """Debug 管理员可跳过过期检查"""
    return (
        getattr(settings, "DEBUG_MODE", False)
        and _is_debug_admin(user)
        and rec.status == ActivationStatus.EXPIRED
    )


def _is_super_admin_user(user: Optional[dict]) -> bool:
    return is_super_admin_user(user)


def _can_bypass_flow_limits(current_user: Optional[dict], rec) -> bool:
    """
    管理员调试豁免（受统一 policy 开关控制）：
    - 用户必须是 super_admin
    - 激活码必须是调试工作区（fork/resident）
    """
    if not is_admin_debug_policy_enabled():
        return False
    if not _is_super_admin_user(current_user):
        return False
    workspace_kind = (getattr(rec, "workspace_kind", None) or "").strip().lower()
    if workspace_kind in {"fork", "resident"}:
        return True
    # 兼容旧沙箱记录（尚未回填 workspace_kind）
    return bool(getattr(rec, "is_sandbox", False))


def _resolve_prompt_lab_override_for_request(rec, current_user: Optional[dict]) -> Optional[Dict]:
    """
    sandbox_only：仅 super_admin + 调试工作区 + policy 开启时生效。
    """
    if not is_admin_sandbox_enabled():
        return None
    if not _is_super_admin_user(current_user):
        return None
    workspace_kind = (getattr(rec, "workspace_kind", None) or "").strip().lower()
    is_workspace = workspace_kind in {"fork", "resident"} or bool(getattr(rec, "is_sandbox", False))
    if not is_workspace:
        return None
    resolved = resolve_simple_chat_prompt_override(getattr(rec, "code", ""))
    if not resolved:
        return None
    template, extra_goal_hint, meta = resolved
    return {
        "template": template,
        "extra_goal_hint": extra_goal_hint,
        "meta": meta,
    }


def _storage_category(phase: str, session_id: str) -> str:
    """存储用 category：每个 step-session 一份文件。"""
    return f"{phase}__{session_id}"


def _step_session_message_count(
    registry: ReportRegistry, report_id: str, phase_step: str, sid: str
) -> int:
    """某 step 下 thread 对话文件中的消息条数（文件不存在为 0）。"""
    if not sid or not report_id:
        return 0
    path = registry.get_step_session_file(report_id, phase_step, sid)
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return len(data.get("messages") or [])
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def _resolve_default_logical_thread_id(
    registry: ReportRegistry,
    report: dict,
    phase_step: str,
    thread_id: Optional[str],
    activation_storage_session_id: str,
) -> str:
    """
    解析当前阶段使用的对话线程 id。

    前端未传 thread_id 时，不能简单用 rec.session_id：该 id 是「问卷/附属文件」命名空间，
    真实对话往往在 values__t_xxx.json。Fork 沙箱后 rec.session_id 为新 UUID，会误开空线程。
    策略：优先显式 thread_id → 已选 selected_session_id → session_ids 中消息数最多的文件
    → 再退到非 activation_storage_session_id 的候选 → 最后 rec.session_id。
    """
    tid = (thread_id or "").strip()
    if tid:
        return tid
    rid = (report.get("report_id") or "").strip()
    step = ((report.get("steps") or {}).get(phase_step)) or {}
    sel = (step.get("selected_session_id") or "").strip()
    if sel:
        return sel
    act_sid = (activation_storage_session_id or "").strip()
    candidates = [str(s).strip() for s in (step.get("session_ids") or []) if str(s).strip()]
    if not candidates:
        return act_sid
    best_sid = None
    best_n = -1
    for sid in candidates:
        n = _step_session_message_count(registry, rid, phase_step, sid)
        if n > best_n:
            best_n = n
            best_sid = sid
    if best_n > 0 and best_sid:
        return best_sid
    non_act = [s for s in candidates if s != act_sid]
    if non_act:
        return non_act[0]
    return act_sid


def _resolve_activation_for_user(
    manager: SimpleActivationManager,
    activation_code: str,
    current_user: dict,
):
    """激活码访问控制：首次使用绑定用户，后续仅归属用户可访问。"""
    rec = manager.get_activation(activation_code)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="激活码不存在",
        )
    if not manager.is_owner(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该激活码已被其他用户使用",
        )
    if rec.status in {ActivationStatus.REVOKED, ActivationStatus.DELETED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码不可用",
        )
    if not rec.owner_user_id and not rec.owner_email:
        rec = manager.claim_owner(rec.code, current_user)
    try:
        assert_sandbox_not_expired(rec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return rec


def _resolve_report_context(
    manager: SimpleActivationManager,
    activation_code: str,
    current_user: dict,
    phase: str,
    thread_id: Optional[str] = None,
):
    """
    统一解析：activation -> report -> step-session 存储上下文。
    沙箱激活码使用 data/test/simple/sandboxes/{fork_id}/ 作为存储根。
    """
    rec = _resolve_activation_for_user(manager, activation_code, current_user)
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.ensure_report(
        activation_code=rec.code,
        user_id=user_id,
        session_id=bind_session_id_for_ensure_report(rec),
    )
    if not report:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="报告初始化失败")

    phase_step = ReportRegistry.normalize_step_id(phase)
    logical_session_id = _resolve_default_logical_thread_id(
        registry,
        report,
        phase_step,
        thread_id,
        rec.session_id,
    )
    if not logical_session_id:
        logical_session_id = rec.session_id

    # 进入新阶段前，锁定上一阶段（管理员调试工作区可豁免，支持回退/跳步）
    if not _can_bypass_flow_limits(current_user, rec):
        try:
            registry.lock_previous_step_when_entering(report["report_id"], phase_step)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # 将当前会话纳入 step 的会话池
    registry.bind_session(report["report_id"], phase_step, logical_session_id)
    category = _storage_category(phase_step, logical_session_id)
    conv_manager = ConversationFileManager(base_dir=str(root / "reports"))
    return rec, report, phase_step, logical_session_id, category, conv_manager


def _phase_to_loader_category(phase: str) -> str:
    """simple_chat 的 phase 映射到 KnowledgeLoader 的 category"""
    if phase == "values":
        return "values"
    if phase == "strengths":
        return "strengths"
    if phase == "interests":
        return "interests"
    if phase == "purpose":
        return "values"  # purpose 阶段复用 values 题库，或可后续单独建
    if phase == "rumination":
        # 不在此加载题库；_get_or_create_thread_question_bank 对 rumination 直接返回空
        return "values"
    return "values"


def _get_random_questions_for_phase(phase: str, n: int = SIMPLE_QUESTION_SAMPLE_SIZE) -> str:
    """
    从 question.md 中按阶段加载问题，随机抽取 n 个，格式化为字符串。
     phase: values | strengths | interests
    """
    try:
        loader = KnowledgeLoader()
        all_questions = loader.load_questions()
        category = _phase_to_loader_category(phase)
        phase_questions = [q for q in all_questions if q.category == category]
        if not phase_questions:
            return "（暂无该阶段题库）"
        sampled = random.sample(phase_questions, min(n, len(phase_questions)))
        lines = [f"{i+1}. {q.content}" for i, q in enumerate(sampled)]
        return "\n".join(lines)
    except Exception:
        return "（题库加载失败）"


def _build_fallback_opening_question(phase: str) -> str:
    """当 LLM 不可用时，提供一个可继续流程的兜底开场问题。"""
    fallback_map = {
        "values": "我们先从价值观开始：最近一次让你“很有意义感”的事情是什么？为什么它对你重要？",
        "strengths": "我们先聊聊优势：在别人眼里，你最常被夸“做得自然且稳定”的一件事是什么？",
        "interests": "我们先聊热忱：哪类话题会让你不知不觉投入很久、并且越做越有能量？",
        "purpose": "我们先聊使命：如果你的工作能持续帮助一类人，你最希望他们发生什么改变？",
        "rumination": "恭喜你进入最后一轮！我们将综合你的价值观、优势、热爱和使命，帮你确定三个职业发展方向。准备好开始了吗？",
    }
    return fallback_map.get(phase, fallback_map["values"])


def _extract_json_object(text: str) -> Optional[Dict]:
    """从文本中提取首个 JSON object。"""
    if not text:
        return None
    s = text.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(s[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_state_content_tokens(text: str) -> Optional[Dict]:
    """从约定 token 中提取状态与展示文案。"""
    if not text:
        return None
    s = text.strip()
    state_match = re.search(r"<STATE>\s*(confirmed|rejected|continue)\s*</STATE>", s, flags=re.IGNORECASE)
    content_match = re.search(r"<CONTENT>\s*(.*?)\s*</CONTENT>", s, flags=re.IGNORECASE | re.DOTALL)
    if not state_match:
        return None
    state = (state_match.group(1) or "").strip().lower()
    content = (content_match.group(1) or "").strip() if content_match else ""
    return {"state": state, "content": content}


def _looks_like_markdown_table(text: str) -> bool:
    if not text:
        return False
    has_row = bool(re.search(r"^\s*\|.+\|\s*$", text, flags=re.MULTILINE))
    has_sep = bool(re.search(r"^\s*\|[\s:\-|]+\|\s*$", text, flags=re.MULTILINE))
    return has_row and has_sep


async def _decide_pending_action_by_llm(
    phase: str,
    pending_conclusion: Dict,
    user_reply: str,
    *,
    vip_level: int,
) -> Dict:
    """
    使用推理模型判断用户对 pending_conclusion 的态度，返回 JSON：
    {"state":"confirmed|rejected|continue","content":"..."}
    """
    llm = _get_reasoning_llm_provider(vip_level=vip_level)
    model_name = str(getattr(llm, "model", "") or "")
    is_reasoner = "reasoner" in model_name.lower()
    logger.info(
        "[pending_judge] phase=%s vip=%s model=%s is_reasoner=%s",
        phase,
        vip_level,
        model_name or "unknown",
        is_reasoner,
    )
    summary = (pending_conclusion or {}).get("summary") or (pending_conclusion or {}).get("ai_summary") or ""
    keywords = (pending_conclusion or {}).get("keywords") or []
    kw_text = "、".join([str(k).strip() for k in keywords if str(k).strip()][:10]) or "（无）"
    prompt = f"""你是职业咨询系统中的“确认状态判定器”。

当前阶段：{phase}
待确认总结摘要：{summary}
待确认关键词：{kw_text}
用户最新回复：{(user_reply or "").strip()}

请仅基于语义判断用户态度，输出 JSON（不要任何额外文字）：
{{
  "state": "confirmed | rejected | continue",
  "content": "给用户展示的一句话（20-80字）"
}}

判定要求：
1) 只有当用户明确同意当前总结内容时，state 才能是 confirmed。
2) 当用户表达不认可、希望调整、继续讨论时，state 为 rejected。
3) 无法明确同意或否定时，state 为 continue。
4) 像“嗯/好/行”等口头语，若缺乏明确语义，优先判为 continue。
"""
    token_prompt = f"""你是职业咨询系统中的“确认状态判定器”。

当前阶段：{phase}
待确认总结摘要：{summary}
待确认关键词：{kw_text}
用户最新回复：{(user_reply or "").strip()}

请严格输出以下两行，不要输出任何其他内容：
<STATE>confirmed|rejected|continue</STATE>
<CONTENT>给用户展示的一句话（20-80字）</CONTENT>

判定要求：
1) 只有当用户明确同意当前总结内容时，state 才能是 confirmed。
2) 当用户表达不认可、希望调整、继续讨论时，state 为 rejected。
3) 无法明确同意或否定时，state 为 continue。
4) 像“嗯/好/行”等口头语，若缺乏明确语义，优先判为 continue。
"""
    resp = None
    try:
        resp = await llm.chat(
            [LLMMessage(role="user", content=prompt)],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        # 某些 OpenAI-compatible 网关/SDK 对 response_format 支持不一致，降级为纯文本 JSON 提取
        logger.warning(
            "[pending_judge] JSON mode failed model=%s err_type=%s err=%s; fallback to plain text",
            model_name or "unknown",
            type(e).__name__,
            e,
        )
    if resp is None:
        try:
            resp = await llm.chat([LLMMessage(role="user", content=token_prompt)], temperature=0.1)
        except Exception as e:
            logger.warning(
                "[pending_judge] reasoner plain mode failed model=%s err_type=%s err=%s",
                model_name or "unknown",
                type(e).__name__,
                e,
            )
            resp = None

    raw_text = (resp.content or "").strip() if resp else ""
    obj = _extract_json_object(raw_text) or _extract_state_content_tokens(raw_text) or {}
    state = str(obj.get("state") or "continue").strip().lower()
    if state not in {"confirmed", "rejected", "continue"}:
        state = "continue"
    content = str(obj.get("content") or "").strip()
    if not content:
        # reasoner 在部分场景会出现空 content，退化到 chat 模型 + token 输出
        dialog_llm = _get_dialogue_llm_provider(vip_level=vip_level)
        dialog_model = str(getattr(dialog_llm, "model", "") or "")
        try:
            logger.info("[pending_judge] fallback_to_dialogue model=%s", dialog_model or "unknown")
            dialog_resp = await dialog_llm.chat(
                [LLMMessage(role="user", content=token_prompt)],
                temperature=0.1,
            )
            dialog_text = (dialog_resp.content or "").strip()
            dialog_obj = _extract_json_object(dialog_text) or _extract_state_content_tokens(dialog_text) or {}
            dialog_state = str(dialog_obj.get("state") or "").strip().lower()
            dialog_content = str(dialog_obj.get("content") or "").strip()
            if dialog_state in {"confirmed", "rejected", "continue"}:
                state = dialog_state
            if dialog_content:
                content = dialog_content
        except Exception as e:
            logger.warning(
                "[pending_judge] dialogue fallback failed model=%s err_type=%s err=%s",
                dialog_model or "unknown",
                type(e).__name__,
                e,
            )
    if not content:
        fallback = {
            "confirmed": "收到你的确认，我将生成结论卡。",
            "rejected": "明白了，我们继续补充完善这个维度。",
            "continue": "我还不确定你是否确认，我们继续聊一聊更稳妥。",
        }
        content = fallback[state]
    return {"state": state, "content": content}


async def _decide_pending_action_by_llm_streaming(
    phase: str,
    pending_conclusion: Dict,
    user_reply: str,
    *,
    vip_level: int,
    emit_event,
) -> Dict:
    """
    pending 判定的流式版本：
    - reasoner 模型走 chat_stream，实时透传 think_start/think_chunk/think_end
    - 同时收集 content 作为最终判定 JSON 文本
    - 若流式失败，降级到非流式判定逻辑
    """
    llm = _get_reasoning_llm_provider(vip_level=vip_level)
    model_name = str(getattr(llm, "model", "") or "")
    is_reasoner = "reasoner" in model_name.lower()
    summary = (pending_conclusion or {}).get("summary") or (pending_conclusion or {}).get("ai_summary") or ""
    keywords = (pending_conclusion or {}).get("keywords") or []
    kw_text = "、".join([str(k).strip() for k in keywords if str(k).strip()][:10]) or "（无）"
    token_prompt = f"""你是职业咨询系统中的“确认状态判定器”。

当前阶段：{phase}
待确认总结摘要：{summary}
待确认关键词：{kw_text}
用户最新回复：{(user_reply or "").strip()}

请严格输出以下两行，不要输出任何其他内容：
<STATE>confirmed|rejected|continue</STATE>
<CONTENT>给用户展示的一句话（20-80字）</CONTENT>

判定要求：
1) 只有当用户明确同意当前总结内容时，state 才能是 confirmed。
2) 当用户表达不认可、希望调整、继续讨论时，state 为 rejected。
3) 无法明确同意或否定时，state 为 continue。
4) 像“嗯/好/行”等口头语，若缺乏明确语义，优先判为 continue。
"""

    if is_reasoner:
        try:
            out_parts: List[str] = []
            async for item in llm.chat_stream([LLMMessage(role="user", content=token_prompt)], temperature=0.1):
                if isinstance(item, dict):
                    t = str(item.get("_t") or "")
                    if t == "think_start":
                        await emit_event({"think_start": True})
                    elif t == "think_chunk":
                        c = str(item.get("content") or "")
                        if c:
                            await emit_event({"think_chunk": c})
                    elif t == "think_end":
                        await emit_event({"think_end": str(item.get("content") or "")})
                    continue
                out_parts.append(str(item or ""))
            raw = "".join(out_parts).strip()
            obj = _extract_json_object(raw) or _extract_state_content_tokens(raw) or {}
            state = str(obj.get("state") or "continue").strip().lower()
            if state not in {"confirmed", "rejected", "continue"}:
                state = "continue"
            content = str(obj.get("content") or "").strip()
            if content:
                return {"state": state, "content": content}
        except Exception as e:
            logger.warning(
                "[pending_judge] reasoner stream failed model=%s err_type=%s err=%s; fallback to non-stream",
                model_name or "unknown",
                type(e).__name__,
                e,
            )

    return await _decide_pending_action_by_llm(
        phase,
        pending_conclusion,
        user_reply,
        vip_level=vip_level,
    )


def _build_pending_confirmation_text(phase: str, conclusion: dict) -> str:
    """在用户确认前先给可读摘要，不直接输出结论卡。"""
    summary = (conclusion or {}).get("summary") or ""
    keywords = (conclusion or {}).get("keywords") or []
    keyword_line = "、".join([str(k).strip() for k in keywords if str(k).strip()][:8])
    phase_label_map = {
        "values": "价值观",
        "strengths": "禀赋",
        "interests": "热忱",
        "purpose": "使命",
        "rumination": "沉淀",
    }
    phase_label = phase_label_map.get(phase, "本阶段")
    parts = [f"我先整理了你的{phase_label}阶段总结，请你确认是否准确。"]
    if summary:
        parts.append(summary)
    if keyword_line:
        parts.append(f"当前提炼关键词：{keyword_line}")
    parts.append("如果你确认无误，我会基于这份确认结果生成结论卡；如果你觉得不准确，我们继续聊。")
    return "\n\n".join(parts)


def _normalize_token_usage(usage: Optional[dict]) -> dict:
    usage = usage or {}
    in_tokens = int(usage.get("prompt_tokens") or 0)
    out_tokens = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (in_tokens + out_tokens))
    result = {
        "prompt_tokens": in_tokens,
        "completion_tokens": out_tokens,
        "total_tokens": total,
    }
    if "prompt_cache_hit_tokens" in usage:
        result["prompt_cache_hit_tokens"] = usage["prompt_cache_hit_tokens"]
    if "prompt_cache_miss_tokens" in usage:
        result["prompt_cache_miss_tokens"] = usage["prompt_cache_miss_tokens"]
    return result


class SimpleChatRequest(BaseModel):
    activation_code: str
    message: str
    # 阶段：values / strengths / interests
    phase: Optional[str] = "values"


class SimpleChatResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleInitRequest(BaseModel):
    activation_code: str
    phase: Optional[str] = "values"
    thread_id: Optional[str] = None  # 新建对话时传入，后端按 thread_id 创建独立存储


class SimpleHistoryResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleChatStreamRequest(BaseModel):
    activation_code: str
    message: str
    phase: Optional[str] = "values"
    thread_id: Optional[str] = None  # 当前对话 id，用于加载/保存到对应记录


class SurveySaveRequest(BaseModel):
    activation_code: str
    survey_data: dict


class PriorContextSaveRequest(BaseModel):
    activation_code: str
    phase: str       # 目标阶段，如 "strengths" / "interests"
    context_text: str


class ThreadCompleteRequest(BaseModel):
    activation_code: str
    phase: str
    thread_id: str


class ThreadDeleteRequest(BaseModel):
    activation_code: str
    phase: str
    thread_id: str


def _get_user_id_from_activation(rec) -> Optional[str]:
    """从激活码记录解析 user_id（owner_user_id 或 owner_email）"""
    uid = (getattr(rec, "owner_user_id", None) or "").strip()
    if uid:
        return uid
    email = (getattr(rec, "owner_email", None) or "").strip()
    if email:
        return email
    return None


def _load_basic_info_from_activation(activation_code: str) -> str:
    """根据激活码加载 basic_info（用户级），格式化为提示词用文本"""
    _manager, rec = get_activation_with_manager(activation_code)
    if not rec:
        return "暂无"
    user_id = _get_user_id_from_activation(rec)
    if user_id:
        data = load_basic_info_by_user(user_id)
        if data:
            return format_basic_info_for_prompt(data)
    base = str(get_effective_simple_root(rec))
    data = load_basic_info(rec.session_id, base)
    return format_basic_info_for_prompt(data)


def _load_prior_context_from_activation(
    activation_code: str, phase: str, report: Optional[dict] = None
) -> str:
    """根据激活码和阶段加载上一轮咨询结果（report 维度）"""
    _manager, rec = get_activation_with_manager(activation_code)
    if not rec:
        return ""
    root = get_effective_simple_root(rec)
    reports_root = str(root / "reports")
    if report and report.get("report_id"):
        text = load_prior_context_for_report(report["report_id"], phase, reports_root)
        if text:
            return text
    return load_prior_context(rec.session_id, phase, str(root))


def _is_step_locked(registry: ReportRegistry, report_id: str, phase_step: str) -> bool:
    record = registry.get_report_by_id(report_id) or {}
    step = ((record.get("steps") or {}).get(phase_step)) or {}
    return bool(step.get("locked", False))


def _assert_step_editable(
    *,
    registry: ReportRegistry,
    report_id: str,
    phase_step: str,
    current_user: Optional[dict],
    rec,
) -> None:
    # 管理员调试工作区可豁免（用于 sandbox/ADM 定向调试）
    if _can_bypass_flow_limits(current_user, rec):
        return
    if _is_step_locked(registry, report_id, phase_step):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该阶段已提交并锁定，不能再修改，请继续下一阶段",
        )


@router.get("/survey")
def get_survey(
    activation_code: str,
    current_user: dict = Depends(get_current_user),
):
    """获取指定激活码下的调研问卷数据（用户级，仅 1 份）"""
    manager = get_activation_manager_for_code(activation_code)
    rec = _resolve_activation_for_user(manager, activation_code, current_user)
    user_id = (current_user or {}).get("user_id") or (current_user or {}).get("email") or ""
    data = load_basic_info_by_user(user_id) if user_id else None
    if not data:
        data = load_basic_info(rec.session_id, str(get_effective_simple_root(rec)))
    return SimpleChatResponse(
        code=200,
        message="success",
        data={"survey_data": data or {}},
    )


@router.get("/prior-context")
def get_prior_context(
    activation_code: str,
    phase: str,
    current_user: dict = Depends(get_current_user),
):
    """获取指定阶段的上一轮咨询结果文本（report 维度）"""
    manager = get_activation_manager_for_code(activation_code)
    rec = _resolve_activation_for_user(manager, activation_code, current_user)
    user_id = (current_user or {}).get("user_id") or (current_user or {}).get("email") or ""
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.get_by_activation_user(rec.code, user_id) if user_id else None
    text = _load_prior_context_from_activation(activation_code, phase, report)
    return SimpleChatResponse(code=200, message="success", data={"context_text": text})


@router.post("/prior-context", response_model=SimpleChatResponse)
async def save_prior_context_endpoint(
    request: PriorContextSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    """保存（上传）指定阶段的上一轮咨询结果文本（report 维度）"""
    manager = get_activation_manager_for_code(request.activation_code)
    rec = _resolve_activation_for_user(manager, request.activation_code, current_user)
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="激活码已过期")
    user_id = (current_user or {}).get("user_id") or (current_user or {}).get("email") or ""
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.ensure_report(
        rec.code, user_id or "", bind_session_id_for_ensure_report(rec)
    )
    if report and report.get("report_id"):
        save_prior_context_for_report(
            report["report_id"],
            request.phase,
            request.context_text or "",
            str(root / "reports"),
        )
    return SimpleChatResponse(code=200, message="success", data={})


@router.post("/survey", response_model=SimpleChatResponse)
async def save_survey(
    request: SurveySaveRequest,
    current_user: dict = Depends(get_current_user),
):
    """保存调研问卷数据（用户级，仅保留最新 1 份）"""
    manager = get_activation_manager_for_code(request.activation_code)
    rec = _resolve_activation_for_user(manager, request.activation_code, current_user)
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期",
        )
    user_id = (current_user or {}).get("user_id") or (current_user or {}).get("email") or ""
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    save_basic_info_by_user(user_id, request.survey_data or {})
    return SimpleChatResponse(code=200, message="success", data={})


class RuminationProgressResponse(BaseModel):
    main_section: str = "opening"
    review_sub_index: int = 0
    filter_step: int = 0
    filter_table: Optional[dict] = None


class RuminationProgressSaveRequest(BaseModel):
    activation_code: str
    main_section: Optional[str] = None
    review_sub_index: Optional[int] = None
    filter_step: Optional[int] = None
    filter_table: Optional[Any] = None
    filter_row_cursor: Optional[int] = None
    hypothesis_round: Optional[int] = None
    filter_early_terminated: Optional[bool] = None
    filter_terminate_reason: Optional[str] = None


class RuminationTableSubmitRequest(BaseModel):
    activation_code: str
    thread_id: str
    step: int
    table_data: Optional[List[dict]] = None
    mode: Optional[str] = "full_step"
    row_id: Optional[str] = None
    patch: Optional[dict] = None
    prefer_single_row: Optional[bool] = None


@router.get("/rumination-progress", response_model=SimpleChatResponse)
def get_rumination_progress(
    activation_code: str,
    current_user: dict = Depends(get_current_user),
):
    """获取 rumination 阶段进度"""
    try:
        manager = get_activation_manager_for_code(activation_code)
        rec = _resolve_activation_for_user(manager, activation_code, current_user)
        root = get_effective_simple_root(rec)
        registry = ReportRegistry(base_dir=str(root))
        report = registry.ensure_report(
            rec.code,
            (current_user or {}).get("user_id", ""),
            bind_session_id_for_ensure_report(rec),
        )
        report_id = report.get("report_id")
        if not report_id:
            raise HTTPException(status_code=500, detail="报告初始化失败")
        reports_root = root / "reports"
        progress = load_rumination_progress(reports_root, report_id)
        return SimpleChatResponse(code=200, message="success", data={"progress": progress})
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("rumination-progress ensure_report failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise


@router.post("/rumination-progress", response_model=SimpleChatResponse)
def save_rumination_progress_endpoint(
    request: RuminationProgressSaveRequest,
    current_user: dict = Depends(get_current_user),
):
    """保存 rumination 阶段进度"""
    manager = get_activation_manager_for_code(request.activation_code)
    rec = _resolve_activation_for_user(manager, request.activation_code, current_user)
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(
        rec, current_user
    ):
        raise HTTPException(status_code=400, detail="激活码已过期")
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.ensure_report(
        rec.code,
        (current_user or {}).get("user_id", ""),
        bind_session_id_for_ensure_report(rec),
    )
    report_id = report.get("report_id")
    if not report_id:
        raise HTTPException(status_code=500, detail="报告初始化失败")
    reports_root = root / "reports"
    progress = save_rumination_progress(
        reports_root,
        report_id,
        main_section=request.main_section,
        review_sub_index=request.review_sub_index,
        filter_step=request.filter_step,
        filter_table=request.filter_table,
        filter_row_cursor=request.filter_row_cursor,
        hypothesis_round=request.hypothesis_round,
        filter_early_terminated=request.filter_early_terminated,
        filter_terminate_reason=request.filter_terminate_reason,
    )
    return SimpleChatResponse(code=200, message="success", data={"progress": progress})


async def _rumination_advance_after_step_confirm(
    step: int,
    table: List[dict],
    *,
    values_list: List[str],
    llm: Any,
) -> Tuple[int, List[dict], Dict[str, Any]]:
    """
    用户已确认当前筛选步骤（全量表）。返回 (下一 filter_step, 新表, 元信息)。
    filter_step 为 0 表示筛选管道已结束并将进入 final_choice。
    """
    meta: Dict[str, Any] = {}

    if step == 1:
        ft = filter_strength(table)
        if not ft:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_rows_after_strength"
            return (1, table, meta)
        nxt = filter_match(ft)
        return (2, nxt, meta)

    if step == 2:
        base = structure_hypothesis_round1_table(table)
        if not base:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_matching_rows"
            return (2, table, meta)
        vhint = "、".join(values_list[:8]) if values_list else ""
        filled = await fill_hypothesis_columns_for_table(
            llm, base, values_hint=vhint, only_empty_hypothesis_slots=False
        )
        return (3, filled, meta)

    if step == 3:
        any_empty = any(not (r.get("用户确认的假设") or "").strip() for r in table)
        if any_empty:
            r2 = generate_hypotheses_round2_table(table)
            vhint = "、".join(values_list[:8]) if values_list else ""
            filled = await fill_hypothesis_columns_for_table(
                llm, r2, values_hint=vhint, only_empty_hypothesis_slots=True
            )
            return (4, filled, meta)
        vt = value_filter(table, values_list)
        if not vt:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_rows_value_filter"
            return (6, [], meta)
        return (6, vt, meta)

    if step == 4:
        any_empty = any(not (r.get("用户确认的假设") or "").strip() for r in table)
        if any_empty:
            r2 = generate_hypotheses_round2_table(table)
            vhint = "、".join(values_list[:8]) if values_list else ""
            filled = await fill_hypothesis_columns_for_table(
                llm, r2, values_hint=vhint, only_empty_hypothesis_slots=True
            )
            return (5, filled, meta)
        vt = value_filter(table, values_list)
        if not vt:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_rows_value_filter"
            return (6, [], meta)
        return (6, vt, meta)

    if step == 5:
        fin = generate_hypotheses_round3_finalize(table)
        vt = value_filter(fin, values_list)
        if not vt:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_rows_value_filter"
            return (6, [], meta)
        return (6, vt, meta)

    if step == 6:
        pt = passion_filter(table)
        if not pt:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_rows_passion_filter"
            return (7, [], meta)
        return (7, pt, meta)

    if step == 7:
        rt = reality_filter(table)
        if not rt:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_rows_reality_filter"
            return (8, [], meta)
        return (8, rt, meta)

    if step == 8:
        st = similar_filter(table)
        if not st:
            meta["early_terminated"] = True
            meta["terminate_reason"] = "no_rows_similar_filter"
            return (9, [], meta)
        return (9, st, meta)

    if step == 9:
        meta["filter_complete"] = True
        meta["main_section"] = "final_choice"
        return (0, table, meta)

    return (step, table, meta)


def _rumination_next_widget(
    next_step: int,
    table: List[dict],
    values_list: List[str],
    *,
    single_row_mode: bool,
    cursor: int,
) -> Optional[dict]:
    if next_step == 0:
        return build_table_widget_payload(
            9,
            table,
            values_list,
            single_row_mode=False,
            row_cursor=0,
            total_rows=len(table),
        )
    disp, rc, tot = slice_rows_for_display(table, cursor, single_row_mode=single_row_mode)
    return build_table_widget_payload(
        next_step,
        disp,
        values_list,
        single_row_mode=single_row_mode and tot > 0,
        row_cursor=rc,
        total_rows=tot,
    )


@router.post("/rumination-table-submit", response_model=SimpleChatResponse)
async def rumination_table_submit(
    request: RuminationTableSubmitRequest,
    current_user: dict = Depends(get_current_user),
):
    """提交 rumination 筛选表格：更新 rumination_progress.json 中的全量 filter_table，不修改各 phase 结论文件。"""
    manager = get_activation_manager_for_code(request.activation_code)
    rec = _resolve_activation_for_user(manager, request.activation_code, current_user)
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(
        rec, current_user
    ):
        raise HTTPException(status_code=400, detail="激活码已过期")
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.ensure_report(
        rec.code,
        (current_user or {}).get("user_id", ""),
        bind_session_id_for_ensure_report(rec),
    )
    report_id = report.get("report_id")
    if not report_id:
        raise HTTPException(status_code=500, detail="报告初始化失败")
    reports_root = root / "reports"
    prior_context = _load_prior_context_from_activation(
        request.activation_code, "rumination", report
    )
    values_list, strengths_list, interests_list, _ = extract_from_prior_context(prior_context)
    passions = interests_list if interests_list else ["热爱1", "热爱2"]
    strengths_list = strengths_list if strengths_list else ["优势1", "优势2"]

    vip_level = getattr(rec, "vip_level", 1) or 1
    llm = _get_dialogue_llm_provider(vip_level=vip_level)

    step = max(1, min(9, int(request.step)))
    mode = (request.mode or "full_step").strip().lower()
    use_single = bool(request.prefer_single_row) or mode == "single_row"
    progress = load_rumination_progress(reports_root, report_id)

    merged_table: List[dict] = []
    if mode == "single_row":
        if not request.row_id:
            raise HTTPException(status_code=400, detail="single_row 模式需要 row_id")
        base = list(progress.get("filter_table") or [])
        if not base and step == 1:
            base = gen_table(strengths_list, passions)
        patch = dict(request.patch or {})
        merged_table = merge_row_by_id(base, str(request.row_id), patch)
        cur = int(progress.get("filter_row_cursor", 0))
        nrows = len(merged_table)
        if cur + 1 < nrows:
            progress = save_rumination_progress(
                reports_root,
                report_id,
                filter_step=step,
                filter_table=merged_table,
                filter_row_cursor=cur + 1,
                hypothesis_round=1,
                filter_early_terminated=False,
                filter_terminate_reason=None,
            )
            w = _rumination_next_widget(
                step, merged_table, values_list, single_row_mode=use_single, cursor=cur + 1
            )
            return SimpleChatResponse(
                code=200,
                message="success",
                data={
                    "progress": progress,
                    "next_step": step,
                    "next_action": "same_step_next_row",
                    "next_table_widget": w,
                    "full_table_preview": merged_table,
                },
            )
        table_for_advance = merged_table
    else:
        table_for_advance = list(request.table_data or [])
        if not table_for_advance and step == 1:
            table_for_advance = gen_table(strengths_list, passions)

    next_step, new_table, meta = await _rumination_advance_after_step_confirm(
        step, table_for_advance, values_list=values_list, llm=llm
    )

    early = bool(meta.get("early_terminated"))
    if early:
        progress = save_rumination_progress(
            reports_root,
            report_id,
            filter_step=0,
            filter_table=new_table,
            filter_row_cursor=0,
            hypothesis_round=1,
            filter_early_terminated=True,
            filter_terminate_reason=str(meta.get("terminate_reason") or "early"),
        )
        return SimpleChatResponse(
            code=200,
            message="success",
            data={
                "progress": progress,
                "next_step": 0,
                "next_action": "early_terminated",
                "early_terminated": True,
                "terminate_reason": meta.get("terminate_reason"),
                "full_table_preview": new_table,
            },
        )

    if meta.get("filter_complete"):
        progress = save_rumination_progress(
            reports_root,
            report_id,
            main_section="final_choice",
            filter_step=0,
            filter_table=new_table,
            filter_row_cursor=0,
            hypothesis_round=1,
            filter_early_terminated=False,
            filter_terminate_reason=None,
        )
        w = _rumination_next_widget(
            0, new_table, values_list, single_row_mode=False, cursor=0
        )
        return SimpleChatResponse(
            code=200,
            message="success",
            data={
                "progress": progress,
                "next_step": 0,
                "next_action": "show_full_table",
                "next_table_widget": w,
                "full_table_preview": new_table,
            },
        )

    progress = save_rumination_progress(
        reports_root,
        report_id,
        filter_step=next_step,
        filter_table=new_table,
        filter_row_cursor=0,
        hypothesis_round=1,
        filter_early_terminated=False,
        filter_terminate_reason=None,
    )
    w = _rumination_next_widget(
        next_step, new_table, values_list, single_row_mode=use_single, cursor=0
    )
    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "progress": progress,
            "next_step": next_step,
            "next_action": "advance_step",
            "next_table_widget": w,
            "full_table_preview": new_table,
        },
    )


@router.get("/rumination-get-table", response_model=SimpleChatResponse)
def rumination_get_table(
    activation_code: str,
    step: Optional[int] = None,
    single_row_mode: bool = Query(False),
    prefer_single_row: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    """获取 rumination 筛选当前步骤表格（全量存 progress，可单行展示）。"""
    manager = get_activation_manager_for_code(activation_code)
    rec = _resolve_activation_for_user(manager, activation_code, current_user)
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.ensure_report(
        rec.code,
        (current_user or {}).get("user_id", ""),
        bind_session_id_for_ensure_report(rec),
    )
    report_id = report.get("report_id")
    if not report_id:
        raise HTTPException(status_code=500, detail="报告初始化失败")
    reports_root = root / "reports"
    progress = load_rumination_progress(reports_root, report_id)
    prior_context = _load_prior_context_from_activation(activation_code, "rumination", report)
    values_list, strengths_list, interests_list, _ = extract_from_prior_context(prior_context)
    passions = interests_list if interests_list else ["热爱1", "热爱2"]
    strengths_list = strengths_list if strengths_list else ["优势1", "优势2"]

    use_single = bool(single_row_mode or prefer_single_row)
    fs = int(progress.get("filter_step") or 0)
    ms = str(progress.get("main_section") or "opening")
    if step is not None:
        eff_step = max(0, min(9, int(step)))
    elif ms == "final_choice" and fs == 0:
        eff_step = 0
    elif fs > 0:
        eff_step = fs
    else:
        eff_step = 1

    payload: Optional[dict] = None
    filter_complete = False

    if eff_step == 0:
        rows = list(progress.get("filter_table") or [])
        payload = build_table_widget_payload(
            9, rows, values_list, single_row_mode=False, row_cursor=0, total_rows=len(rows)
        )
        filter_complete = True
    elif eff_step == 1:
        ft = progress.get("filter_table")
        fs_cur = int(progress.get("filter_step") or 0)
        if not ft or fs_cur == 0:
            rows = gen_table(strengths_list, passions)
            progress = save_rumination_progress(
                reports_root,
                report_id,
                filter_step=1,
                filter_table=rows,
                filter_row_cursor=0,
            )
        else:
            rows = list(ft)
        cur = int(progress.get("filter_row_cursor", 0))
        disp, rc, tot = slice_rows_for_display(rows, cur, single_row_mode=use_single)
        payload = build_table_widget_payload(
            1,
            disp,
            values_list,
            single_row_mode=use_single and tot > 0,
            row_cursor=rc,
            total_rows=tot,
        )
    else:
        rows = list(progress.get("filter_table") or [])
        if not rows:
            payload = None
        else:
            cur = int(progress.get("filter_row_cursor", 0))
            disp, rc, tot = slice_rows_for_display(rows, cur, single_row_mode=use_single)
            payload = build_table_widget_payload(
                eff_step,
                disp,
                values_list,
                single_row_mode=use_single and tot > 0,
                row_cursor=rc,
                total_rows=tot,
            )

    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "table_widget": payload,
            "progress": progress,
            "filter_complete": filter_complete,
        },
    )


def _build_system_prompt(
    phase: str,
    question_bank: str = "",
    basic_info: str = "暂无",
    prior_context: str = "",
    template_override: Optional[str] = None,
    extra_goal_hint: str = "",
) -> str:
    """根据阶段构建 system prompt（通过模板渲染，避免超长硬编码）。"""
    prior_block = f"\n\n以下是该来访者在上一轮咨询中的谈话结果，供你参考：\n{prior_context}" if prior_context.strip() else ""
    context = {
        "phase": phase,
        "question_bank": question_bank,
        "basic_info": basic_info,
        "prior_block": prior_block,
    }
    if (template_override or "").strip():
        env = Environment(trim_blocks=True, lstrip_blocks=True)
        base_prompt = env.from_string(template_override).render(**context)
    else:
        base_prompt = get_simple_chat_system_prompt(context)
    if (extra_goal_hint or "").strip():
        base_prompt = f"{base_prompt}\n\n[管理员调试目标补充]\n{extra_goal_hint.strip()}"
    # 机器协议：每轮回复末尾输出状态 JSON，后端据此驱动 pending 状态机（不会展示给前端）。
    phase_key = (phase or "values").strip().lower()
    if phase_key == "rumination" and (prior_context or "").strip():
        base_prompt = (
            f"{base_prompt}\n\n[四维关键词摘要 — 提问与回顾须结合此处与前文 prior，不使用固定选择题库]\n"
            f"{build_prior_keywords_summary(prior_context)}"
        )
    if phase_key == "rumination":
        protocol = """

[输出协议 - 必须遵守]
沉淀阶段不使用维度结论卡。在自然语言回复末尾追加如下块（严格 JSON）：
[STATE_JSON]
{"state":"continue","draft":null}
[/STATE_JSON]
规则：state 必须为 continue，draft 必须为 null；禁止 pending_ready。
[STATE_JSON] 块之外只写给用户看的自然语言，不要解释本协议。
"""
    else:
        protocol = """

[输出协议 - 必须遵守]
在你的自然语言回复末尾，追加如下块（严格 JSON）：
[STATE_JSON]
{"state":"continue|pending_ready","draft":{"summary":"...","keywords":["..."]}}
[/STATE_JSON]

规则：
1) 仅当你判断“已可进入结论确认”时，state 才能是 pending_ready。
2) state=continue 时，draft 置为 null。
3) state=pending_ready 时，draft.summary 必填，draft.keywords 为数组（可为空但应尽量给出）。
4) draft.keywords 中每一项必须是单一概念词（或本阶段要求的单一短语），不得使用「/、或、以及、&、|」并列多个候选；近义词须先在对话中与用户确认取舍后再写入。
5) values / strengths / interests / purpose：当用户已按该阶段流程完成确认（如价值观 5 词与排序、禀赋 10 条优势与标记、热忱 top3、使命宣言等）后，必须输出 pending_ready 并给出合格 draft，以便系统展示结论卡供用户最终确认；不得仅口头说“完成”而省略 STATE_JSON。
6) [STATE_JSON] 块之外只写给用户看的自然语言，不要解释本协议。
"""
    return f"{base_prompt}\n{protocol}"


def _split_visible_reply_and_state(raw_text: str) -> tuple[str, Optional[Dict]]:
    """
    从模型输出中拆分用户可见文本和状态 JSON。
    格式：
      ...用户可见文本...
      [STATE_JSON]
      {...}
      [/STATE_JSON]
    """
    if not raw_text:
        return "", None
    m = re.search(r"\[STATE_JSON\]\s*(\{.*?\})\s*\[/STATE_JSON\]\s*$", raw_text, flags=re.DOTALL)
    if not m:
        return raw_text.strip(), None
    json_part = m.group(1).strip()
    visible = raw_text[:m.start()].rstrip()
    try:
        obj = json.loads(json_part)
        return visible, obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        return visible, None


def _strip_hidden_blocks_for_stream(
    raw_text: str,
    block_markers: Sequence[Tuple[str, str]],
) -> str:
    """
    流式展示时隐藏协议块（可配置起止标记）：
    - 去掉已闭合 start...end
    - 若出现未闭合 start，从 start 起全部截断
    - 末尾若是 start 的前缀片段，先暂存不输出，避免闪现
    """
    if not raw_text:
        return ""
    txt = raw_text
    for start_marker, end_marker in block_markers:
        if not start_marker or not end_marker:
            continue
        txt = re.sub(
            f"{re.escape(start_marker)}.*?{re.escape(end_marker)}",
            "",
            txt,
            flags=re.DOTALL,
        )
        start = txt.find(start_marker)
        if start >= 0:
            txt = txt[:start]
        hold = 0
        max_k = min(len(start_marker) - 1, len(txt))
        for k in range(max_k, 0, -1):
            if txt.endswith(start_marker[:k]):
                hold = k
                break
        if hold:
            txt = txt[:-hold]
    return txt


def _build_stream_hidden_block_filter(
    block_markers: Sequence[Tuple[str, str]],
) -> Callable[[str], str]:
    """
    构建“累计文本 -> 本次可见增量”的过滤器。
    通过闭包持有已输出内容，确保 SSE chunk 增量一致。
    """
    emitted_visible = ""

    def consume(cumulative_raw_text: str) -> str:
        nonlocal emitted_visible
        visible = _strip_hidden_blocks_for_stream(cumulative_raw_text, block_markers)
        if len(visible) <= len(emitted_visible):
            return ""
        delta = visible[len(emitted_visible) :]
        emitted_visible = visible
        return delta

    return consume


@router.post("/message", response_model=SimpleChatResponse)
async def simple_chat(
    request: SimpleChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    简单模式的单轮对话：
    - 使用 activation_code 找到对应的会话与模式
    - 读取历史消息
    - 构造 system_prompt + 历史 + 当前用户消息
    - 调用 LLM 得到回复
    - 将本轮 user / assistant 消息写入 data/simple 下
    """
    manager = get_activation_manager_for_code(request.activation_code)
    phase = (request.phase or "values").strip() or "values"
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=phase,
        thread_id=None,
    )

    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )

    # 更新最后活跃时间（过期时不更新）
    if rec.status == ActivationStatus.ACTIVE:
        manager.touch_activity(rec.code)

    # 使用 report 目录保存对话
    session_id = report["report_id"]
    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    _assert_step_editable(
        registry=registry,
        report_id=report["report_id"],
        phase_step=phase_step,
        current_user=current_user,
        rec=rec,
    )

    # 读取历史消息（只取当前分类）
    history_messages: List[dict] = await conv_manager.get_messages(
        session_id=session_id,
        category=category,
    )

    vip_level = getattr(rec, "vip_level", 1) or 1
    llm = _get_dialogue_llm_provider(vip_level=vip_level)

    # question_bank 在线程内固定：首次生成，后续复用，避免每轮变化导致 cache miss
    question_bank = await _get_or_create_thread_question_bank(
        conv_manager=conv_manager,
        session_id=session_id,
        category=category,
        phase_step=phase_step,
    )
    basic_info = _load_basic_info_from_activation(request.activation_code)
    prior_context = _load_prior_context_from_activation(
        request.activation_code, phase_step, report
    )
    override_cfg = _resolve_prompt_lab_override_for_request(rec, current_user)
    system_prompt = _build_system_prompt(
        phase_step,
        question_bank=question_bank,
        basic_info=basic_info,
        prior_context=prior_context,
        template_override=(override_cfg or {}).get("template"),
        extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
    )
    llm_messages = [LLMMessage(role="system", content=system_prompt)]

    # 把历史文件中的 role/content 转成 LLMMessage
    for m in history_messages:
        role = m.get("role") or "user"
        if role not in {"user", "assistant", "system"}:
            continue
        content = m.get("content") or ""
        if not content:
            continue
        llm_messages.append(LLMMessage(role=role, content=content))

    # 当前用户输入
    llm_messages.append(LLMMessage(role="user", content=request.message))

    # 调用大模型
    token_usage = _normalize_token_usage(None)
    try:
        response = await llm.chat(llm_messages, temperature=0.7)
        reply_text = (response.content or "").strip()
        reply_text, _ = _split_visible_reply_and_state(reply_text)
        token_usage = _normalize_token_usage(getattr(response, "usage", None))
    except Exception as e:
        # 避免因为上游 LLM 配置/网络问题导致初始化 500，保证问答流程可继续。
        logger.exception("simple-chat init failed, fallback to local prompt: %s", e)
        reply_text = _build_fallback_opening_question(phase_step)

    if not reply_text:
        reply_text = _build_fallback_opening_question(phase_step)

    # 把当前轮 user / assistant 消息写入文件
    await conv_manager.append_message(
        session_id=session_id,
        category=category,
        message={
            "role": "user",
            "content": request.message,
            "session_id": logical_session_id,
            "step_id": phase_step,
            "agent_id": None,
            "event": "user_message",
        },
    )

    await conv_manager.append_message(
        session_id=session_id,
        category=category,
        message={
            "role": "assistant",
            "content": reply_text,
            "session_id": logical_session_id,
            "step_id": phase_step,
            "agent_id": "coach",
            "event": "assistant_reply",
            "token_usage": token_usage,
        },
    )

    try:
        await AnalyticsService.record_chat_turn(
            session_id=logical_session_id,
            dimension=phase_step,
            user_input_chars=len(request.message or ""),
            llm_input_tokens=int(token_usage.get("prompt_tokens") or 0),
            llm_output_tokens=int(token_usage.get("completion_tokens") or 0),
            log_index=None,
        )
    except Exception:
        pass

    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "reply": reply_text,
            "activation": {
                "activation_code": rec.code,
                "session_id": logical_session_id,
                "mode": rec.mode,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
                "status": rec.status,
            },
            "report_id": report["report_id"],
            "step_id": phase_step,
            "token_usage": token_usage,
        },
    )


@router.post("/init", response_model=SimpleChatResponse)
async def simple_init(
    request: SimpleInitRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    初始化某个阶段的对话：
    - 如果该阶段已经有历史消息，则直接返回（不再重复生成）
    - 如果没有历史，则生成一条「首轮引导问题」的 assistant 消息
    """
    try:
        return await _simple_init_impl(request, current_user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("simple-chat init 500: %s", e)
        raise HTTPException(status_code=500, detail=f"初始化失败: {type(e).__name__}: {str(e)}")


async def _simple_init_impl(request: SimpleInitRequest, current_user: dict) -> SimpleChatResponse:
    manager = get_activation_manager_for_code(request.activation_code)
    phase = (request.phase or "values").strip() or "values"
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=phase,
        thread_id=request.thread_id,
    )
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )
    session_id = report["report_id"]

    # 如果已有历史，就直接返回历史（新建 thread_id 时文件不存在，返回空）
    history_messages: List[dict] = await conv_manager.get_messages(
        session_id=session_id,
        category=category,
    )
    if history_messages:
        return SimpleChatResponse(
            code=200,
            message="success",
            data={
                "messages": history_messages,
                "activation": {
                    "activation_code": rec.code,
                    "session_id": logical_session_id,
                    "mode": rec.mode,
                    "created_at": rec.created_at,
                    "expires_at": rec.expires_at,
                    "status": rec.status,
                },
                "report_id": report["report_id"],
                "step_id": phase_step,
            },
        )
    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    _assert_step_editable(
        registry=registry,
        report_id=report["report_id"],
        phase_step=phase_step,
        current_user=current_user,
        rec=rec,
    )

    # 没有历史：生成一条首轮引导问题
    vip_level = getattr(rec, "vip_level", 1) or 1
    llm = _get_dialogue_llm_provider(vip_level=vip_level)
    question_bank = await _get_or_create_thread_question_bank(
        conv_manager=conv_manager,
        session_id=session_id,
        category=category,
        phase_step=phase_step,
    )
    basic_info = _load_basic_info_from_activation(request.activation_code)
    prior_context = _load_prior_context_from_activation(
        request.activation_code, phase_step, report
    )
    override_cfg = _resolve_prompt_lab_override_for_request(rec, current_user)
    system_prompt = _build_system_prompt(
        phase_step,
        question_bank=question_bank,
        basic_info=basic_info,
        prior_context=prior_context,
        template_override=(override_cfg or {}).get("template"),
        extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
    )
    llm_messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content="我是来访者，你需要向我提问。以下是我的基本信息：暂无。请给出第一轮温柔而具体的引导问题，让我开始思考。"),
    ]
    token_usage = _normalize_token_usage(None)
    try:
        response = await llm.chat(llm_messages, temperature=0.7)
        reply_text = (response.content or "").strip()
        reply_text, _ = _split_visible_reply_and_state(reply_text)
        token_usage = _normalize_token_usage(getattr(response, "usage", None))
    except Exception as e:
        # 避免初始化阶段因上游 LLM 失败直接 500，先返回本地兜底问题保证流程可继续。
        logger.exception("simple-chat init failed, fallback to local prompt: %s", e)
        reply_text = _build_fallback_opening_question(phase_step)

    if not reply_text:
        reply_text = _build_fallback_opening_question(phase_step)

    # 只写入 assistant 消息，作为起始问题
    await conv_manager.append_message(
        session_id=session_id,
        category=category,
        message={
            "role": "assistant",
            "content": reply_text,
            "session_id": logical_session_id,
            "step_id": phase_step,
            "agent_id": "coach",
            "event": "init_question",
            "token_usage": token_usage,
        },
    )

    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "messages": [
                {
                    "role": "assistant",
                    "content": reply_text,
                }
            ],
            "activation": {
                "activation_code": rec.code,
                "session_id": logical_session_id,
                "mode": rec.mode,
                "created_at": rec.created_at,
                "expires_at": rec.expires_at,
                "status": rec.status,
            },
            "report_id": report["report_id"],
            "step_id": phase_step,
            "token_usage": token_usage,
        },
    )


class ThreadReopenRequest(BaseModel):
    activation_code: str
    phase: str
    thread_id: str


@router.post("/thread/reopen", response_model=SimpleChatResponse)
async def reopen_thread(
    request: ThreadReopenRequest,
    current_user: dict = Depends(get_current_user),
):
    """用户选择「再聊聊」完善答案时，清除完成状态以便继续对话"""
    manager = get_activation_manager_for_code(request.activation_code)
    phase_val = (request.phase or "values").strip() or "values"
    try:
        rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=request.activation_code,
            current_user=current_user,
            phase=phase_val,
            thread_id=request.thread_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("reopen_thread _resolve_report_context failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="解析会话上下文失败，请刷新页面后重试",
        ) from e
    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    _assert_step_editable(
        registry=registry,
        report_id=report["report_id"],
        phase_step=phase_step,
        current_user=current_user,
        rec=rec,
    )
    # 允许在已锁定阶段继续对话：用户明确选择「再聊聊」时，可对当前线程补充完善
    # locked 仅限制「切换会话」，不限制对已选线程的继续编辑
    conv_data = await conv_manager.get_conversation_data(report["report_id"], category)
    meta = conv_data.get("metadata") or {}
    cmeta = _read_conclusion_meta(meta)
    last_conclusion = cmeta.get("final")
    pending_rejected = {
        "summary": (last_conclusion or {}).get("summary", ""),
        "keywords": (last_conclusion or {}).get("keywords", []),
        "feedback": "用户选择再聊聊",
    } if isinstance(last_conclusion, dict) else {
        "summary": "",
        "keywords": [],
        "feedback": "用户选择再聊聊",
    }
    await conv_manager.update_metadata(
        report["report_id"],
        category,
        _build_conclusion_meta_update(
            state=CONCLUSION_STATE_REJECTED,
            final=last_conclusion if isinstance(last_conclusion, dict) else None,
            feedback=pending_rejected.get("feedback", "用户选择再聊聊"),
            thread_completed=False,
        ),
    )
    return SimpleChatResponse(code=200, message="success", data={})


@router.post("/thread/complete", response_model=SimpleChatResponse)
async def mark_thread_complete(
    request: ThreadCompleteRequest,
    current_user: dict = Depends(get_current_user),
):
    """标记某对话为已完成（用户点击「确认没有问题」后调用）"""
    manager = get_activation_manager_for_code(request.activation_code)
    phase_val = (request.phase or "values").strip() or "values"
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=phase_val,
        thread_id=request.thread_id,
    )
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    try:
        registry.select_session(report["report_id"], phase_step, logical_session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    conv_data = await conv_manager.get_conversation_data(report["report_id"], category)
    metadata = conv_data.get("metadata", {})
    cmeta = _read_conclusion_meta(metadata)
    dimension_conclusion = cmeta.get("final") or cmeta.get("draft")
    messages = conv_data.get("messages") or []
    has_conclusion_card = any((m or {}).get("role") == "conclusion_card" for m in messages)
    if dimension_conclusion and not has_conclusion_card:
        await conv_manager.append_message(
            session_id=report["report_id"],
            category=category,
            message={
                "role": "conclusion_card",
                "content": json.dumps(dimension_conclusion, ensure_ascii=False),
                "session_id": logical_session_id,
                "step_id": phase_step,
                "agent_id": "coach",
                "event": "dimension_conclusion",
                "card_type": "dimension_conclusion",
                "card_payload": dimension_conclusion,
            },
        )
    await conv_manager.update_metadata(
        report["report_id"],
        category,
        _build_conclusion_meta_update(
            state=CONCLUSION_STATE_CONFIRMED,
            final=dimension_conclusion if isinstance(dimension_conclusion, dict) else None,
            shown_at=metadata.get("conclusion_shown_at_turn"),
            thread_completed=True,
        ),
    )
    if dimension_conclusion:
        await _append_note_json(
            conv_manager,
            report["report_id"],
            category,
            "dimension_conclusion_confirmed",
            {
                "phase": phase_step,
                "thread_id": logical_session_id,
                "dimension_conclusion": dimension_conclusion,
            },
        )
        _write_anchor_from_conclusion(
            report_id=report["report_id"],
            phase_step=phase_step,
            storage_root=str(root),
            conclusion=dimension_conclusion,
        )
        summary = dimension_conclusion.get("summary") or dimension_conclusion.get("ai_summary", "")
        keywords = dimension_conclusion.get("keywords") or []
        if isinstance(keywords, list):
            kw_text = "、".join(str(k) for k in keywords)
        else:
            kw_text = str(keywords)
        prior_text = f"{summary}\n关键词：{kw_text}".strip() if (summary or kw_text) else ""
        if prior_text:
            phase_labels = {"values": "信念", "strengths": "禀赋", "interests": "热忱", "purpose": "使命"}
            label = phase_labels.get(phase_step, phase_step)
            prior_block = f"【{label} 阶段结果】\n{prior_text}"
            next_phase = {"values": "strengths", "strengths": "interests", "interests": "purpose", "purpose": "rumination"}.get(phase_step)
            if next_phase:
                save_prior_context_for_report(
                    report["report_id"], next_phase, prior_block, str(root / "reports")
                )
    _trigger_anchor_refiner(
        report["report_id"],
        phase_step,
        category,
        conv_manager,
        str(root),
        dimension_conclusion=dimension_conclusion,
        vip_level=getattr(rec, "vip_level", 1) or 1,
    )
    return SimpleChatResponse(code=200, message="success", data={})


@router.get("/threads", response_model=SimpleHistoryResponse)
async def list_threads(
    activation_code: str,
    phase: Optional[str] = "values",
    current_user: dict = Depends(get_current_user),
):
    """
    获取某阶段下的线程列表（后端为数据源，支持跨设备同步）。
    返回 record.json 中 steps[phase].session_ids 对应的线程元信息。
    """
    manager = get_activation_manager_for_code(activation_code)
    phase_val = (phase or "values").strip() or "values"
    phase_step = ReportRegistry.normalize_step_id(phase_val)
    rec = _resolve_activation_for_user(manager, activation_code, current_user)
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    # 注意：threads 列表是只读入口，不在这里自动绑定默认 session，
    # 否则首次激活会出现“有线程但无消息”，前端误判为已初始化。
    report = registry.ensure_report(
        activation_code=rec.code,
        user_id=user_id,
        session_id=None,
    )
    if not report:
        raise HTTPException(status_code=500, detail="报告初始化失败")

    step = (report.get("steps") or {}).get(phase_step) or {}
    session_ids = step.get("session_ids") or []
    conv_manager = ConversationFileManager(base_dir=str(root / "reports"))

    threads: List[dict] = []
    report_id = report.get("report_id")
    if not report_id:
        return SimpleHistoryResponse(code=200, message="success", data={"threads": []})

    selected_id = step.get("selected_session_id")

    for idx, tid in enumerate(session_ids):
        tid = (tid or "").strip()
        if not tid:
            continue
        category = _storage_category(phase_step, tid)
        conv_data = await conv_manager.get_conversation_data(report_id, category)
        meta = conv_data.get("metadata") or {}
        messages = conv_data.get("messages") or []
        created_at = meta.get("created_at") or ""
        first_msg = messages[0] if messages else {}
        msg_ts = first_msg.get("created_at") or created_at
        try:
            ts_ms = int(datetime.fromisoformat(msg_ts.replace("Z", "+00:00")).timestamp() * 1000) if msg_ts else 0
        except (ValueError, TypeError):
            ts_ms = 0
        cmeta = _read_conclusion_meta(meta)
        completed = bool(cmeta.get("thread_completed"))
        dim_preview = cmeta.get("final") or (
            cmeta.get("draft") if cmeta.get("state") == CONCLUSION_STATE_PENDING else None
        )
        threads.append({
            "id": tid,
            "title": f"对话 {idx + 1}",
            "status": "completed" if completed else "in-progress",
            "messages": [],  # 列表不返回消息体，由 /history 按需加载
            "createdAt": ts_ms or int(datetime.now(timezone.utc).timestamp() * 1000),
            "dimensionConclusion": dim_preview,
            "selected": tid == selected_id,
            "step_locked": bool(step.get("locked", False)),
        })

    return SimpleHistoryResponse(
        code=200,
        message="success",
        data={
            "threads": threads,
            "report_id": report_id,
            "step_id": phase_step,
            "step_locked": bool(step.get("locked", False)),
        },
    )


@router.get("/history", response_model=SimpleHistoryResponse)
async def simple_history(
    activation_code: str,
    phase: Optional[str] = "values",
    thread_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    获取某个激活码 + 阶段下的全部历史消息
    """
    try:
        manager = get_activation_manager_for_code(activation_code)
        phase_val = (phase or "values").strip() or "values"
        rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=activation_code,
            current_user=current_user,
            phase=phase_val,
            thread_id=thread_id,
        )
        session_id = report["report_id"]
        root = get_effective_simple_root(rec)
        registry = ReportRegistry(base_dir=str(root))

        conv_data = await conv_manager.get_conversation_data(session_id, category)
        history_messages = conv_data.get("messages", [])
        metadata = conv_data.get("metadata", {})
        cmeta = _read_conclusion_meta(metadata)
        record = registry.get_report_by_id(report["report_id"]) or {}
        step_payload = ((record.get("steps") or {}).get(phase_step)) or {}
        dim_for_meta = cmeta.get("final") or (
            cmeta.get("draft") if cmeta.get("state") == CONCLUSION_STATE_PENDING else None
        )

        return SimpleHistoryResponse(
            code=200,
            message="success",
            data={
                "messages": history_messages,
                "metadata": {
                    "session_id": logical_session_id,
                    "thread_completed": cmeta.get("thread_completed", False),
                    "dimension_conclusion": dim_for_meta,
                    "step_locked": bool(step_payload.get("locked", False)),
                },
                "activation": {
                    "activation_code": rec.code,
                    "session_id": logical_session_id,
                    "mode": rec.mode,
                    "created_at": rec.created_at,
                    "expires_at": rec.expires_at,
                    "status": rec.status,
                },
                "report_id": report["report_id"],
                "step_id": phase_step,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "simple_history error: activation=%s phase=%s thread_id=%s: %s",
            activation_code, phase, thread_id, e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="加载历史消息失败，请稍后重试",
        ) from e


@router.post("/message/stream")
async def simple_chat_stream(
    request: SimpleChatStreamRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    简单模式流式对话：
    - 使用 activation_code + phase 区分会话与阶段
    - 保存用户消息
    - 使用 chat_stream 按块返回助手回复
    - 结束时保存完整助手回复
    """
    manager = get_activation_manager_for_code(request.activation_code)
    phase = (request.phase or "values").strip() or "values"
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=phase,
        thread_id=request.thread_id,
    )
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )
    session_id = report["report_id"]
    vip_level = getattr(rec, "vip_level", 1) or 1
    storage_root = str(get_effective_simple_root(rec))
    registry = ReportRegistry(base_dir=storage_root)
    _assert_step_editable(
        registry=registry,
        report_id=report["report_id"],
        phase_step=phase_step,
        current_user=current_user,
        rec=rec,
    )

    async def event_stream() -> AsyncIterator[str]:
        llm = _get_dialogue_llm_provider(vip_level=vip_level)
        reasoning_llm = _get_reasoning_llm_provider(vip_level=vip_level)
        # 避免复用 provider 时串用上一次流式 token 使用量
        if hasattr(llm, "_last_stream_usage"):
            try:
                setattr(llm, "_last_stream_usage", None)
            except Exception:
                pass

        # 读取当前 thread 的历史（独立存储，全新上下文）
        history_messages: List[dict] = await conv_manager.get_messages(
            session_id=session_id,
            category=category,
        )

        # 进入新阶段的首条消息时，为上一阶段触发锚点摘要（step 提交时）
        user_msg_count = sum(1 for m in history_messages if m.get("role") == "user")
        if phase_step != "values" and user_msg_count == 0:
            idx = STEP_ORDER.get(phase_step, 0)
            if idx > 0:
                prev_phase = STEP_IDS[idx - 1]
                prev_selected = (report.get("steps") or {}).get(prev_phase) or {}
                prev_sess = prev_selected.get("selected_session_id")
                if prev_sess:
                    prev_cat = _storage_category(prev_phase, prev_sess)
                    _trigger_anchor_refiner(
                        session_id, prev_phase, prev_cat, conv_manager, storage_root, vip_level=vip_level
                    )

        question_bank = await _get_or_create_thread_question_bank(
            conv_manager=conv_manager,
            session_id=session_id,
            category=category,
            phase_step=phase_step,
        )
        basic_info = _load_basic_info_from_activation(request.activation_code)
        prior_context = _load_prior_context_from_activation(
            request.activation_code, phase_step, report
        )
        override_cfg = _resolve_prompt_lab_override_for_request(rec, current_user)
        system_prompt = _build_system_prompt(
            phase_step,
            question_bank=question_bank,
            basic_info=basic_info,
            prior_context=prior_context,
            template_override=(override_cfg or {}).get("template"),
            extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
        )
        llm_messages = [LLMMessage(role="system", content=system_prompt)]

        # 若有锚点摘要，插入 [此前对话要点] 再拼接最近 N 轮
        anchor = load_anchor_for_phase(session_id, phase_step, storage_root)
        anchor_text = format_anchor_for_prompt(anchor)
        if anchor_text:
            llm_messages.append(LLMMessage(role="assistant", content=f"[此前对话要点]\n{anchor_text}"))

        # 仅保留最近 N 轮，减少 token 与延迟
        turn_count = 0
        trimmed: List[dict] = []
        for m in reversed(history_messages):
            role = m.get("role") or "user"
            if role == "user":
                turn_count += 1
                if turn_count > MAX_HISTORY_TURNS:
                    break
            if role in {"user", "assistant", "system"}:
                trimmed.insert(0, m)

        for m in trimmed:
            role = m.get("role") or "user"
            if role not in {"user", "assistant", "system"}:
                continue
            content = m.get("content") or ""
            if not content:
                continue
            llm_messages.append(LLMMessage(role=role, content=content))

        # 当前用户输入
        user_content = (request.message or "").strip()
        if user_content:
            llm_messages.append(LLMMessage(role="user", content=user_content))
            # 先保存用户消息
            await conv_manager.append_message(
                session_id=session_id,
                category=category,
                message={
                    "role": "user",
                    "content": user_content,
                    "session_id": logical_session_id,
                    "step_id": phase_step,
                    "agent_id": None,
                    "event": "user_message",
                },
            )

        full_reply = ""

        # 发送 started 事件
        yield f"data: {{\"started\": true}}\n\n"

        # 1) pending 草案处理：由推理模型输出 JSON state（confirmed/rejected/continue）
        conv_data = await conv_manager.get_conversation_data(session_id, category)
        meta = conv_data.get("metadata", {})
        cmeta = _read_conclusion_meta(meta)
        pending_conclusion = cmeta.get("draft")
        rejected_feedback = cmeta.get("feedback") or ""
        conv_history = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in conv_data.get("messages", [])
        ]
        user_count = sum(1 for m in conv_data.get("messages", []) if m.get("role") == "user")
        conclusion_shown_at = cmeta.get("shown_at")

        if pending_conclusion and not cmeta.get("thread_completed"):
            pending_events_q: asyncio.Queue = asyncio.Queue()

            async def _emit_pending_event(evt: Dict) -> None:
                await pending_events_q.put(evt)

            pending_task = asyncio.create_task(
                _decide_pending_action_by_llm_streaming(
                    phase_step,
                    pending_conclusion if isinstance(pending_conclusion, dict) else {},
                    user_content,
                    vip_level=vip_level,
                    emit_event=_emit_pending_event,
                )
            )
            pending_timed_out = False
            elapsed = 0.0
            while True:
                if pending_task.done() and pending_events_q.empty():
                    break
                try:
                    evt = await asyncio.wait_for(pending_events_q.get(), timeout=PENDING_HEARTBEAT_SECONDS)
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    elapsed += PENDING_HEARTBEAT_SECONDS
                    yield (
                        f"data: {{\"heartbeat\": \"pending_judge\", \"elapsed\": {int(elapsed)} }}\n\n"
                    )
                    if elapsed >= PENDING_JUDGE_TIMEOUT_SECONDS:
                        pending_timed_out = True
                        pending_task.cancel()
                        logger.warning(
                            "[pending_judge] timeout degrade after %.1fs phase=%s thread=%s",
                            elapsed,
                            phase_step,
                            logical_session_id,
                        )
                        break

            if pending_timed_out:
                try:
                    await pending_task
                except Exception:
                    pass
                decision = {
                    "state": "continue",
                    "content": "当前网络较慢，我们先继续补充，再为你生成结论卡。",
                }
            else:
                try:
                    decision = await pending_task
                except asyncio.CancelledError:
                    decision = {
                        "state": "continue",
                        "content": "当前网络较慢，我们先继续补充，再为你生成结论卡。",
                    }
                except Exception as e:
                    logger.warning(
                        "[pending_judge] streaming task failed err_type=%s err=%s",
                        type(e).__name__,
                        e,
                    )
                    decision = {
                        "state": "continue",
                        "content": "我还不确定你是否确认，我们继续聊一聊更稳妥。",
                    }
            pending_state = decision.get("state", "continue")
            pending_msg = decision.get("content", "")

            if pending_state == "confirmed":
                reasoning_llm = _get_reasoning_llm_provider(vip_level=vip_level)
                try:
                    dimension_conclusion = await asyncio.wait_for(
                        check_dimension_complete(
                            phase_step,
                            conv_history,
                            prior_conclusion=pending_conclusion if isinstance(pending_conclusion, dict) else None,
                            vip_level=vip_level,
                            llm_provider=reasoning_llm,
                        ),
                        timeout=CONCLUSION_GEN_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "[conclusion_gen] timeout degrade after %ss phase=%s thread=%s",
                        CONCLUSION_GEN_TIMEOUT_SECONDS,
                        phase_step,
                        logical_session_id,
                    )
                    dimension_conclusion = None
                if not dimension_conclusion and isinstance(pending_conclusion, dict):
                    dimension_conclusion = pending_conclusion

                if dimension_conclusion:
                    await conv_manager.update_metadata(
                        session_id,
                        category,
                        _build_conclusion_meta_update(
                            state=CONCLUSION_STATE_CONFIRMED,
                            final=dimension_conclusion,
                            shown_at=user_count,
                            thread_completed=False,
                        ),
                    )
                    transition_msg = pending_msg or "收到你的确认，我将生成结论卡。"
                    yield f"data: {{\"chunk\": {json.dumps(transition_msg, ensure_ascii=False)} }}\n\n"
                    full_reply = transition_msg
                    yield f"data: {{\"conclusion_loading\": true}}\n\n"
                    yield f"data: {{\"dimension_conclusion\": {json.dumps(dimension_conclusion, ensure_ascii=False)} }}\n\n"
                    try:
                        await conv_manager.append_message(
                            session_id=session_id,
                            category=category,
                            message={
                                "role": "assistant",
                                "content": full_reply,
                                "session_id": logical_session_id,
                                "step_id": phase_step,
                                "agent_id": "coach",
                                "event": "assistant_reply",
                                "token_usage": _normalize_token_usage(None),
                            },
                        )
                        updated_card = await conv_manager.update_last_conclusion_card_payload(
                            session_id, category, dimension_conclusion
                        )
                        if not updated_card:
                            await conv_manager.append_message(
                                session_id=session_id,
                                category=category,
                                message={
                                    "role": "conclusion_card",
                                    "content": json.dumps(dimension_conclusion, ensure_ascii=False),
                                    "session_id": logical_session_id,
                                    "step_id": phase_step,
                                    "agent_id": "coach",
                                    "event": "dimension_conclusion",
                                    "card_type": "dimension_conclusion",
                                    "card_payload": dimension_conclusion,
                                },
                            )
                        await _append_note_json(
                            conv_manager,
                            session_id,
                            category,
                            "dimension_conclusion_confirmed",
                            {
                                "phase": phase_step,
                                "thread_id": logical_session_id,
                                "dimension_conclusion": dimension_conclusion,
                            },
                        )
                    except Exception as e:
                        logger.warning("append conclusion_card/note failed: %s", e)

                    _write_anchor_from_conclusion(
                        report_id=session_id,
                        phase_step=phase_step,
                        storage_root=storage_root,
                        conclusion=dimension_conclusion,
                    )
                    # 保留异步提炼（补充 personality/style/conflicts），不影响当前结论锚点直写
                    _trigger_anchor_refiner(
                        session_id,
                        phase_step,
                        category,
                        conv_manager,
                        storage_root,
                        dimension_conclusion=dimension_conclusion,
                        vip_level=vip_level,
                    )
                    try:
                        await AnalyticsService.record_chat_turn(
                            session_id=logical_session_id,
                            dimension=phase_step,
                            user_input_chars=len(user_content or ""),
                            llm_input_tokens=0,
                            llm_output_tokens=0,
                            log_index=None,
                        )
                    except Exception:
                        pass
                    yield f"data: {{\"done\": true, \"response\": {json.dumps(full_reply, ensure_ascii=False)} }}\n\n"
                    return

            elif pending_state == "rejected":
                rejected_snapshot = {
                    "summary": (pending_conclusion or {}).get("summary", ""),
                    "keywords": (pending_conclusion or {}).get("keywords", []),
                    "feedback": user_content,
                }
                await conv_manager.update_metadata(
                    session_id,
                    category,
                    _build_conclusion_meta_update(
                        state=CONCLUSION_STATE_REJECTED,
                        final=cmeta.get("final"),
                        feedback=user_content,
                        shown_at=conclusion_shown_at,
                        thread_completed=False,
                    ),
                )
                try:
                    await _append_note_json(
                        conv_manager,
                        session_id,
                        category,
                        "pending_conclusion_rejected",
                        {
                            "phase": phase_step,
                            "thread_id": logical_session_id,
                            "pending": pending_conclusion,
                            "feedback": user_content,
                            "decision_msg": pending_msg,
                        },
                    )
                except Exception:
                    pass
                if phase_step != "rumination":
                    try:
                        await conv_manager.remove_last_conclusion_card(session_id, category)
                    except Exception as e:
                        logger.warning("remove_last_conclusion_card on reject failed: %s", e)
                pending_conclusion = None
                rejected_feedback = user_content

        # 用户否定后：保留轻量反馈上下文（不做关键词规则）
        if rejected_feedback and not pending_conclusion:
            llm_messages.append(
                LLMMessage(
                    role="assistant",
                    content=f"[上一版结论未获认可] 用户反馈：{rejected_feedback[:200]}",
                )
            )

        # 2) 无 pending 时，不再走额外同步完成检测；仅依赖模型输出的 STATE_JSON 驱动 pending。

        try:
            sem = _get_llm_semaphore()
            stream_coro = llm.chat_stream(llm_messages, temperature=0.7)

            full_think = ""
            stream_hidden_filter = _build_stream_hidden_block_filter(
                block_markers=[("[STATE_JSON]", "[/STATE_JSON]")]
            )

            def _process_chunk(c):
                nonlocal full_reply, full_think
                out = []
                if isinstance(c, dict):
                    t = c.get("_t")
                    if t == "think_start":
                        out.append(f"data: {{\"think_start\": true}}\n\n")
                    elif t == "think_chunk":
                        tc = c.get("content", "")
                        if tc:
                            out.append(f"data: {{\"think_chunk\": {json.dumps(tc, ensure_ascii=False)} }}\n\n")
                    elif t == "think_end":
                        tc = c.get("content", "")
                        full_think = tc
                        out.append(f"data: {{\"think_end\": {json.dumps(tc, ensure_ascii=False)} }}\n\n")
                elif c:
                    full_reply += c
                    delta = stream_hidden_filter(full_reply)
                    if delta:
                        out.append(f"data: {{\"chunk\": {json.dumps(delta, ensure_ascii=False)} }}\n\n")
                return out

            if sem:
                async with sem:
                    async for chunk in stream_coro:
                        for ev in _process_chunk(chunk):
                            yield ev
            else:
                async for chunk in stream_coro:
                    for ev in _process_chunk(chunk):
                        yield ev
        except Exception as e:
            err = str(e)
            yield f"data: {{\"error\": {json.dumps(err, ensure_ascii=False)} }}\n\n"
            return
        stream_usage = _normalize_token_usage(getattr(llm, "_last_stream_usage", None))
        # 诊断 DeepSeek Context Cache：首 token 慢时查看 hit/miss
        if stream_usage and (stream_usage.get("prompt_cache_hit_tokens") or stream_usage.get("prompt_cache_miss_tokens")):
            logger.info(
                "[llm_stream] cache hit=%s miss=%s prompt=%s",
                stream_usage.get("prompt_cache_hit_tokens", 0),
                stream_usage.get("prompt_cache_miss_tokens", 0),
                stream_usage.get("prompt_tokens"),
            )

        # 3) 解析模型状态输出（STATE_JSON）并驱动 pending 状态
        raw_full_reply = full_reply
        visible_reply, state_obj = _split_visible_reply_and_state(raw_full_reply)
        full_reply = visible_reply

        # 保存助手回复（只保存用户可见文本）
        if full_reply:
            msg_payload = {
                "role": "assistant",
                "content": full_reply,
                "session_id": logical_session_id,
                "step_id": phase_step,
                "agent_id": "coach",
                "event": "assistant_reply",
                "token_usage": stream_usage,
            }
            if full_think:
                msg_payload["think_content"] = full_think
            await conv_manager.append_message(
                session_id=session_id,
                category=category,
                message=msg_payload,
            )
            if phase_step == "rumination" and _looks_like_markdown_table(full_reply):
                await conv_manager.append_message(
                    session_id=session_id,
                    category=category,
                    message={
                        "role": "table",
                        "content": full_reply,
                        "session_id": logical_session_id,
                        "step_id": phase_step,
                        "agent_id": "coach",
                        "event": "table_output",
                        "table_format": "markdown",
                    },
                )
        if state_obj and not cmeta.get("thread_completed"):
            state_name = str(state_obj.get("state") or "").strip().lower()
            draft = state_obj.get("draft")
            if phase_step == "rumination" and state_name == "pending_ready":
                state_name = "continue"
                draft = None
            if state_name == "pending_ready" and isinstance(draft, dict):
                await conv_manager.update_metadata(
                    session_id,
                    category,
                    _build_conclusion_meta_update(
                        state=CONCLUSION_STATE_PENDING,
                        draft=draft,
                        final=cmeta.get("final"),
                        shown_at=user_count,
                        thread_completed=False,
                    ),
                )
                try:
                    await _append_note_json(
                        conv_manager,
                        session_id,
                        category,
                        "pending_conclusion_created",
                        {
                            "phase": phase_step,
                            "thread_id": logical_session_id,
                            "pending_conclusion": draft,
                        },
                    )
                except Exception:
                    pass
                # 四阶段（非 rumination）立即推送结论卡草案，与前端 dimension_conclusion 事件对齐
                if phase_step != "rumination" and isinstance(draft, dict):
                    card_data = _normalize_draft_for_dimension_card(draft)
                    try:
                        yield "data: {\"conclusion_loading\": true}\n\n"
                        yield (
                            "data: "
                            + json.dumps({"dimension_conclusion": card_data}, ensure_ascii=False)
                            + "\n\n"
                        )
                        await conv_manager.append_message(
                            session_id=session_id,
                            category=category,
                            message={
                                "role": "conclusion_card",
                                "content": json.dumps(card_data, ensure_ascii=False),
                                "session_id": logical_session_id,
                                "step_id": phase_step,
                                "agent_id": "coach",
                                "event": "dimension_conclusion",
                                "card_type": "dimension_conclusion",
                                "card_payload": card_data,
                            },
                        )
                    except Exception as e:
                        logger.warning("pending_ready append conclusion_card failed: %s", e)
            elif state_name == "continue":
                # 无状态迁移，保持当前会话态
                pass

        # 每 20 轮触发后台锚点摘要
        user_count_after = user_count + (1 if user_content else 0)
        if user_count_after > 0 and user_count_after % 20 == 0 and phase_step != "rumination":
            _trigger_anchor_refiner(
                session_id,
                phase_step,
                category,
                conv_manager,
                storage_root,
                round_count=user_count_after,
                vip_level=vip_level,
            )

        # 4) 埋点：记录对话轮次
        try:
            await AnalyticsService.record_chat_turn(
                session_id=logical_session_id,
                dimension=phase_step,
                user_input_chars=len(user_content or ""),
                llm_input_tokens=int(stream_usage.get("prompt_tokens") or 0),
                llm_output_tokens=int(stream_usage.get("completion_tokens") or 0),
                log_index=None,
            )
        except Exception:
            pass

        yield (
            f"data: {{\"done\": true, \"response\": {json.dumps(full_reply, ensure_ascii=False)}, "
            f"\"token_usage\": {json.dumps(stream_usage, ensure_ascii=False)} }}\n\n"
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/thread/delete", response_model=SimpleChatResponse)
async def delete_thread(
    request: ThreadDeleteRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    删除某个线程：同时删除后端 report 中的会话文件与 session 绑定，保证前后端一致。
    """
    manager = get_activation_manager_for_code(request.activation_code)
    phase_val = (request.phase or "values").strip() or "values"
    phase_step = ReportRegistry.normalize_step_id(phase_val)
    rec = _resolve_activation_for_user(manager, request.activation_code, current_user)
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    root = get_effective_simple_root(rec)
    registry = ReportRegistry(base_dir=str(root))
    report = registry.get_by_activation_user(rec.code, user_id)
    if not report or not report.get("report_id"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报告不存在")
    report_id = report["report_id"]

    _assert_step_editable(
        registry=registry,
        report_id=report_id,
        phase_step=phase_step,
        current_user=current_user,
        rec=rec,
    )

    thread_id = (request.thread_id or "").strip()
    if not thread_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="thread_id 不能为空")

    file = registry.get_step_session_file(report_id, phase_step, thread_id)
    try:
        if file.is_file():
            file.unlink()
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除会话文件失败: {e}")

    updated = registry.remove_session(report_id, phase_step, thread_id) or {}
    step_payload = ((updated.get("steps") or {}).get(phase_step)) or {}
    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "deleted": True,
            "step_id": phase_step,
            "thread_id": thread_id,
            "remaining_thread_ids": step_payload.get("session_ids") or [],
            "selected_thread_id": step_payload.get("selected_session_id"),
            "step_locked": bool(step_payload.get("locked", False)),
        },
    )

