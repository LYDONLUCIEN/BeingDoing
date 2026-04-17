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
import logging
import re

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.core.llmapi.factory import create_llm_provider
from app.api.v1.auth import get_current_user, _is_debug_admin
from app.config.settings import settings
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
    build_conclusion_generation_messages,
    check_dimension_complete,
    finalize_conclusion_from_summary_text,
)
from app.services.analytics_service import AnalyticsService
from app.utils.report_registry import ReportRegistry, STEP_IDS, STEP_ORDER
from copy import deepcopy

from app.utils.rumination_progress import (
    MAX_FILTER_STEP,
    load_rumination_progress,
    max_reached_filter_step,
    save_rumination_progress,
)
from app.utils.rumination_table_widgets import build_table_widget_payload
from app.utils.rumination_ops import (
    gen_table,
    filter_strength,
    filter_match,
    extract_dimension_lists_for_rumination_table,
    structure_hypothesis_round1_table,
    is_rumination_hypothesis_pending,
    value_filter,
    passion_filter,
    reality_filter,
    similar_filter,
)
from app.utils.rumination_hypothesis_service import (
    ensure_row_has_pair_hypotheses,
    fill_hypothesis_columns_for_table,
    generate_hypothesis_pair_for_row,
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
    merge_dimension_conclusion_record,
    build_values_info_for_prompt,
)
from app.domain.conclusion_card_goals import cap_strengths_keywords_list, get_conclusion_card_goal
from app.domain.conclusion_card_payload import (
    REJECTED_DRAFT_SUPERSESSION_LINE,
    build_pending_main_dialogue_system_addon,
    build_state_json_draft_extension_protocol,
    format_rejected_conclusion_injection,
    sanitize_pending_conclusion_draft,
)
from app.domain.prompts import get_simple_chat_system_prompt, get_step_copy
from app.domain.rumination_prompt_strings import RUMINATION_CLOSING_SUMMARY_MAX_CHARS
from app.domain.rumination_step_guidance import (
    build_opening_context,
    build_opening_llm_messages,
    get_opening_mode,
    get_rumination_chat_step_addon,
    render_fixed_opening_zh,
)
from app.services.rumination_finalize import append_post_table_finalize_message
from app.services.rumination_init_greeting import synthesize_rumination_entry_greeting
from app.utils.rumination_background_text import compose_hypothesis_user_background
from app.utils.admin_policy import is_admin_debug_policy_enabled
from app.utils.admin_prompt_lab import resolve_simple_chat_prompt_override
from app.utils.admin_policy import is_admin_sandbox_enabled
from app.utils.super_admin import is_super_admin_user
from jinja2 import Environment

# ── 从子模块导入已拆分的函数 ──────────────────────────────────────────
from app.api.v1.simple_chat.stream_utils import (
    extract_json_object as _extract_json_object,
    extract_state_content_tokens as _extract_state_content_tokens,
    looks_like_markdown_table as _looks_like_markdown_table,
    split_visible_reply_and_state as _split_visible_reply_and_state,
    strip_hidden_blocks_for_stream as _strip_hidden_blocks_for_stream,
    build_stream_hidden_block_filter as _build_stream_hidden_block_filter,
    normalize_token_usage as _normalize_token_usage,
)
from app.api.v1.simple_chat.llm_providers import (
    get_dialogue_llm_provider as _get_dialogue_llm_provider,
    get_reasoning_llm_provider as _get_reasoning_llm_provider,
    to_non_reasoning_model as _to_non_reasoning_model,
    to_reasoning_model as _to_reasoning_model,
)
from app.api.v1.simple_chat.prompt_builder import (
    build_fallback_opening_question as _build_fallback_opening_question,
    get_or_create_thread_question_bank as _get_or_create_thread_question_bank,
    get_random_questions_for_phase as _get_random_questions_for_phase,
)
from app.api.v1.simple_chat.context_resolver import (
    storage_category as _storage_category,
    resolve_report_context as _resolve_report_context,
    resolve_activation_for_user as _resolve_activation_for_user,
    resolve_default_logical_thread_id as _resolve_default_logical_thread_id,
    skip_expired_for_debug as _skip_expired_for_debug,
    can_bypass_flow_limits as _can_bypass_flow_limits,
    resolve_prompt_lab_override_for_request as _resolve_prompt_lab_override_for_request,
    get_user_id_from_activation as _get_user_id_from_activation,
    load_basic_info_from_activation as _load_basic_info_from_activation,
    load_prior_context_from_activation as _load_prior_context_from_activation,
    is_step_locked as _is_step_locked,
    assert_step_editable as _assert_step_editable,
)

# 每阶段随机抽取的题目数量
SIMPLE_QUESTION_SAMPLE_SIZE = 6
# 发送给 LLM 的历史消息最大轮数（减少 token、加快响应）
MAX_HISTORY_TURNS = 30
# 并发 LLM 调用限制（0=不限制）
_LLM_SEM = None
PENDING_JUDGE_TIMEOUT_SECONDS = 20
CONCLUSION_GEN_TIMEOUT_SECONDS = 25
# 独立 POST「确认稿」可放宽：流式内嵌结论生成仍用 CONCLUSION_GEN_TIMEOUT_SECONDS，避免长占 SSE
CONCLUSION_DRAFT_HTTP_TIMEOUT_SECONDS = 90
PENDING_HEARTBEAT_SECONDS = 2.0
CONCLUSION_STATE_NONE = "none"
CONCLUSION_STATE_PENDING = "pending"
CONCLUSION_STATE_CONFIRMED = "confirmed"
CONCLUSION_STATE_REJECTED = "rejected"

# 用户否定/再聊聊后，每满 N 轮用户消息注入一次轻量 system 提醒（非第二模型）
CONCLUSION_REJECT_NUDGE_USER_TURNS = 3
CONCLUSION_REJECT_SYSTEM_NUDGE = (
    "[内部策略提醒·勿向用户复述] 用户此前否定了待确认结论或选择再聊聊，并已继续补充多轮对话。"
    "若当前信息已足以给出待确认草案，请在本轮回复中按需输出 STATE_JSON，且 state 须为 pending_ready，"
    "draft 含 summary 与 keywords（遵守系统内嵌协议）。"
)


def _trim_history_messages_for_llm(
    history_messages: List[dict], max_user_turns: int = MAX_HISTORY_TURNS
) -> List[dict]:
    """与主对话流一致：仅保留最近若干用户轮内的消息，抑制上下文与 token 随时间线性膨胀。"""
    turn_count = 0
    trimmed: List[dict] = []
    for m in reversed(history_messages or []):
        role = m.get("role") or "user"
        if role == "user":
            turn_count += 1
            if turn_count > max_user_turns:
                break
        if role in {"user", "assistant", "system"}:
            trimmed.insert(0, m)
    return trimmed


def _count_user_messages(messages: Optional[List[dict]]) -> int:
    return sum(1 for m in (messages or []) if (m.get("role") or "") == "user")


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


def _normalize_client_locale(locale: Optional[str]) -> str:
    if not locale:
        return "zh"
    s = str(locale).strip().lower().replace("_", "-")
    if s.startswith("en"):
        return "en"
    return "zh"


def _system_prompt_dimension_extras(
    phase_step: str,
    report: Optional[dict],
    reports_root: str,
    rumination_filter_step: Optional[int],
    locale: str,
) -> Tuple[str, str]:
    """purpose 的 values_info + rumination 子步注入段。"""
    rid = (report or {}).get("report_id") if report else None
    if not rid:
        return "", ""
    values_info = ""
    if phase_step == "purpose":
        values_info = build_values_info_for_prompt(rid, reports_root)
    rumination_step_addon = ""
    if phase_step == "rumination" and rumination_filter_step is not None:
        rumination_step_addon = get_rumination_chat_step_addon(rumination_filter_step, locale)
    return values_info, rumination_step_addon


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
        return ""
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


def _build_conclusion_meta_update(
    *,
    state: str,
    draft: Optional[Dict] = None,
    final: Optional[Dict] = None,
    feedback: Optional[str] = None,
    shown_at: Optional[int] = None,
    thread_completed: Optional[bool] = None,
) -> Dict:
    """写入结论状态（仅新字段）。"""
    is_confirmed = state == CONCLUSION_STATE_CONFIRMED
    is_pending = state == CONCLUSION_STATE_PENDING
    is_rejected = state == CONCLUSION_STATE_REJECTED
    update = {
        "conclusion_state": state,
        "conclusion_draft": draft if is_pending else None,
        "conclusion_final": final if final else None,
        "conclusion_feedback": (feedback or "") if is_rejected else "",
        "thread_completed": (is_confirmed if thread_completed is None else bool(thread_completed)),
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
    if phase_step == "strengths":
        kw_line = cap_strengths_keywords_list(keywords)
    else:
        kw_line = [str(k).strip() for k in keywords if str(k).strip()][:10]
    kw_text = "、".join(kw_line)
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


def _require_simple_chat_phase(phase: Optional[str]) -> str:
    """将 phase 解析为规范 step id；非法时返回 400，避免静默退回 values。"""
    try:
        return ReportRegistry.resolve_simple_chat_phase(phase)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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

    phase_step = _require_simple_chat_phase(phase)
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


def _pending_judge_goal_blurb(phase: str) -> str:
    """pending 判定器用：四步各一行阶段目标（values/strengths/interests/purpose）。"""
    p = (phase or "").strip().lower()
    if p not in {"values", "strengths", "interests", "purpose"}:
        return ""
    obj = (get_conclusion_card_goal(p).get("objective") or "").strip()
    if not obj:
        return ""
    return f"本阶段结论目标（供你理解用户是否在认可该方向，勿向用户复述本行）：{obj}\n"


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
    goal_line = _pending_judge_goal_blurb(phase)
    prompt = f"""你是职业咨询系统中的“确认状态判定器”。

当前阶段：{phase}
{goal_line}待确认总结摘要：{summary}
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
{goal_line}待确认总结摘要：{summary}
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
    goal_line = _pending_judge_goal_blurb(phase)
    token_prompt = f"""你是职业咨询系统中的“确认状态判定器”。

当前阶段：{phase}
{goal_line}待确认总结摘要：{summary}
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
    # 阶段：values / strengths / interests / purpose / rumination（必填，禁止省略）
    phase: str
    locale: Optional[str] = None
    rumination_filter_step: Optional[int] = None


class SimpleChatResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleInitRequest(BaseModel):
    activation_code: str
    phase: str
    thread_id: Optional[str] = None  # 新建对话时传入，后端按 thread_id 创建独立存储
    locale: Optional[str] = None  # zh | en，用于 step_intro 等展示文案


class SimpleHistoryResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: dict


class SimpleChatStreamRequest(BaseModel):
    activation_code: str
    message: str
    phase: str
    thread_id: Optional[str] = None  # 当前对话 id，用于加载/保存到对应记录
    # 可选：前端结论卡 UI 快照（诊断/后续扩展；不参与业务分支）
    client_conclusion_ui: Optional[Dict[str, Any]] = None
    locale: Optional[str] = None  # zh | en
    # 沉淀阶段当前筛选子步（1–7），用于注入主对话 system 小段指引
    rumination_filter_step: Optional[int] = None


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
    filter_table: Optional[dict] = None


class RuminationTableSubmitRequest(BaseModel):
    """提交筛选表。递进逻辑依赖非空的 table_data（整表行列表）；传 null 时服务端不会进入任一步的 if step==N and table_data 分支。"""

    model_config = ConfigDict(extra="ignore")

    activation_code: str
    # 表格进度按 report 落库，不依赖 thread；允许空串避免前端会话竞态导致无法提交
    thread_id: str = ""
    step: int
    table_data: Optional[List[Dict[str, Any]]] = None
    # 终步（7）多选提交时可传 id 列表，否则从 table_data 行内 __pick / _rumination_selected 读取
    selected_row_ids: Optional[List[str]] = None


class RuminationStepOpeningStreamRequest(BaseModel):
    """沉淀子步引导语流式生成（仅 opening_mode=llm 的子步）。"""

    model_config = ConfigDict(extra="ignore")

    activation_code: str
    filter_step: int
    thread_id: str = ""


class RuminationRegenerateHypothesesRequest(BaseModel):
    """假设子步（仅第 3 步）单行重新生成假设1、假设2。"""

    model_config = ConfigDict(extra="ignore")

    activation_code: str
    filter_step: int
    row_id: str


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
        mr = max_reached_filter_step(progress.get("filter_step_snapshots") or {})
        return SimpleChatResponse(
            code=200, message="success", data={"progress": progress, "max_reached_filter_step": mr}
        )
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
    )
    return SimpleChatResponse(code=200, message="success", data={"progress": progress})


def _rumination_snapshots_copy(progress: Dict[str, Any]) -> Dict[str, Any]:
    s = progress.get("filter_step_snapshots") or {}
    return deepcopy(s) if isinstance(s, dict) else {}


def _rumination_get_table_response(
    progress: Dict[str, Any],
    payload: Optional[dict],
) -> SimpleChatResponse:
    mr = max_reached_filter_step(progress.get("filter_step_snapshots") or {})
    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "table_widget": payload,
            "progress": progress,
            "max_reached_filter_step": mr,
        },
    )


def _rumination_opening_load_bundle(
    activation_code: str,
    current_user: dict,
):
    """
    读取报告、进度与价值观关键词，供 rumination 子步引导语使用。
    Returns:
        tuple[rec, reports_root, report_id, progress, values_list]
    """
    manager = get_activation_manager_for_code(activation_code)
    rec = _resolve_activation_for_user(manager, activation_code, current_user)
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
    progress = load_rumination_progress(reports_root, report_id)
    record_path = reports_root / report_id / "record.json"
    record_obj: Optional[dict] = None
    if record_path.is_file():
        try:
            raw_rec = json.loads(record_path.read_text(encoding="utf-8") or "{}")
            if isinstance(raw_rec, dict):
                record_obj = raw_rec
        except (json.JSONDecodeError, OSError, TypeError):
            record_obj = None
    values_list, _, _, _ = extract_dimension_lists_for_rumination_table(
        str(reports_root), report_id, record_obj
    )
    return rec, reports_root, report_id, progress, values_list


@router.get("/rumination-step-opening", response_model=SimpleChatResponse)
def rumination_step_opening(
    activation_code: str,
    filter_step: int = 1,
    current_user: dict = Depends(get_current_user),
):
    """子步引导：fixed 时返回完整文案（前端模拟流式）；llm 时 text 为 null，走流式接口。"""
    try:
        _rec, _rp, _rid, progress, values_list = _rumination_opening_load_bundle(
            activation_code, current_user
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("rumination-step-opening load failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    step = max(1, min(MAX_FILTER_STEP, int(filter_step)))
    ctx = build_opening_context(filter_step=step, progress=progress, values_list=values_list)
    mode = get_opening_mode(step)
    if mode == "llm":
        return SimpleChatResponse(
            code=200,
            message="success",
            data={"mode": "llm", "text": None, "filter_step": step},
        )
    text = render_fixed_opening_zh(step, ctx)
    return SimpleChatResponse(
        code=200,
        message="success",
        data={"mode": "fixed", "text": text, "filter_step": step},
    )


@router.post("/rumination-step-opening-stream")
async def rumination_step_opening_stream(
    request: RuminationStepOpeningStreamRequest,
    current_user: dict = Depends(get_current_user),
):
    """子步引导流式生成（SSE 事件与 /message/stream 的 chunk/think/done 兼容）。"""
    step = max(1, min(MAX_FILTER_STEP, int(request.filter_step)))
    if get_opening_mode(step) != "llm":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该子步使用固定引导语，请使用 GET /rumination-step-opening",
        )
    try:
        rec, _reports_root, _report_id, progress, values_list = _rumination_opening_load_bundle(
            request.activation_code, current_user
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    ctx = build_opening_context(filter_step=step, progress=progress, values_list=values_list)
    try:
        llm_messages = build_opening_llm_messages(step, ctx)
    except ValueError as e:
        logger.warning("rumination opening llm build failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="该子步未配置 LLM 引导提示词",
        ) from e

    manager = get_activation_manager_for_code(request.activation_code)
    try:
        _, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=request.activation_code,
            current_user=current_user,
            phase="rumination",
            thread_id=(request.thread_id or "").strip() or None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("rumination opening stream resolve context: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="会话上下文无效，请刷新后重试",
        ) from e

    if phase_step != "rumination":
        raise HTTPException(status_code=400, detail="仅支持沉淀阶段")

    session_id = report["report_id"]
    vip_level = getattr(rec, "vip_level", 1) or 1

    async def event_stream() -> AsyncIterator[str]:
        llm = _get_dialogue_llm_provider(vip_level=vip_level)
        if hasattr(llm, "_last_stream_usage"):
            try:
                setattr(llm, "_last_stream_usage", None)
            except Exception:
                pass
        full_reply = ""
        sem = _get_llm_semaphore()

        async def run_one() -> AsyncIterator[str]:
            nonlocal full_reply
            stream_coro = llm.chat_stream(llm_messages, temperature=0.65, max_tokens=600)
            async for piece in stream_coro:
                if isinstance(piece, dict):
                    t = piece.get("_t")
                    if t == "think_start":
                        yield 'data: {"think_start": true}\n\n'
                    elif t == "think_chunk":
                        tc = piece.get("content") or ""
                        if tc:
                            yield f"data: {json.dumps({'think_chunk': tc}, ensure_ascii=False)}\n\n"
                    elif t == "think_end":
                        te = piece.get("content")
                        yield f"data: {json.dumps({'think_end': te}, ensure_ascii=False)}\n\n"
                    continue
                if piece:
                    full_reply += piece
                    yield f"data: {json.dumps({'chunk': piece}, ensure_ascii=False)}\n\n"

        try:
            if sem:
                async with sem:
                    async for line in run_one():
                        yield line
            else:
                async for line in run_one():
                    yield line
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return

        text = full_reply.strip()
        stream_usage = _normalize_token_usage(getattr(llm, "_last_stream_usage", None))
        if text:
            try:
                await conv_manager.append_message(
                    session_id=session_id,
                    category=category,
                    message={
                        "role": "assistant",
                        "content": text,
                        "session_id": logical_session_id,
                        "step_id": phase_step,
                        "agent_id": "coach",
                        "event": "assistant_reply",
                        "token_usage": stream_usage,
                    },
                )
            except Exception as e:
                logger.warning("rumination opening append_message failed: %s", e)

        yield (
            f"data: {{\"done\": true, \"response\": {json.dumps(text, ensure_ascii=False)}, "
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


@router.post("/rumination-regenerate-hypotheses", response_model=SimpleChatResponse)
async def rumination_regenerate_hypotheses(
    request: RuminationRegenerateHypothesesRequest,
    current_user: dict = Depends(get_current_user),
):
    """筛选子步 3：对单行重新生成假设1、假设2（一次 LLM），已选假设由前端按槽位映射保留。"""
    step = int(request.filter_step)
    if step != 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持筛选子步 3 的假设重新生成",
        )
    row_id = str(request.row_id or "").strip()
    if not row_id:
        raise HTTPException(status_code=400, detail="row_id 无效")

    try:
        rec, reports_root, report_id, progress, values_list = _rumination_opening_load_bundle(
            request.activation_code, current_user
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    values_hint = "、".join(values_list[:8]) if values_list else ""
    root_rh = get_effective_simple_root(rec)
    registry_rh = ReportRegistry(base_dir=str(root_rh))
    report_rh = registry_rh.ensure_report(
        rec.code,
        (current_user or {}).get("user_id", ""),
        bind_session_id_for_ensure_report(rec),
    )
    prior_rh = _load_prior_context_from_activation(
        request.activation_code, "rumination", report_rh
    )
    user_bg = compose_hypothesis_user_background(
        values_hint=values_hint,
        prior_rumination_text=prior_rh,
    )
    snapshots = _rumination_snapshots_copy(progress)
    sk = str(step)
    ent = dict(snapshots.get(sk) or {})
    rows = ent.get("submitted")
    storage_key = "submitted"
    if rows is None:
        rows = ent.get("initial")
        storage_key = "initial"
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="当前子步无表格数据")

    idx = None
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            continue
        if str(r.get("id", "")) == row_id:
            idx = i
            break
    if idx is None:
        raise HTTPException(status_code=404, detail="未找到该行")

    row = dict(rows[idx])
    passion = str(row.get("热爱") or "")
    strength = str(row.get("优势") or "")
    match_reason = str(row.get("匹配原因") or "")
    vip_level = getattr(rec, "vip_level", 1) or 1
    llm = _get_dialogue_llm_provider(vip_level=vip_level)
    h1, h2 = await generate_hypothesis_pair_for_row(
        llm,
        passion=passion,
        strength=strength,
        match_reason=match_reason,
        user_background=user_bg,
        row_index=idx,
    )
    row["假设1"] = h1
    row["假设2"] = h2
    row["假设3"] = ""
    ensure_row_has_pair_hypotheses(row, passion=passion, strength=strength, row_index=idx)
    row["用户确认的假设"] = ""

    new_rows = list(rows)
    new_rows[idx] = row
    ent = {**ent, storage_key: new_rows}
    snapshots[sk] = ent

    save_kw: Dict[str, Any] = {"filter_step_snapshots": snapshots}
    cur_fs = int(progress.get("filter_step") or 0)
    if cur_fs == step:
        save_kw["filter_table"] = new_rows

    progress = save_rumination_progress(reports_root, report_id, **save_kw)
    payload = build_table_widget_payload(step, new_rows, values_list)
    return _rumination_get_table_response(progress, payload)


def _build_table_widget_payload(
    step: int,
    rows: List[dict],
    columns: List[dict],
    editable_cols: List[str],
    guide_text: str = "",
) -> dict:
    """构建 table_widget 消息的 card_payload"""
    return {
        "columns": columns,
        "rows": rows,
        "editableCols": editable_cols,
        "guideText": guide_text,
        "step": step,
    }


RUMINATION_GUIDE_ALL_PENDING_ZH = (
    "如果您对生成的假设内容不够确定，可以与我交流，或者可以点击蓝色的按钮，重新生成新的假设。"
)

RUMINATION_GUIDE_ZERO_SELECTION_ZH = (
    "注意到您觉得所有选项都不太匹配，但或许我们只是还没发现它们各自的可能性。"
    "接下来，让我们一起探索一下。"
)

# 兼容旧名：第 1 步无优势标记 / 第 2 步全不匹配，共用同一引导
RUMINATION_GUIDE_ZERO_STRENGTH_ZH = RUMINATION_GUIDE_ZERO_SELECTION_ZH
RUMINATION_GUIDE_ALL_MISMATCH_ZH = RUMINATION_GUIDE_ZERO_SELECTION_ZH


def _rumination_clear_snapshots_from_step(snapshots: Dict[str, Any], start: int) -> None:
    """删除从 start 到 7 的子步快照（含），用于回退或直达终筛后避免脏数据。"""
    for d in range(max(1, int(start)), MAX_FILTER_STEP + 1):
        snapshots.pop(str(d), None)


def _rumination_step7_rows_for_widget(rows: List[dict]) -> List[dict]:
    """终步表格增加 __pick 字段供前端多选。"""
    out: List[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        x = dict(r)
        x.setdefault("__pick", False)
        out.append(x)
    return out


def _rumination_parse_selected_row_ids(
    table_data: Optional[List[Dict[str, Any]]],
    selected_row_ids: Optional[List[str]],
) -> List[str]:
    if selected_row_ids:
        return [str(x).strip() for x in selected_row_ids if str(x).strip()]
    if not table_data:
        return []
    out: List[str] = []
    for r in table_data:
        if not isinstance(r, dict):
            continue
        if r.get("__pick") is True or r.get("_rumination_selected") is True:
            rid = str(r.get("id", "")).strip()
            if rid:
                out.append(rid)
    seen = set()
    uniq: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def _rumination_strip_meta_keys(rows: List[dict]) -> List[dict]:
    out: List[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        x = dict(r)
        x.pop("__pick", None)
        x.pop("_rumination_selected", None)
        out.append(x)
    return out


def _rumination_step7_via_456_chain(rows: List[dict]) -> List[dict]:
    """第 4 步形态的表格（含「工作目的」列）经 激情→现实→similar 得到终步展示行。"""
    if not rows:
        return []
    s5 = passion_filter(rows)
    s6 = reality_filter(s5)
    return similar_filter(s6)


def _rumination_step7_preserve_incoming_rows(incoming: List[dict]) -> List[dict]:
    """假设后任一步筛选得到 0 行时：保留用户本步提交的每一行，投射为终步两列。"""
    out: List[dict] = []
    for r in incoming:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "id": str(r.get("id", "")),
                "用户确认的假设": (r.get("用户确认的假设") or "").strip(),
            }
        )
    return out


def _rumination_persist_skip_to_step7(
    reports_root: Path,
    report_id: str,
    snapshots: Dict[str, Any],
    step7_rows: List[dict],
    values_list: List[str],
    *,
    filter_early_terminated: bool,
    clear_snapshots_from: int,
    preserve_step6_initial: Optional[List[dict]] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], int]:
    """直达第 7 步：清理中间快照、写入 7 的 initial、更新 progress。

    preserve_step6_initial：短链跳过第 6 步 UI 时仍写入第 6 步 initial，便于用户「上一阶段」回看（能看即可）。
    """
    _rumination_clear_snapshots_from_step(snapshots, clear_snapshots_from)
    wrows = _rumination_step7_rows_for_widget(step7_rows)
    s7 = snapshots.setdefault("7", {})
    if s7.get("initial") is None:
        s7["initial"] = deepcopy(_rumination_strip_meta_keys(wrows))
    s7["submitted"] = None
    snapshots["7"] = s7
    if preserve_step6_initial is not None:
        s6 = snapshots.setdefault("6", {})
        s6["initial"] = deepcopy(preserve_step6_initial)
        s6["submitted"] = None
        snapshots["6"] = s6
    progress = save_rumination_progress(
        reports_root,
        report_id,
        main_section="filter",
        filter_step=7,
        filter_table=wrows,
        filter_step_snapshots=snapshots,
        filter_early_terminated=filter_early_terminated,
        filter_terminate_reason=None,
    )
    next_table = build_table_widget_payload(7, wrows, values_list)
    return progress, next_table, 7


@router.post("/rumination-table-submit", response_model=SimpleChatResponse)
async def rumination_table_submit(
    request: RuminationTableSubmitRequest,
    current_user: dict = Depends(get_current_user),
):
    """提交 rumination 筛选表格数据，更新 progress，并可能返回下一步表格。"""
    try:
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
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("rumination-table-submit 报告上下文无效: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        report_id = report.get("report_id")
        if not report_id:
            raise HTTPException(status_code=500, detail="报告初始化失败")
        reports_root = root / "reports"
        step = max(1, min(MAX_FILTER_STEP, request.step))
        progress0 = load_rumination_progress(reports_root, report_id)
        snapshots = _rumination_snapshots_copy(progress0)
        sk = str(step)
        ent = snapshots.setdefault(sk, {})
        table_data = request.table_data
        if table_data is not None:
            if ent.get("initial") is None:
                ent["initial"] = deepcopy(table_data)
            ent["submitted"] = deepcopy(table_data)
            snapshots[sk] = ent

        progress = save_rumination_progress(
            reports_root,
            report_id,
            filter_step=step,
            filter_table=table_data,
            filter_step_snapshots=snapshots,
        )

        # ── 读取维度关键词（step 3 LLM 需要 values_hint，假设后各步需要 values_list）──
        record_path = reports_root / report_id / "record.json"
        record_obj: Optional[dict] = None
        if record_path.is_file():
            try:
                raw_rec = json.loads(record_path.read_text(encoding="utf-8") or "{}")
                if isinstance(raw_rec, dict):
                    record_obj = raw_rec
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        values_list, strengths_list, interests_list, _purpose = extract_dimension_lists_for_rumination_table(
            str(reports_root), report_id, record_obj
        )
        values_hint = "、".join(values_list[:8]) if values_list else ""
        passions = interests_list if interests_list else ["热爱1", "热爱2"]
        strengths_for_gen = strengths_list if strengths_list else ["优势1", "优势2"]

        next_table = None
        next_step_val = step
        dimension_conclusion_payload: Optional[dict] = None
        rumination_submit_next_action: Optional[str] = None
        closing_summary_for_epilogue = ""
        rumination_finalize_via_short_path = False

        if step == 1 and table_data:
            filtered = filter_strength(table_data)
            if not filtered:
                ent1 = snapshots.setdefault("1", {})
                initial1 = ent1.get("initial")
                if not initial1:
                    initial1 = gen_table(strengths_for_gen, passions)
                    ent1["initial"] = deepcopy(initial1)
                rows1 = deepcopy(initial1)
                ent1["submitted"] = None
                snapshots["1"] = ent1
                _rumination_clear_snapshots_from_step(snapshots, 2)
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    main_section="filter",
                    filter_step=1,
                    filter_table=rows1,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                next_table = build_table_widget_payload(1, rows1, values_list)
                if next_table:
                    base_g = str(next_table.get("guideText") or "")
                    next_table["guideText"] = f"{RUMINATION_GUIDE_ZERO_SELECTION_ZH}\n\n{base_g}".strip()
                next_step_val = 1
            else:
                step2_rows = filter_match(filtered)
                next_table = _build_table_widget_payload(
                    step=2,
                    rows=step2_rows,
                    columns=[
                        {"key": "id", "label": "id"},
                        {"key": "热爱", "label": "热爱"},
                        {"key": "优势", "label": "优势"},
                        {"key": "匹配性", "label": "匹配性", "options": ["匹配", "不匹配"]},
                        {"key": "匹配原因", "label": "匹配原因"},
                    ],
                    editable_cols=["匹配性"],
                    guide_text="这是匹配分析结果。如不同意某行标记，可直接修改。确认后我们将基于匹配结果提出假设。",
                )
                next_step_val = 2
                s2 = snapshots.setdefault("2", {})
                # 每次从第 1 步生成第 2 步表时同步 initial，避免沿用过期快照行数导致引导语 row_count 错误
                if step2_rows:
                    s2["initial"] = deepcopy(step2_rows)
                    s2["submitted"] = None
                snapshots["2"] = s2
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    filter_step=2,
                    filter_table=step2_rows,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )

        elif step == 2 and table_data:
            # step 2 → 3: 结构化假设表 + LLM 填充假设
            step3_rows = structure_hypothesis_round1_table(table_data)
            if not step3_rows:
                ent2 = snapshots.setdefault("2", {})
                initial2 = ent2.get("initial")
                if not initial2:
                    prev_source = snapshots.get("1", {}).get("submitted")
                    if prev_source is None:
                        prev_source = progress0.get("filter_table") or []
                    filtered = filter_strength(prev_source)
                    initial2 = filter_match(filtered) if filtered else []
                if not initial2:
                    raise HTTPException(
                        status_code=400,
                        detail="当前无法恢复第 2 步初始表，请从第 1 步重新确认。",
                    )
                rows2 = deepcopy(initial2)
                ent2["submitted"] = None
                snapshots["2"] = ent2
                _rumination_clear_snapshots_from_step(snapshots, 3)
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    main_section="filter",
                    filter_step=2,
                    filter_table=rows2,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                next_table = build_table_widget_payload(2, rows2, values_list)
                if next_table:
                    base_g = str(next_table.get("guideText") or "")
                    next_table["guideText"] = f"{RUMINATION_GUIDE_ZERO_SELECTION_ZH}\n\n{base_g}".strip()
                next_step_val = 2
            else:
                vip_level = getattr(rec, "vip_level", 1) or 1
                llm = _get_dialogue_llm_provider(vip_level=vip_level)
                prior_h = _load_prior_context_from_activation(
                    request.activation_code, "rumination", report
                )
                hypo_bg = compose_hypothesis_user_background(
                    values_hint=values_hint,
                    prior_rumination_text=prior_h,
                )
                step3_rows = await fill_hypothesis_columns_for_table(
                    llm, step3_rows, user_background=hypo_bg
                )
                next_table = build_table_widget_payload(3, step3_rows, values_list)
                next_step_val = 3
                s3 = snapshots.setdefault("3", {})
                if s3.get("initial") is None:
                    s3["initial"] = deepcopy(step3_rows)
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    filter_step=3,
                    filter_table=step3_rows,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )

        elif step == 3 and table_data:
            # 单轮假设 → 价值观入口（原 step5→6 的 value_filter）
            finalized: List[dict] = []
            for r in table_data:
                row = dict(r)
                if not (row.get("用户确认的假设") or "").strip():
                    row["用户确认的假设"] = "暂未选定"
                finalized.append(row)
            valid_count = sum(
                1 for r in finalized if not is_rumination_hypothesis_pending(r.get("用户确认的假设"))
            )
            if valid_count == 0:
                ent3 = snapshots.setdefault("3", {})
                initial3 = ent3.get("initial")
                if not initial3:
                    initial3 = deepcopy(finalized)
                    ent3["initial"] = deepcopy(initial3)
                rows3 = deepcopy(initial3)
                ent3["submitted"] = None
                snapshots["3"] = ent3
                _rumination_clear_snapshots_from_step(snapshots, 4)
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    main_section="filter",
                    filter_step=3,
                    filter_table=rows3,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                next_table = build_table_widget_payload(3, rows3, values_list)
                if next_table:
                    base_g = str(next_table.get("guideText") or "")
                    next_table["guideText"] = f"{RUMINATION_GUIDE_ALL_PENDING_ZH}\n\n{base_g}".strip()
                next_step_val = 3
            else:
                step4_rows = value_filter(finalized, values_list)
                if not step4_rows:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="没有可进入价值观筛选的有效假设，请至少保留一行非「暂未选定」的有效选择。",
                    )
                if 1 <= len(step4_rows) <= 3:
                    step7_r = _rumination_step7_via_456_chain(step4_rows)
                    if not step7_r:
                        step7_r = _rumination_step7_preserve_incoming_rows(step4_rows)
                    progress, next_table, next_step_val = _rumination_persist_skip_to_step7(
                        reports_root,
                        report_id,
                        snapshots,
                        step7_r,
                        values_list,
                        filter_early_terminated=True,
                        clear_snapshots_from=4,
                    )
                else:
                    next_table = build_table_widget_payload(4, step4_rows, values_list)
                    next_step_val = 4
                    s4 = snapshots.setdefault("4", {})
                    if s4.get("initial") is None:
                        s4["initial"] = deepcopy(step4_rows)
                    progress = save_rumination_progress(
                        reports_root,
                        report_id,
                        filter_step=4,
                        filter_table=step4_rows,
                        filter_step_snapshots=snapshots,
                        filter_early_terminated=False,
                        filter_terminate_reason=None,
                    )

        elif step == 4 and table_data:
            step5_rows = passion_filter(table_data)
            if not step5_rows:
                step7_r = _rumination_step7_preserve_incoming_rows(deepcopy(table_data))
                progress, next_table, next_step_val = _rumination_persist_skip_to_step7(
                    reports_root,
                    report_id,
                    snapshots,
                    step7_r,
                    values_list,
                    filter_early_terminated=True,
                    clear_snapshots_from=5,
                )
            elif 1 <= len(step5_rows) <= 3:
                step7_r = _rumination_step7_via_456_chain(step5_rows)
                if not step7_r:
                    step7_r = _rumination_step7_preserve_incoming_rows(step5_rows)
                progress, next_table, next_step_val = _rumination_persist_skip_to_step7(
                    reports_root,
                    report_id,
                    snapshots,
                    step7_r,
                    values_list,
                    filter_early_terminated=True,
                    clear_snapshots_from=5,
                )
            else:
                next_table = build_table_widget_payload(5, step5_rows, values_list)
                next_step_val = 5
                s5 = snapshots.setdefault("5", {})
                if s5.get("initial") is None:
                    s5["initial"] = deepcopy(step5_rows)
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    filter_step=5,
                    filter_table=step5_rows,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )

        elif step == 5 and table_data:
            incoming5 = deepcopy(table_data)
            step6_rows = reality_filter(table_data)
            if not step6_rows:
                step7_r = _rumination_step7_preserve_incoming_rows(incoming5)
                progress, next_table, next_step_val = _rumination_persist_skip_to_step7(
                    reports_root,
                    report_id,
                    snapshots,
                    step7_r,
                    values_list,
                    filter_early_terminated=True,
                    clear_snapshots_from=5,
                )
            elif 1 <= len(step6_rows) <= 3:
                step7_r = _rumination_step7_via_456_chain(step6_rows)
                if not step7_r:
                    step7_r = _rumination_step7_preserve_incoming_rows(step6_rows)
                progress, next_table, next_step_val = _rumination_persist_skip_to_step7(
                    reports_root,
                    report_id,
                    snapshots,
                    step7_r,
                    values_list,
                    filter_early_terminated=True,
                    clear_snapshots_from=5,
                    preserve_step6_initial=step6_rows,
                )
            else:
                next_table = build_table_widget_payload(6, step6_rows, values_list)
                next_step_val = 6
                s6 = snapshots.setdefault("6", {})
                if s6.get("initial") is None:
                    s6["initial"] = deepcopy(step6_rows)
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    filter_step=6,
                    filter_table=step6_rows,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )

        elif step == 6 and table_data:
            incoming6 = deepcopy(table_data)
            step7_plain = similar_filter(table_data)
            if not step7_plain:
                step7_plain = _rumination_step7_preserve_incoming_rows(incoming6)
                progress, next_table, next_step_val = _rumination_persist_skip_to_step7(
                    reports_root,
                    report_id,
                    snapshots,
                    step7_plain,
                    values_list,
                    filter_early_terminated=True,
                    clear_snapshots_from=6,
                    preserve_step6_initial=incoming6,
                )
            else:
                wrows = _rumination_step7_rows_for_widget(step7_plain)
                s7 = snapshots.setdefault("7", {})
                if s7.get("initial") is None:
                    s7["initial"] = deepcopy(_rumination_strip_meta_keys(wrows))
                s7["submitted"] = None
                snapshots["7"] = s7
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    main_section="filter",
                    filter_step=7,
                    filter_table=wrows,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                next_table = build_table_widget_payload(7, wrows, values_list)
                next_step_val = 7

        elif step == 7 and table_data is not None:
            sel_ids = _rumination_parse_selected_row_ids(table_data, request.selected_row_ids)
            if not (1 <= len(sel_ids) <= 3):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请在左侧点选 1–3 行方向后再点确认",
                )
            id_set = set(sel_ids)
            by_id: Dict[str, dict] = {}
            for r in table_data or []:
                if not isinstance(r, dict):
                    continue
                rid = str(r.get("id", "")).strip()
                if rid in id_set:
                    clean = _rumination_strip_meta_keys([dict(r)])[0]
                    by_id[rid] = clean
            ordered = [by_id[i] for i in sel_ids if i in by_id]
            if len(ordered) != len(sel_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="所选行与当前表格不一致，请刷新后重试",
                )
            wdone = [{**dict(r), "__pick": True} for r in ordered]
            # 在覆盖 progress 之前读取：短链直达终步时曾为 True，用于结语分支
            rumination_finalize_via_short_path = bool(progress.get("filter_early_terminated"))
            closing_summary_for_epilogue = "；".join(
                str(r.get("用户确认的假设") or "").strip() for r in ordered
            )[:RUMINATION_CLOSING_SUMMARY_MAX_CHARS]
            s7 = snapshots.setdefault("7", {})
            s7["submitted"] = deepcopy(_rumination_strip_meta_keys(wdone))
            snapshots["7"] = s7
            progress = save_rumination_progress(
                reports_root,
                report_id,
                main_section="final_choice",
                filter_step=7,
                filter_table=wdone,
                filter_step_snapshots=snapshots,
                filter_early_terminated=False,
                filter_terminate_reason=None,
            )
            next_table = None
            next_step_val = 7
            rumination_submit_next_action = "rumination_finalize_transition"

        # 终步确认后写入会话结语：见 ``append_post_table_finalize_message``（短链固定 / 正常 LLM；非流式与 submit 同请求）。
        if rumination_submit_next_action == "rumination_finalize_transition":
            try:
                mgr_e = get_activation_manager_for_code(request.activation_code)
                _rec_e, _rep_e, _ph_e, log_sid_e, cat_e, conv_e = _resolve_report_context(
                    manager=mgr_e,
                    activation_code=request.activation_code,
                    current_user=current_user,
                    phase="rumination",
                    thread_id=(request.thread_id or "").strip() or None,
                )
                vip_e = getattr(rec, "vip_level", 1) or 1
                llm_e = _get_dialogue_llm_provider(vip_level=vip_e)
                await append_post_table_finalize_message(
                    llm=llm_e,
                    conv_manager=conv_e,
                    report_session_id=report["report_id"],
                    category=cat_e,
                    logical_session_id=log_sid_e,
                    via_short_path=rumination_finalize_via_short_path,
                    selected_summary=closing_summary_for_epilogue,
                    normalize_token_usage=_normalize_token_usage,
                )
            except Exception as e:
                logger.warning("rumination closing epilogue skipped: %s", e)

        snaps = progress.get("filter_step_snapshots") or {}
        data: dict = {
            "progress": progress,
            "next_step": next_step_val,
            "max_reached_filter_step": max_reached_filter_step(snaps),
        }
        if next_table:
            data["next_table_widget"] = next_table
        if dimension_conclusion_payload is not None:
            data["dimension_conclusion"] = dimension_conclusion_payload
            data["next_action"] = "rumination_conclusion_insert"
        elif rumination_submit_next_action:
            data["next_action"] = rumination_submit_next_action

        return SimpleChatResponse(code=200, message="success", data=data)
    except HTTPException:
        raise
    except Exception:
        logger.exception("rumination-table-submit 未预期错误")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="表格提交失败，请稍后重试",
        ) from None


@router.get("/rumination-get-table", response_model=SimpleChatResponse)
async def rumination_get_table(
    activation_code: str,
    step: Optional[int] = 1,
    reset_initial: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """获取 rumination 筛选流程指定步的表格；支持快照恢复与 reset_initial 回到该步初始表。"""
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
    record_path = reports_root / report_id / "record.json"
    record_obj: Optional[dict] = None
    if record_path.is_file():
        try:
            raw = json.loads(record_path.read_text(encoding="utf-8") or "{}")
            if isinstance(raw, dict):
                record_obj = raw
        except (json.JSONDecodeError, OSError, TypeError):
            record_obj = None
    values_list, strengths_list, interests_list, _purpose = extract_dimension_lists_for_rumination_table(
        str(reports_root), report_id, record_obj
    )
    passions = interests_list if interests_list else ["热爱1", "热爱2"]
    strengths_list = strengths_list if strengths_list else ["优势1", "优势2"]

    step = max(1, min(MAX_FILTER_STEP, int(step or 1)))
    snapshots = _rumination_snapshots_copy(progress)
    sk = str(step)

    def _persist(rows: List[dict], snap: Dict[str, Any]) -> Dict[str, Any]:
        kw: Dict[str, Any] = dict(
            filter_step=step,
            filter_table=rows,
            filter_step_snapshots=snap,
        )
        # 首次拉取第 1 步表时同步进入筛选段，否则前端仅靠 progress 不会请求 get-table
        if step == 1 and (progress.get("main_section") or "opening") in (
            "opening",
            "review",
        ):
            kw["main_section"] = "filter"
            kw["filter_early_terminated"] = False
        return save_rumination_progress(reports_root, report_id, **kw)

    if reset_initial:
        ent = snapshots.get(sk) or {}
        initial = ent.get("initial")
        if initial is None:
            return SimpleChatResponse(
                code=400,
                message="该步暂无初始表格快照，无法重新填写",
                data={"progress": progress, "table_widget": None},
            )
        # 从本步起之后整段作废：删除后续子步快照，本步恢复 initial、清空 submitted
        for d in range(step + 1, MAX_FILTER_STEP + 1):
            snapshots.pop(str(d), None)
        rows = deepcopy(initial)
        if step == 7:
            rows = _rumination_step7_rows_for_widget(rows)
        ent = {**ent, "submitted": None}
        snapshots[sk] = ent
        # 与筛选主线对齐：回到 filter、当前子步；清除提前终止标记
        hr = 1 if step <= 3 else 2
        prog = save_rumination_progress(
            reports_root,
            report_id,
            main_section="filter",
            filter_step=step,
            filter_table=rows,
            filter_row_cursor=0,
            hypothesis_round=hr,
            filter_early_terminated=False,
            filter_terminate_reason=None,
            filter_step_snapshots=snapshots,
        )
        payload = build_table_widget_payload(step, rows, values_list)
        return _rumination_get_table_response(prog, payload)

    ent_sub = snapshots.get(sk) or {}
    if ent_sub.get("submitted") is not None:
        rows = deepcopy(ent_sub["submitted"])
        if step == 7:
            rows = _rumination_step7_rows_for_widget(rows)
        prog = _persist(rows, snapshots)
        payload = build_table_widget_payload(step, rows, values_list)
        return _rumination_get_table_response(prog, payload)

    if step == 1:
        rows = gen_table(strengths_list, passions)
        ent = snapshots.setdefault(sk, {})
        if ent.get("initial") is None:
            ent["initial"] = deepcopy(rows)
            snapshots[sk] = ent
        prog = _persist(rows, snapshots)
        payload = build_table_widget_payload(step, rows, values_list)
        return _rumination_get_table_response(prog, payload)

    if step == 2:
        prev_source = snapshots.get("1", {}).get("submitted")
        if prev_source is None:
            prev_source = progress.get("filter_table") or []
        filtered = filter_strength(prev_source)
        rows = filter_match(filtered)
        if not rows:
            return _rumination_get_table_response(progress, None)
        ent = snapshots.setdefault(sk, {})
        if ent.get("initial") is None:
            ent["initial"] = deepcopy(rows)
            snapshots[sk] = ent
        prog = _persist(rows, snapshots)
        payload = build_table_widget_payload(step, rows, values_list)
        return _rumination_get_table_response(prog, payload)

    # ── step 3-7: 先查快照，无快照则从前一步 submitted 生成 ──
    ent_any = snapshots.get(sk) or {}
    for key in ("submitted", "initial"):
        r0 = ent_any.get(key)
        if r0 is not None:
            rows = deepcopy(r0)
            if step == 7:
                rows = _rumination_step7_rows_for_widget(rows)
            prog = _persist(rows, snapshots)
            payload = build_table_widget_payload(step, rows, values_list)
            return _rumination_get_table_response(prog, payload)

    # 无快照：从前一步 submitted 生成
    prev_sk = str(step - 1)
    prev_submitted = (snapshots.get(prev_sk) or {}).get("submitted")
    if prev_submitted is None:
        return _rumination_get_table_response(progress, None)

    rows = None
    if step == 3:
        rows = structure_hypothesis_round1_table(prev_submitted)
        if rows:
            vip_level = getattr(rec, "vip_level", 1) or 1
            llm = _get_dialogue_llm_provider(vip_level=vip_level)
            values_hint = "、".join(values_list[:8]) if values_list else ""
            prior_gt = _load_prior_context_from_activation(activation_code, "rumination", report)
            hypo_bg_gt = compose_hypothesis_user_background(
                values_hint=values_hint,
                prior_rumination_text=prior_gt,
            )
            rows = await fill_hypothesis_columns_for_table(
                llm, rows, user_background=hypo_bg_gt
            )
    elif step == 4:
        rows = value_filter(prev_submitted, values_list)
    elif step == 5:
        rows = passion_filter(prev_submitted)
    elif step == 6:
        rows = reality_filter(prev_submitted)
    elif step == 7:
        rows = similar_filter(prev_submitted)
        if rows:
            rows = _rumination_step7_rows_for_widget(rows)

    if not rows:
        return _rumination_get_table_response(progress, None)

    ent = snapshots.setdefault(sk, {})
    if ent.get("initial") is None:
        ent["initial"] = deepcopy(_rumination_strip_meta_keys(rows) if step == 7 else rows)
        snapshots[sk] = ent
    prog = _persist(rows, snapshots)
    payload = build_table_widget_payload(step, rows, values_list)
    return _rumination_get_table_response(prog, payload)


def _build_system_prompt(
    phase: str,
    question_bank: str = "",
    basic_info: str = "暂无",
    prior_context: str = "",
    template_override: Optional[str] = None,
    extra_goal_hint: str = "",
    *,
    values_info: str = "",
    rumination_step_addon: str = "",
) -> str:
    """根据阶段构建 system prompt（通过模板渲染，避免超长硬编码）。"""
    prior_block = f"\n\n以下是该来访者在上一轮咨询中的谈话结果，供你参考：\n{prior_context}" if prior_context.strip() else ""
    context = {
        "phase": phase,
        "question_bank": question_bank,
        "basic_info": basic_info,
        "prior_block": prior_block,
        "values_info": (values_info or "").strip(),
        "rumination_step_addon": (rumination_step_addon or "").strip(),
    }
    if (template_override or "").strip():
        env = Environment(trim_blocks=True, lstrip_blocks=True)
        base_prompt = env.from_string(template_override).render(**context)
    else:
        base_prompt = get_simple_chat_system_prompt(context)
    if (extra_goal_hint or "").strip():
        base_prompt = f"{base_prompt}\n\n[管理员调试目标补充]\n{extra_goal_hint.strip()}"
    # 机器协议：每轮回复末尾输出状态 JSON，后端据此驱动 pending 状态机（不会展示给前端）。
    protocol = f"""

[输出协议 - 必须遵守]
在你的自然语言回复末尾，追加如下块（严格 JSON）：
[STATE_JSON]
{{"state":"continue|pending_ready","draft":{{"summary":"...","keywords":["..."]}}}}
[/STATE_JSON]
（draft 可含本阶段扩展字段，见下；须输出合法嵌套 JSON。）

规则：
1) 仅当你判断“已可进入结论确认”时，state 才能是 pending_ready。
2) state=continue 时，draft 置为 null。
3) state=pending_ready 时，draft.summary 必填，draft.keywords 为数组（可为空但应尽量给出）。
{build_state_json_draft_extension_protocol(phase)}

【用户可见正文 - 硬性禁止】
- 不要在自然语言里提及本协议、隐藏块名称、state 取值英文名、或「JSON / 待确认草案 / 机器协议」等字眼。
- 禁止用「系统将弹出结论卡」「即将输出 pending」「严格遵循协议」等元话术代替真实隐藏块；界面是否出卡仅由隐藏块触发，口头承诺无效。
- 对用户只说话题本身（如价值观、优势、小结），就像没有后台协议存在。
"""
    return f"{base_prompt}\n{protocol}"


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


@router.post("/message", response_model=SimpleChatResponse, deprecated=True)
async def simple_chat(
    request: SimpleChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    [DEPRECATED] 简单模式的单轮对话（同步版本）。
    前端已全部迁移到 /message/stream 流式端点，此端点仅作降级保留。
    """
    manager = get_activation_manager_for_code(request.activation_code)
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=request.phase,
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
    _root = get_effective_simple_root(rec)
    reports_root = str(Path(_root) / "reports")
    loc = _normalize_client_locale(request.locale)
    vi, ra = _system_prompt_dimension_extras(
        phase_step,
        report,
        reports_root,
        request.rumination_filter_step,
        loc,
    )
    system_prompt = _build_system_prompt(
        phase_step,
        question_bank=question_bank,
        basic_info=basic_info,
        prior_context=prior_context,
        template_override=(override_cfg or {}).get("template"),
        extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
        values_info=vi,
        rumination_step_addon=ra,
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
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=request.phase,
        thread_id=request.thread_id,
    )
    if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="激活码已过期（历史记录已保留，可以用于回放或导出）",
        )
    session_id = report["report_id"]
    init_loc = _normalize_client_locale(getattr(request, "locale", None))

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
                "step_intro": get_step_copy(phase_step, "intro", init_loc),
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

    # 沉淀阶段：首轮开场白见 ``synthesize_rumination_entry_greeting``
    if phase_step == "rumination":
        vip_r = getattr(rec, "vip_level", 1) or 1
        llm_r = _get_dialogue_llm_provider(vip_level=vip_r)
        basic_info_r = _load_basic_info_from_activation(request.activation_code)
        prior_r = _load_prior_context_from_activation(
            request.activation_code, phase_step, report
        )
        reply_text, token_usage = await synthesize_rumination_entry_greeting(
            llm_r,
            basic_info=basic_info_r,
            prior_block=prior_r,
            normalize_token_usage=_normalize_token_usage,
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
                "event": "init_rumination_intro",
                "token_usage": token_usage,
            },
        )
        return SimpleChatResponse(
            code=200,
            message="success",
            data={
                "messages": [{"role": "assistant", "content": reply_text}],
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
                "step_intro": get_step_copy(phase_step, "intro", init_loc),
                "token_usage": token_usage,
            },
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
    _ir = get_effective_simple_root(rec)
    _reports_root = str(Path(_ir) / "reports")
    vi_i, ra_i = _system_prompt_dimension_extras(
        phase_step, report, _reports_root, None, init_loc
    )
    system_prompt = _build_system_prompt(
        phase_step,
        question_bank=question_bank,
        basic_info=basic_info,
        prior_context=prior_context,
        template_override=(override_cfg or {}).get("template"),
        extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
        values_info=vi_i,
        rumination_step_addon=ra_i,
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
            "step_intro": get_step_copy(phase_step, "intro", init_loc),
            "token_usage": token_usage,
        },
    )


class ThreadReopenRequest(BaseModel):
    activation_code: str
    phase: str
    thread_id: str


class RequestConclusionDraftBody(BaseModel):
    """用户主动请求根据当前对话生成待确认结论草案（不走双模型兜底）。"""

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
    try:
        rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=request.activation_code,
            current_user=current_user,
            phase=request.phase,
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
    draft = cmeta.get("draft")
    last_conclusion = cmeta.get("final")
    uc = _count_user_messages(conv_data.get("messages"))

    # 仅有待确认草案（pending）时点「再聊聊」：视为放弃待确认，清 draft，回到主对话（等同 rejected）
    if isinstance(draft, dict):
        summ = (draft.get("summary") or draft.get("ai_summary") or "").strip().replace("\n", " ")
        if len(summ) > 100:
            summ = summ[:99] + "…"
        kws = draft.get("keywords") or []
        kw_s = "、".join(str(k).strip() for k in kws[:8] if str(k).strip())
        feedback = (
            f"{REJECTED_DRAFT_SUPERSESSION_LINE}\n"
            "[再聊聊] 用户折叠结论卡希望继续完善。上一版待确认草案"
        )
        if summ:
            feedback += f" 摘录：{summ}"
        if kw_s:
            feedback += f" 关键词：{kw_s}"
        if len(feedback) > 520:
            feedback = feedback[:517] + "…"
        await conv_manager.update_metadata(
            report["report_id"],
            category,
            {
                **_build_conclusion_meta_update(
                    state=CONCLUSION_STATE_REJECTED,
                    final=last_conclusion if isinstance(last_conclusion, dict) else None,
                    feedback=feedback,
                    thread_completed=False,
                ),
                "conclusion_reject_baseline_user_count": uc,
            },
        )
    elif isinstance(last_conclusion, dict):
        # 已有最终结论后仍「再聊聊」：保留原逻辑（轻量反馈）
        await conv_manager.update_metadata(
            report["report_id"],
            category,
            {
                **_build_conclusion_meta_update(
                    state=CONCLUSION_STATE_REJECTED,
                    final=last_conclusion,
                    feedback="用户选择再聊聊",
                    thread_completed=False,
                ),
                "conclusion_reject_baseline_user_count": uc,
            },
        )
    else:
        await conv_manager.update_metadata(
            report["report_id"],
            category,
            {
                **_build_conclusion_meta_update(
                    state=CONCLUSION_STATE_NONE,
                    final=None,
                    feedback="",
                    thread_completed=False,
                ),
                "conclusion_reject_baseline_user_count": None,
            },
        )
    return SimpleChatResponse(code=200, message="success", data={})


@router.post("/conclusion-draft/request", response_model=SimpleChatResponse)
async def request_conclusion_draft(
    request: RequestConclusionDraftBody,
    current_user: dict = Depends(get_current_user),
):
    """根据当前对话生成待确认结论草案（跳过「是否已完成探索」判定）。

    说明：主对话流中模型仍可在满足条件时通过 STATE_JSON（pending_ready）自动推送结论卡；
    本接口为「确认稿」兜底，不替代自动路径。
    """
    manager = get_activation_manager_for_code(request.activation_code)
    try:
        rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=request.activation_code,
            current_user=current_user,
            phase=request.phase,
            thread_id=request.thread_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("request_conclusion_draft _resolve_report_context failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="解析会话上下文失败，请刷新页面后重试",
        ) from e
    if phase_step == "rumination":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前阶段不支持确认稿")
    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    _assert_step_editable(
        registry=registry,
        report_id=report["report_id"],
        phase_step=phase_step,
        current_user=current_user,
        rec=rec,
    )
    session_id = report["report_id"]
    conv_data = await conv_manager.get_conversation_data(session_id, category)
    meta = conv_data.get("metadata") or {}
    cmeta = _read_conclusion_meta(meta)
    if cmeta.get("thread_completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="本维度对话已确认完成，无需再生成确认稿",
        )
    raw_messages = conv_data.get("messages") or []
    messages = _trim_history_messages_for_llm(raw_messages)
    conv_history = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in messages
    ]
    vip_level = getattr(rec, "vip_level", 1) or 1
    reasoning_llm = _get_reasoning_llm_provider(vip_level=vip_level)
    try:
        result = await asyncio.wait_for(
            check_dimension_complete(
                phase_step,
                conv_history,
                prior_conclusion=None,
                vip_level=vip_level,
                llm_provider=reasoning_llm,
                skip_completion_check=True,
            ),
            timeout=CONCLUSION_DRAFT_HTTP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[request_conclusion_draft] timeout after %ss phase=%s thread=%s",
            CONCLUSION_DRAFT_HTTP_TIMEOUT_SECONDS,
            phase_step,
            logical_session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="生成确认稿超时，请稍后重试",
        ) from None
    if not result:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="暂无法从当前对话生成确认稿，请多聊几句再试",
        )
    draft_clean = sanitize_pending_conclusion_draft(phase_step, dict(result))
    uc = _count_user_messages(raw_messages)
    await conv_manager.update_metadata(
        session_id,
        category,
        {
            **_build_conclusion_meta_update(
                state=CONCLUSION_STATE_PENDING,
                draft=draft_clean,
                final=cmeta.get("final"),
                shown_at=uc,
                thread_completed=False,
            ),
            "conclusion_reject_baseline_user_count": None,
        },
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
                "pending_conclusion": draft_clean,
                "source": "request_conclusion_draft",
            },
        )
    except Exception:
        pass
    return SimpleChatResponse(
        code=200,
        message="success",
        data={"draft": draft_clean},
    )


@router.post("/conclusion-draft/request-stream")
async def request_conclusion_draft_stream(
    request: RequestConclusionDraftBody,
    current_user: dict = Depends(get_current_user),
):
    """
    确认稿：推理模型流式生成结构化结论（与 request相同 prompt/落库逻辑），无整段 asyncio硬超时。
    SSE 事件与主对话流兼容：think_start / think_chunk / think_end / chunk；结束时 draft。
    """
    manager = get_activation_manager_for_code(request.activation_code)
    try:
        rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=request.activation_code,
            current_user=current_user,
            phase=request.phase,
            thread_id=request.thread_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("request_conclusion_draft_stream _resolve_report_context failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="解析会话上下文失败，请刷新页面后重试",
        ) from e
    if phase_step == "rumination":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前阶段不支持确认稿")
    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    _assert_step_editable(
        registry=registry,
        report_id=report["report_id"],
        phase_step=phase_step,
        current_user=current_user,
        rec=rec,
    )
    session_id = report["report_id"]
    conv_data = await conv_manager.get_conversation_data(session_id, category)
    meta = conv_data.get("metadata") or {}
    cmeta = _read_conclusion_meta(meta)
    if cmeta.get("thread_completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="本维度对话已确认完成，无需再生成确认稿",
        )
    raw_messages = conv_data.get("messages") or []
    messages = _trim_history_messages_for_llm(raw_messages)
    conv_history = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in messages
    ]
    gen_messages = build_conclusion_generation_messages(phase_step, conv_history, None)
    if not gen_messages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="暂无法从当前对话生成确认稿，请多聊几句再试",
        )

    vip_level = getattr(rec, "vip_level", 1) or 1
    reasoning_llm = _get_reasoning_llm_provider(vip_level=vip_level)

    async def event_stream() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'started': True}, ensure_ascii=False)}\n\n"
        full_text = ""
        sem = _get_llm_semaphore()
        try:
            stream_coro = reasoning_llm.chat_stream(gen_messages, temperature=0.3)

            async def _consume_stream() -> AsyncIterator[str]:
                nonlocal full_text
                async for piece in stream_coro:
                    if isinstance(piece, dict):
                        t = piece.get("_t")
                        if t == "think_start":
                            yield f"data: {json.dumps({'think_start': True}, ensure_ascii=False)}\n\n"
                        elif t == "think_chunk":
                            tc = piece.get("content") or ""
                            if tc:
                                yield f"data: {json.dumps({'think_chunk': tc}, ensure_ascii=False)}\n\n"
                        elif t == "think_end":
                            te = piece.get("content")
                            yield f"data: {json.dumps({'think_end': te}, ensure_ascii=False)}\n\n"
                        continue
                    if piece:
                        full_text += piece
                        yield f"data: {json.dumps({'chunk': piece}, ensure_ascii=False)}\n\n"

            if sem:
                async with sem:
                    async for line in _consume_stream():
                        yield line
            else:
                async for line in _consume_stream():
                    yield line
        except Exception as e:
            logger.warning("conclusion-draft stream LLM failed: %s", e)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return

        result = finalize_conclusion_from_summary_text(phase_step, full_text.strip(), None)
        if not result:
            yield f"data: {json.dumps({'error': '模型输出无法解析为结论，请重试'}, ensure_ascii=False)}\n\n"
            return
        draft_clean = sanitize_pending_conclusion_draft(phase_step, dict(result))
        uc = _count_user_messages(raw_messages)
        await conv_manager.update_metadata(
            session_id,
            category,
            {
                **_build_conclusion_meta_update(
                    state=CONCLUSION_STATE_PENDING,
                    draft=draft_clean,
                    final=cmeta.get("final"),
                    shown_at=uc,
                    thread_completed=False,
                ),
                "conclusion_reject_baseline_user_count": None,
            },
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
                    "pending_conclusion": draft_clean,
                    "source": "request_conclusion_draft_stream",
                },
            )
        except Exception:
            pass
        yield f"data: {json.dumps({'done': True, 'draft': draft_clean}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/thread/complete", response_model=SimpleChatResponse)
async def mark_thread_complete(
    request: ThreadCompleteRequest,
    current_user: dict = Depends(get_current_user),
):
    """标记某对话为已完成（用户点击「确认没有问题」后调用）"""
    manager = get_activation_manager_for_code(request.activation_code)
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=request.phase,
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
        try:
            merge_dimension_conclusion_record(
                report["report_id"],
                phase_step,
                dimension_conclusion,
                str(root / "reports"),
            )
        except Exception:
            pass
        summary = dimension_conclusion.get("summary") or dimension_conclusion.get("ai_summary", "")
        keywords = dimension_conclusion.get("keywords") or []
        if isinstance(keywords, list):
            kw_for_prior = (
                cap_strengths_keywords_list(keywords)
                if phase_step == "strengths"
                else keywords
            )
            kw_text = "、".join(str(k) for k in kw_for_prior)
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
    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "step_outro": get_step_copy(phase_step, "outro", "zh"),
            "step_outro_en": get_step_copy(phase_step, "outro", "en"),
        },
    )


@router.get("/threads", response_model=SimpleHistoryResponse)
async def list_threads(
    activation_code: str,
    phase: str,
    current_user: dict = Depends(get_current_user),
):
    """
    获取某阶段下的线程列表（后端为数据源，支持跨设备同步）。
    返回 record.json 中 steps[phase].session_ids 对应的线程元信息。
    """
    manager = get_activation_manager_for_code(activation_code)
    phase_step = _require_simple_chat_phase(phase)
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
        threads.append({
            "id": tid,
            "title": f"对话 {idx + 1}",
            "status": "completed" if completed else "in-progress",
            "messages": [],  # 列表不返回消息体，由 /history 按需加载
            "createdAt": ts_ms or int(datetime.now(timezone.utc).timestamp() * 1000),
            "dimensionConclusion": cmeta.get("final"),
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
    phase: str,
    thread_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    获取某个激活码 + 阶段下的全部历史消息
    """
    try:
        manager = get_activation_manager_for_code(activation_code)
        rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=activation_code,
            current_user=current_user,
            phase=phase,
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

        return SimpleHistoryResponse(
            code=200,
            message="success",
            data={
                "messages": history_messages,
                "metadata": {
                    "session_id": logical_session_id,
                    "thread_completed": cmeta.get("thread_completed", False),
                    "dimension_conclusion": cmeta.get("final"),
                    # 待确认草案仅存在 metadata，消息文件里可能没有 conclusion_card 行；供前端 hydrate 弹卡
                    "conclusion_state": cmeta.get("state"),
                    "conclusion_draft": (
                        cmeta.get("draft")
                        if cmeta.get("state") == CONCLUSION_STATE_PENDING
                        and isinstance(cmeta.get("draft"), dict)
                        else None
                    ),
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
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=request.phase,
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
    if request.client_conclusion_ui:
        logger.debug(
            "[message_stream] client_conclusion_ui thread=%s payload=%s",
            logical_session_id,
            request.client_conclusion_ui,
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
        stream_loc = _normalize_client_locale(request.locale)
        reports_root = str(Path(storage_root) / "reports")
        vi_s, ra_s = _system_prompt_dimension_extras(
            phase_step,
            report,
            reports_root,
            request.rumination_filter_step,
            stream_loc,
        )
        system_prompt = _build_system_prompt(
            phase_step,
            question_bank=question_bank,
            basic_info=basic_info,
            prior_context=prior_context,
            template_override=(override_cfg or {}).get("template"),
            extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
            values_info=vi_s,
            rumination_step_addon=ra_s,
        )
        llm_messages = [LLMMessage(role="system", content=system_prompt)]

        # 若有锚点摘要，插入 [此前对话要点] 再拼接最近 N 轮
        anchor = load_anchor_for_phase(session_id, phase_step, storage_root)
        anchor_text = format_anchor_for_prompt(anchor)
        if anchor_text:
            llm_messages.append(LLMMessage(role="assistant", content=f"[此前对话要点]\n{anchor_text}"))

        trimmed = _trim_history_messages_for_llm(history_messages)

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
        user_count = _count_user_messages(conv_data.get("messages"))
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
            _draft_kw = (
                (pending_conclusion or {}).get("keywords")
                if isinstance(pending_conclusion, dict)
                else None
            )
            _draft_kw_list = _draft_kw[:12] if isinstance(_draft_kw, list) else []
            try:
                await _append_note_json(
                    conv_manager,
                    session_id,
                    category,
                    "pending_judge_decision",
                    {
                        "phase": phase_step,
                        "thread_id": logical_session_id,
                        "result_state": pending_state,
                        "timed_out": pending_timed_out,
                        "decision_visible_reply": (pending_msg or "")[:800],
                        "user_input_excerpt": (user_content or "")[:600],
                        "draft_summary_excerpt": str(
                            (pending_conclusion or {}).get("summary")
                            or (pending_conclusion or {}).get("ai_summary")
                            or ""
                        )[:400],
                        "draft_keywords": [str(x) for x in _draft_kw_list if str(x).strip()][
                            :12
                        ],
                    },
                )
            except Exception:
                pass

            if pending_state == "confirmed":
                # 与主对话流一致：pending 判定流结束后进入非流式推理前，通知前端可切换「后台处理中」提示
                yield f"data: {json.dumps({'llm_stream_end': True}, ensure_ascii=False)}\n\n"
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
                    yield f"data: {json.dumps({'conclusion_loading': True}, ensure_ascii=False)}\n\n"
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
                    {
                        **_build_conclusion_meta_update(
                            state=CONCLUSION_STATE_REJECTED,
                            final=cmeta.get("final"),
                            feedback=user_content,
                            shown_at=conclusion_shown_at,
                            thread_completed=False,
                        ),
                        "conclusion_reject_baseline_user_count": user_count,
                    },
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
                pending_conclusion = None
                rejected_feedback = user_content

        # 同步最新 metadata（含 pending→rejected），并按需注入「每 N 轮」轻量 system 提醒
        conv_data = await conv_manager.get_conversation_data(session_id, category)
        meta = conv_data.get("metadata", {})
        cmeta = _read_conclusion_meta(meta)
        user_count = _count_user_messages(conv_data.get("messages"))
        pending_conclusion = cmeta.get("draft")
        rejected_feedback = cmeta.get("feedback") or ""

        if (
            cmeta.get("state") == CONCLUSION_STATE_REJECTED
            and not cmeta.get("thread_completed")
            and not isinstance(pending_conclusion, dict)
            and phase_step != "rumination"
        ):
            baseline = meta.get("conclusion_reject_baseline_user_count")
            if isinstance(baseline, int) and user_count - baseline >= CONCLUSION_REJECT_NUDGE_USER_TURNS:
                if llm_messages and llm_messages[0].role == "system":
                    llm_messages[0] = LLMMessage(
                        role="system",
                        content=llm_messages[0].content + "\n\n" + CONCLUSION_REJECT_SYSTEM_NUDGE,
                    )
                await conv_manager.update_metadata(
                    session_id,
                    category,
                    {"conclusion_reject_baseline_user_count": user_count},
                )

        # 用户否定后：保留轻量反馈上下文（不做关键词规则）
        if rejected_feedback and not pending_conclusion:
            llm_messages.append(
                LLMMessage(
                    role="assistant",
                    content="[对话状态备注·供你理解上下文]\n"
                    + format_rejected_conclusion_injection(rejected_feedback),
                )
            )

        # 仍有待确认草案且本轮将走主对话：system 追加极简状态（判定器判 continue 等情形）
        if (
            isinstance(pending_conclusion, dict)
            and not cmeta.get("thread_completed")
            and llm_messages
            and llm_messages[0].role == "system"
        ):
            addon = build_pending_main_dialogue_system_addon(phase_step, pending_conclusion)
            if addon:
                llm_messages[0] = LLMMessage(
                    role="system",
                    content=llm_messages[0].content + "\n\n" + addon,
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

        # 主对话模型流式输出已结束；后续为解析、落盘、结论卡与埋点，前端可切换「后台处理中」占位提示
        yield f"data: {json.dumps({'llm_stream_end': True}, ensure_ascii=False)}\n\n"

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
            if state_name == "pending_ready" and isinstance(draft, dict):
                # 自动出卡：主模型在可见正文后附带 STATE_JSON pending_ready，经落库后再 SSE 推送 dimension_conclusion
                draft_to_save = sanitize_pending_conclusion_draft(phase_step, dict(draft))
                yield f"data: {json.dumps({'conclusion_loading': True}, ensure_ascii=False)}\n\n"
                await conv_manager.update_metadata(
                    session_id,
                    category,
                    {
                        **_build_conclusion_meta_update(
                            state=CONCLUSION_STATE_PENDING,
                            draft=draft_to_save,
                            final=cmeta.get("final"),
                            shown_at=user_count,
                            thread_completed=False,
                        ),
                        "conclusion_reject_baseline_user_count": None,
                    },
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
                            "pending_conclusion": draft_to_save,
                        },
                    )
                except Exception:
                    pass
                # 与「确认 pending」流一致：推送 dimension_conclusion，否则前端只收到纯文字，必须刷新才能看到卡
                yield (
                    "data: "
                    + json.dumps({"dimension_conclusion": draft_to_save}, ensure_ascii=False)
                    + "\n\n"
                )
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
    phase_step = _require_simple_chat_phase(request.phase)
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

