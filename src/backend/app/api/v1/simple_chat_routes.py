"""
简单模式对话 API

特点：
- 不使用 LangGraph
- 通过一个较长的 system_prompt + 历史消息，分模块（values/strengths/interests）引导用户
- 会话由「激活码」标识，对话历史保存在 data/simple 下
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Literal, Optional, Sequence, Tuple
import asyncio
import json
import logging
import re
import uuid

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
from app.utils.activation_audit import (
    append_activation_audit,
    EVENT_OWNER_DENIED,
    EVENT_OWNER_VERIFIED,
)
from app.utils.sandbox_fork import assert_sandbox_not_expired
from app.utils.conversation_file_manager import ConversationFileManager
from app.utils.id_codec import IDCodec
from app.core.dimension_completion_checker import (
    check_dimension_complete,
)
from app.services.analytics_service import AnalyticsService
from app.utils.report_registry import ReportRegistry, STEP_IDS, STEP_ORDER
from copy import deepcopy

from app.utils.purpose_progress import (
    normalize_progress,
    build_progress_injection,
    apply_progress_update,
    progress_to_experience_value_rows,
)
from app.utils.rumination_progress import (
    MAX_FILTER_STEP,
    clear_neg_gate_triggered_step,
    is_neg_gate_triggered,
    load_rumination_progress,
    mark_neg_gate_triggered,
    max_reached_filter_step,
    merge_rumination_progress_fields,
    save_rumination_progress,
)
from app.utils.rumination_neg_gate import build_zero_results_gate, try_build_neg_gate_response
from app.utils.rumination_table_widgets import build_table_widget_payload
from app.utils.rumination_ops import (
    gen_table,
    filter_strength,
    filter_match,
    extract_dimension_lists_for_rumination_table,
    structure_hypothesis_round1_table,
    is_rumination_hypothesis_pending,
    is_rumination_step3_row_hypothesis_complete,
    value_filter,
    passion_filter,
    reality_filter,
    similar_filter,
    resolve_values_for_step4,
    save_values_snapshot_to_snapshots,
    load_values_snapshot_from_snapshots,
    load_strength_markers,
)
from app.utils.rumination_row_context import (
    format_step3_row_context_block,
    format_step3_confirmed_rows_block,
    summarize_prev_combo_row,
)
from app.utils.rumination_step3_flow import apply_step3_table_trigger
from app.utils.context_refiner import (
    refine_and_save_anchor,
    refine_and_save_rumination_step_anchor,
    format_anchor_for_prompt,
    load_anchor_for_phase,
    load_rumination_step_anchors,
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
    split_visible_reply_and_row_state as _split_visible_reply_and_row_state,
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
        if int(rumination_filter_step) == 3:
            try:
                prog_ex = load_rumination_progress(Path(reports_root), str(rid))
                ft_ex = prog_ex.get("filter_table")
                cur_ex = int(prog_ex.get("filter_row_cursor") or 0)
                if isinstance(ft_ex, list) and ft_ex:
                    # 已确认行摘要（cursor 之前的行）
                    confirmed_block = format_step3_confirmed_rows_block(ft_ex, cur_ex)
                    rumination_step_addon = f"{rumination_step_addon}\n\n{confirmed_block}".strip()
                    # 当前行上下文
                    if 0 <= cur_ex < len(ft_ex):
                        row_ex = ft_ex[cur_ex]
                        if isinstance(row_ex, dict):
                            prev_s = ""
                            if cur_ex > 0:
                                pr = ft_ex[cur_ex - 1]
                                if isinstance(pr, dict):
                                    prev_s = summarize_prev_combo_row(pr)
                            block = format_step3_row_context_block(
                                str(rid),
                                reports_root,
                                row_ex,
                                combo_index_1based=cur_ex + 1,
                                total_combos=len(ft_ex),
                                prev_combo_summary=prev_s,
                            )
                            rumination_step_addon = f"{rumination_step_addon}\n\n{block}".strip()
            except Exception:
                pass
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
                **IDCodec.build_note_container_root(session_id),
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
    → 再退到非 activation_storage_session_id 的候选 → 新建 thread_id。
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
        # session_ids 为空说明该阶段没有任何已注册线程（可能用户已全部删除）。
        # 返回空字符串让调用方自行处理，而非 fallback 到 act_sid——
        # act_sid 指向的对话文件可能残留于磁盘，导致"删光了又恢复"。
        return ""
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
    return f"t_{uuid.uuid4().hex}"


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
    uid = (current_user or {}).get("user_id")
    email = (current_user or {}).get("email")
    if not manager.is_owner(rec, current_user):
        # 审计日志：归属拒绝
        append_activation_audit(
            EVENT_OWNER_DENIED,
            activation_code,
            actor_user_id=uid,
            actor_email=email,
            detail={
                "owner_user_id": rec.owner_user_id,
                "owner_email": rec.owner_email,
                "endpoint": "simple_chat_routes._resolve_activation_for_user",
            },
        )
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
    else:
        # 审计日志：归属校验通过
        append_activation_audit(
            EVENT_OWNER_VERIFIED,
            activation_code,
            actor_user_id=uid,
            actor_email=email,
            detail={"endpoint": "simple_chat_routes._resolve_activation_for_user"},
        )
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
        # 不自动生成新 thread_id：POST 端点应传入显式 thread_id，
        # GET 端点不应触发任何写入。返回空 logical_session_id 让调用方判断。
        pass

    # 进入新阶段前，锁定上一阶段（管理员调试工作区可豁免，支持回退/跳步）
    if not _can_bypass_flow_limits(current_user, rec):
        try:
            registry.lock_previous_step_when_entering(report["report_id"], phase_step)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

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
        "strengths": "优势",
        "interests": "热爱",
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
    activation_session_id: Optional[str] = None  # 仅用于诊断/去歧义，业务以激活码后端记录为准
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
    data = load_basic_info(IDCodec.activation_session_id_from_rec(rec), base)
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
    return load_prior_context(IDCodec.activation_session_id_from_rec(rec), phase, str(root))


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


@router.get("/user-survey-status")
def get_user_survey_status(
    current_user: dict = Depends(get_current_user),
):
    """
    按当前登录用户维度查询 basic_info 是否已填写。

    返回 { completed: bool, survey_data: {...} } 。
    前端登录后可先调此接口决定是否需要跳问卷，不依赖激活码。
    """
    user_id = (current_user or {}).get("user_id") or (current_user or {}).get("email") or ""
    if not user_id:
        return SimpleChatResponse(code=200, message="success", data={"completed": False, "survey_data": {}})
    data = load_basic_info_by_user(user_id)
    completed = bool(data) and any(
        v is not None and v != "" and (not isinstance(v, list) or len(v) > 0)
        for v in (data or {}).values()
    )
    return SimpleChatResponse(code=200, message="success", data={"completed": completed, "survey_data": data or {}})


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
        data = load_basic_info(
            IDCodec.activation_session_id_from_rec(rec),
            str(get_effective_simple_root(rec)),
        )
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
    filter_table: Optional[List[Dict[str, Any]]] = None
    filter_row_cursor: Optional[int] = None
    hypothesis_round: Optional[int] = None
    filter_early_terminated: Optional[bool] = None
    filter_terminate_reason: Optional[str] = None
    step3_trigger: Optional[str] = None


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
    # 为 True 时跳过「否定/标记」闸门（由 rumination-neg-resolve 在暂存提交后调用）
    neg_force_commit: bool = False


class RuminationNegResolveRequest(BaseModel):
    """闸门：继续推进 / 开始深入讨论 / 结束讨论并推进 / 暂时关闭弹窗。"""

    model_config = ConfigDict(extra="ignore")

    activation_code: str
    thread_id: str = ""
    action: Literal["continue", "deep_start", "deep_end", "dismiss"]


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
    # step3 逐行编辑：前端发来的 filter_table 中，未解锁行的业务字段已被 redact 清空。
    # 直接覆盖会丢失后端已有的热爱/优势等原始数据。需要智能合并。
    save_table = request.filter_table
    if (
        int(request.filter_step or 0) == 3
        and isinstance(save_table, list)
        and save_table
    ):
        existing = load_rumination_progress(reports_root, report_id).get("filter_table")
        if isinstance(existing, list) and existing:
            save_table = _merge_step3_filter_table(save_table, existing)
    progress = save_rumination_progress(
        reports_root,
        report_id,
        main_section=request.main_section,
        review_sub_index=request.review_sub_index,
        filter_step=request.filter_step,
        filter_table=save_table,
        filter_row_cursor=request.filter_row_cursor,
        hypothesis_round=request.hypothesis_round,
        filter_early_terminated=request.filter_early_terminated,
        filter_terminate_reason=request.filter_terminate_reason,
    )
    # step3 表格触发（none / hypothesis_commit）：处理副作用并推进 cursor
    step3_side_effect = None
    trigger = request.step3_trigger
    if trigger and int(request.filter_step or 0) == 3:
        merged_table = progress.get("filter_table")
        if isinstance(merged_table, list):
            side_effect, new_cursor = apply_step3_table_trigger(
                existing_prog=progress,
                merged_table=merged_table,
                trigger=trigger,
            )
            if new_cursor is not None:
                progress = save_rumination_progress(
                    reports_root, report_id, filter_row_cursor=new_cursor
                )
            if side_effect:
                step3_side_effect = side_effect
    return SimpleChatResponse(code=200, message="success", data={"progress": progress, "step3_side_effect": step3_side_effect})


def _rumination_snapshots_copy(progress: Dict[str, Any]) -> Dict[str, Any]:
    s = progress.get("filter_step_snapshots") or {}
    return deepcopy(s) if isinstance(s, dict) else {}


def _table_widget_payload(
    step: int,
    rows: List[dict],
    values_list: List[str],
    *,
    progress: Optional[Dict[str, Any]] = None,
    values_source: str = "",
) -> Optional[dict]:
    """构建 table_widget；子步 3 注入 filter_row_cursor 以做行脱敏。"""
    progress = progress or {}
    kwargs: Dict[str, Any] = {}
    if step == 3:
        kwargs["hypothesis_row_cursor"] = int(progress.get("filter_row_cursor") or 0)
    return build_table_widget_payload(
        step, rows, values_list, values_source=values_source, **kwargs
    )


def _try_rumination_step3_row_unlock(
    reports_root: Path,
    report_id: str,
    row_state: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """解析 ROW_STATE_JSON；校验当前行假设已填后 filter_row_cursor += 1。"""
    if str(row_state.get("state") or "").strip().lower() != "confirmed":
        return None
    try:
        idx = int(row_state["row"])
    except (KeyError, TypeError, ValueError):
        return None
    prog = load_rumination_progress(reports_root, report_id)
    cur = int(prog.get("filter_row_cursor") or 0)
    if idx != cur:
        logger.info(
            "[rumination] step3 unlock skipped: row index %s != cursor %s", idx, cur
        )
        return None
    ft = prog.get("filter_table")
    if not isinstance(ft, list) or idx < 0 or idx >= len(ft):
        return None
    row = ft[idx]
    if not isinstance(row, dict):
        return None
    hyp = str(row.get("用户确认的假设") or "").strip()
    if not is_rumination_step3_row_hypothesis_complete(hyp):
        logger.info("[rumination] step3 unlock skipped: row %s hypothesis incomplete", idx)
        return None
    return save_rumination_progress(
        reports_root,
        report_id,
        filter_row_cursor=cur + 1,
    )


def _try_rumination_step3_auto_unlock(
    reports_root: Path,
    report_id: str,
) -> Optional[Dict[str, Any]]:
    """兜底自动解锁：当 AI 未输出 ROW_STATE_JSON 但当前行假设已完整时，自动推进 cursor。

    在每次 step3 AI 回复结束后调用。检查当前 cursor 行的假设是否完整，
    若完整且 cursor 不是最后一行，则 cursor+1。
    """
    prog = load_rumination_progress(reports_root, report_id)
    cur = int(prog.get("filter_row_cursor") or 0)
    ft = prog.get("filter_table")
    if not isinstance(ft, list) or cur < 0 or cur >= len(ft):
        return None
    row = ft[cur]
    if not isinstance(row, dict):
        return None
    hyp = str(row.get("用户确认的假设") or "").strip()
    if not is_rumination_step3_row_hypothesis_complete(hyp):
        return None
    logger.info("[rumination] step3 auto-unlock (fallback): row %s hypothesis complete, advancing cursor", cur)
    return save_rumination_progress(
        reports_root,
        report_id,
        filter_row_cursor=cur + 1,
    )


def _merge_step3_filter_table(
    incoming: list,
    existing: list,
) -> list:
    """合并 step3 前端发来的表格与后端已有数据。

    前端 redact 会清空未解锁行的业务字段（热爱、优势等）。
    直接覆盖会丢失后端已有的原始数据。此函数对每个字段做智能合并：
    - 若前端传来的值为非空字符串 → 采用前端值（用户确实编辑了）
    - 若前端传来的值为空/None → 保留后端原有值（未被 redact 或用户清空）
    """
    out: list = []
    for i, row in enumerate(incoming):
        if not isinstance(row, dict):
            out.append(row)
            continue
        ex = existing[i] if i < len(existing) and isinstance(existing[i], dict) else {}
        merged = dict(row)
        for k, v in merged.items():
            # 非空字符串保留前端值；空值尝试从后端回填
            sv = str(v).strip() if v is not None else ""
            if not sv and k in ex:
                ev = ex[k]
                if ev is not None and str(ev).strip():
                    merged[k] = ev
        # 确保后端有但前端没传的字段也保留
        for k, v in ex.items():
            if k not in merged and v is not None:
                merged[k] = v
        out.append(merged)
    # 后端行数更多时追加
    if len(existing) > len(incoming):
        for i in range(len(incoming), len(existing)):
            out.append(existing[i])
    return out


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

    价值观关键词优先从 step 4 快照读取，保证与下拉选项一致；
    无快照时实时解析并返回 source tag。

    Returns:
        tuple[rec, reports_root, report_id, progress, values_list, values_source]
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
    # 优先使用快照中的价值观关键词（保证与下拉选项一致）
    snapshots = progress.get("filter_step_snapshots") or {}
    values_list, values_source = resolve_values_for_step4(
        str(reports_root), report_id, record_obj, snapshots
    )
    return rec, reports_root, report_id, progress, values_list, values_source


@router.get("/rumination-step-opening", response_model=SimpleChatResponse)
def rumination_step_opening(
    activation_code: str,
    filter_step: int = 1,
    current_user: dict = Depends(get_current_user),
):
    """子步引导：fixed 时返回完整文案（前端模拟流式）；llm 时 text 为 null，走流式接口。"""
    try:
        _rec, _rp, _rid, progress, values_list, values_source = _rumination_opening_load_bundle(
            activation_code, current_user
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("rumination-step-opening load failed: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    step = max(1, min(MAX_FILTER_STEP, int(filter_step)))
    ctx = build_opening_context(filter_step=step, progress=progress, values_list=values_list, values_source=values_source)
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
        rec, _reports_root, _report_id, progress, values_list, values_source = _rumination_opening_load_bundle(
            request.activation_code, current_user
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    ctx = build_opening_context(filter_step=step, progress=progress, values_list=values_list, values_source=values_source)
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

    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    registry.bind_session(report["report_id"], phase_step, logical_session_id)

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
                        **IDCodec.build_message_ids(
                            thread_id=logical_session_id,
                            activation_session_id=rec.session_id,
                        ),
                        "step_id": phase_step,
                        "filter_step": step,
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
    """已废弃：子步 3 改为逐行对话探索，不再在表格内重新生成两条假设。"""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="子步 3 已改为逐行对话探索，请使用右侧对话讨论假设，不再支持表格内重新生成。",
    )


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
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], int]:
    """直达第 7 步：清理中间快照、标记 skipped、写入 7 的 initial、更新 progress。"""
    _rumination_clear_snapshots_from_step(snapshots, clear_snapshots_from)
    # 标记被短链跳过的中间子步为 skipped，前端据此灰显并禁止操作
    for skip_step in range(clear_snapshots_from, 7):
        snapshots[str(skip_step)] = {"skipped": True}
    wrows = _rumination_step7_rows_for_widget(step7_rows)
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

        # 被短链跳过的子步禁止提交
        step_snap = progress0.get("filter_step_snapshots", {}).get(sk, {})
        if step_snap.get("skipped"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该步骤已被跳过，不可提交",
            )

        pending0 = progress0.get("pending_table_submit")
        neg0_early = progress0.get("rumination_neg_state") or {}
        neg0_active = neg0_early.get("status") in ("awaiting_choice", "exploring")
        if isinstance(pending0, dict) and not request.neg_force_commit and neg0_active:
            if int(pending0.get("step") or 0) == step and table_data is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请先处理表格上方的跟进选项后再确认",
                )

        neg0 = progress0.get("rumination_neg_state") or {}
        if (
            neg0.get("status") == "exploring"
            and int(neg0.get("step") or 0) == step
            and table_data is not None
            and not request.neg_force_commit
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请先点击「结束讨论」后再确认表格",
            )

        if (
            table_data is not None
            and step in (2, 3, 5, 6)
            and not request.neg_force_commit
            and ent.get("submitted") is None
            and not is_neg_gate_triggered(progress0, step)
        ):
            vip_gate = getattr(rec, "vip_level", 1) or 1
            llm_gate = _get_dialogue_llm_provider(vip_level=vip_gate)
            gate_pkg = await try_build_neg_gate_response(
                step=step,
                table_data=table_data,
                llm=llm_gate,
                selected_row_ids=request.selected_row_ids,
            )
            if gate_pkg:
                # 标记本子步闸门已触发，避免后续重复弹出
                mark_neg_gate_triggered(reports_root, report_id, step)
                merge_rumination_progress_fields(
                    reports_root,
                    report_id,
                    {
                        "pending_table_submit": gate_pkg["pending"],
                        "rumination_neg_state": gate_pkg["neg_state"],
                        "filter_table": table_data,
                    },
                )
                progress = load_rumination_progress(reports_root, report_id)
                snaps_gate = progress.get("filter_step_snapshots") or {}
                return SimpleChatResponse(
                    code=200,
                    message="success",
                    data={
                        "progress": progress,
                        "next_step": step,
                        "max_reached_filter_step": max_reached_filter_step(snaps_gate),
                        "next_action": "rumination_neg_confirm",
                        "neg_confirm": gate_pkg["confirm"],
                    },
                )

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

        # ── 后台异步生成当前子步的 anchor 摘要（供后续子步使用）──
        try:
            rum_cat = category  # rumination__{thread_id}
            asyncio.create_task(
                refine_and_save_rumination_step_anchor(
                    report_id, step, rum_cat, vip_level=getattr(rec, "vip_level", 1) or 1
                )
            )
        except Exception as e:
            logger.warning("rumination_submit: anchor task spawn failed: %s", e)

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

        # step 4 价值观关键词优先从快照读取，保证下拉选项与右侧对话一致
        values_list, values_source = resolve_values_for_step4(
            str(reports_root), report_id, record_obj, snapshots
        )
        # 若快照尚不存在（首次进入 step 4 前景），使用全量解析结果
        if not values_list:
            _v, strengths_list, interests_list, _purpose, _sources = extract_dimension_lists_for_rumination_table(
                str(reports_root), report_id, record_obj
            )
            values_list = _v
            values_source = _sources.get("values", "none")
        else:
            # 快照已有 values，仍需 strengths/interests 用于后续步骤
            _, strengths_list, interests_list, _purpose, _sources = extract_dimension_lists_for_rumination_table(
                str(reports_root), report_id, record_obj
            )
        values_hint = "、".join(values_list[:8]) if values_list else ""
        passions = interests_list if interests_list else ["热爱1", "热爱2"]
        strengths_for_gen = strengths_list if strengths_list else ["优势1", "优势2"]
        strength_markers = load_strength_markers(str(reports_root), report_id)

        next_table = None
        next_step_val = step
        rumination_submit_next_action: Optional[str] = None
        closing_summary_for_epilogue = ""
        rumination_finalize_via_short_path = False

        if step == 1 and table_data:
            filtered = filter_strength(table_data)
            if not filtered:
                ent1 = snapshots.setdefault("1", {})
                initial1 = ent1.get("initial")
                if not initial1:
                    initial1 = gen_table(strengths_for_gen, passions, strength_markers)
                    ent1["initial"] = deepcopy(initial1)
                rows1 = deepcopy(initial1)
                ent1["submitted"] = None
                snapshots["1"] = ent1
                _rumination_clear_snapshots_from_step(snapshots, 2)
                save_rumination_progress(
                    reports_root,
                    report_id,
                    main_section="filter",
                    filter_step=1,
                    filter_table=rows1,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                gate_pkg = build_zero_results_gate(
                    step=1,
                    initial_rows=rows1,
                    kind="zero_strength",
                )
                merge_rumination_progress_fields(
                    reports_root,
                    report_id,
                    {
                        "pending_table_submit": gate_pkg["pending"],
                        "rumination_neg_state": gate_pkg["neg_state"],
                        "filter_table": rows1,
                    },
                )
                progress = load_rumination_progress(reports_root, report_id)
                snaps_gate = progress.get("filter_step_snapshots") or {}
                return SimpleChatResponse(
                    code=200,
                    message="success",
                    data={
                        "progress": progress,
                        "next_step": 1,
                        "max_reached_filter_step": max_reached_filter_step(snaps_gate),
                        "next_action": "rumination_neg_confirm",
                        "neg_confirm": gate_pkg["confirm"],
                    },
                )
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
                save_rumination_progress(
                    reports_root,
                    report_id,
                    main_section="filter",
                    filter_step=2,
                    filter_table=rows2,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                gate_pkg = build_zero_results_gate(
                    step=2,
                    initial_rows=rows2,
                    kind="zero_match",
                )
                merge_rumination_progress_fields(
                    reports_root,
                    report_id,
                    {
                        "pending_table_submit": gate_pkg["pending"],
                        "rumination_neg_state": gate_pkg["neg_state"],
                        "filter_table": rows2,
                    },
                )
                progress = load_rumination_progress(reports_root, report_id)
                snaps_gate = progress.get("filter_step_snapshots") or {}
                return SimpleChatResponse(
                    code=200,
                    message="success",
                    data={
                        "progress": progress,
                        "next_step": 2,
                        "max_reached_filter_step": max_reached_filter_step(snaps_gate),
                        "next_action": "rumination_neg_confirm",
                        "neg_confirm": gate_pkg["confirm"],
                    },
                )
            else:
                s3 = snapshots.setdefault("3", {})
                if s3.get("initial") is None:
                    s3["initial"] = deepcopy(step3_rows)
                progress = save_rumination_progress(
                    reports_root,
                    report_id,
                    filter_step=3,
                    filter_table=step3_rows,
                    filter_row_cursor=0,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                next_table = _table_widget_payload(3, step3_rows, values_list, progress=progress)
                next_step_val = 3

        elif step == 3 and table_data:
            # 单轮假设 → 价值观入口；须完成逐行对话（cursor）且每行显式「无」或自填
            progress3 = load_rumination_progress(reports_root, report_id)
            cur3 = int(progress3.get("filter_row_cursor") or 0)
            n3 = len(table_data)
            if cur3 < n3:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请先在右侧对话中完成本步骤全部行的确认，再提交表格。",
                )
            finalized = []
            for r in table_data:
                row = dict(r)
                hyp = str(row.get("用户确认的假设") or "").strip()
                if not is_rumination_step3_row_hypothesis_complete(hyp):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail='存在未完成行：请在「假设」列选择「无」或填写具体内容。',
                    )
                finalized.append(row)
            step4_rows = value_filter(finalized, values_list)
            if not step4_rows:
                # 价值观筛选后 0 条：弹窗兜底
                ent3v = snapshots.setdefault("3", {})
                initial3v = ent3v.get("initial")
                if not initial3v:
                    initial3v = deepcopy(finalized)
                    ent3v["initial"] = deepcopy(initial3v)
                rows3v = deepcopy(initial3v)
                ent3v["submitted"] = None
                snapshots["3"] = ent3v
                _rumination_clear_snapshots_from_step(snapshots, 4)
                save_rumination_progress(
                    reports_root,
                    report_id,
                    main_section="filter",
                    filter_step=3,
                    filter_table=rows3v,
                    filter_step_snapshots=snapshots,
                    filter_early_terminated=False,
                    filter_terminate_reason=None,
                )
                gate_pkg = build_zero_results_gate(
                    step=3,
                    initial_rows=rows3v,
                    kind="zero_value",
                )
                merge_rumination_progress_fields(
                    reports_root,
                    report_id,
                    {
                        "pending_table_submit": gate_pkg["pending"],
                        "rumination_neg_state": gate_pkg["neg_state"],
                        "filter_table": rows3v,
                    },
                )
                progress = load_rumination_progress(reports_root, report_id)
                snaps_gate = progress.get("filter_step_snapshots") or {}
                return SimpleChatResponse(
                    code=200,
                    message="success",
                    data={
                        "progress": progress,
                        "next_step": 3,
                        "max_reached_filter_step": max_reached_filter_step(snaps_gate),
                        "next_action": "rumination_neg_confirm",
                        "neg_confirm": gate_pkg["confirm"],
                    },
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
                next_table = _table_widget_payload(
                    4,
                    step4_rows,
                    values_list,
                    progress=load_rumination_progress(reports_root, report_id),
                    values_source=values_source,
                )
                next_step_val = 4
                s4 = snapshots.setdefault("4", {})
                if s4.get("initial") is None:
                    s4["initial"] = deepcopy(step4_rows)
                # 快照价值观关键词 + source，保证下拉与对话一致
                snapshots = save_values_snapshot_to_snapshots(
                    snapshots, values_list, values_source, step=4
                )
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
                    clear_snapshots_from=6,
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
                    clear_snapshots_from=6,
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
                    clear_snapshots_from=7,
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
                    activation_session_id=getattr(_rec_e, "session_id", None),
                    via_short_path=rumination_finalize_via_short_path,
                    selected_summary=closing_summary_for_epilogue,
                    normalize_token_usage=_normalize_token_usage,
                )
            except Exception as e:
                logger.warning("rumination closing epilogue skipped: %s", e)

        merge_rumination_progress_fields(
            reports_root,
            report_id,
            {"pending_table_submit": None, "rumination_neg_state": None},
        )
        progress = load_rumination_progress(reports_root, report_id)
        snaps = progress.get("filter_step_snapshots") or {}
        data: dict = {
            "progress": progress,
            "next_step": next_step_val,
            "max_reached_filter_step": max_reached_filter_step(snaps),
        }
        if next_table:
            data["next_table_widget"] = next_table
        if rumination_submit_next_action:
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


@router.post("/rumination-neg-resolve", response_model=SimpleChatResponse)
async def rumination_neg_resolve(
    request: RuminationNegResolveRequest,
    current_user: dict = Depends(get_current_user),
):
    """闸门后续：继续推进 / 开始深入讨论 / 结束讨论并回到表格。"""
    try:
        manager = get_activation_manager_for_code(request.activation_code)
        rec = _resolve_activation_for_user(manager, request.activation_code, current_user)
        if rec.status == ActivationStatus.EXPIRED and not _skip_expired_for_debug(rec, current_user):
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
        neg = progress.get("rumination_neg_state") or {}
        pending = progress.get("pending_table_submit")

        if request.action == "dismiss":
            """用户点击「我再看看」：关闭闸门弹窗，清除 pending 和 triggered 标记，下次确认重新检测。"""
            if not isinstance(neg, dict) or neg.get("status") != "awaiting_choice":
                raise HTTPException(status_code=400, detail="当前没有待确认的闸门弹窗")
            gate_step = int(neg.get("step") or progress.get("filter_step") or 0)
            merge_rumination_progress_fields(
                reports_root,
                report_id,
                {"rumination_neg_state": None, "pending_table_submit": None},
            )
            if gate_step >= 1:
                clear_neg_gate_triggered_step(reports_root, report_id, gate_step)
            progress2 = load_rumination_progress(reports_root, report_id)
            return SimpleChatResponse(
                code=200,
                message="success",
                data={
                    "progress": progress2,
                    "next_action": "rumination_neg_dismissed",
                },
            )

        if request.action == "deep_start":
            if not isinstance(pending, dict) or pending.get("table_data") is None:
                raise HTTPException(status_code=400, detail="没有待处理的表格提交，请先确认表格")
            if not isinstance(neg, dict) or neg.get("status") != "awaiting_choice":
                raise HTTPException(
                    status_code=400, detail="当前没有待处理的表格跟进项，请重新确认表格",
                )
            neg2 = {**neg, "status": "exploring"}
            merge_rumination_progress_fields(
                reports_root,
                report_id,
                {"rumination_neg_state": neg2},
            )
            progress2 = load_rumination_progress(reports_root, report_id)
            return SimpleChatResponse(
                code=200,
                message="success",
                data={
                    "progress": progress2,
                    "next_action": "rumination_neg_deep_started",
                    "opening_zh": str(neg.get("opening_zh") or ""),
                },
            )

        if request.action == "deep_end":
            if not isinstance(neg, dict) or neg.get("status") != "exploring":
                raise HTTPException(status_code=400, detail="当前不在深入讨论状态")
            gate_step = int(neg.get("step") or progress.get("filter_step") or 0)
            # 结束讨论后保留 pending 表格数据到 filter_table，防止数据丢失
            update_fields: Dict[str, Any] = {
                "pending_table_submit": None,
                "rumination_neg_state": None,
            }
            if isinstance(pending, dict) and isinstance(pending.get("table_data"), list):
                update_fields["filter_table"] = pending["table_data"]
            if gate_step >= 1:
                update_fields["filter_step"] = gate_step
            merge_rumination_progress_fields(
                reports_root,
                report_id,
                update_fields,
            )
            progress2 = load_rumination_progress(reports_root, report_id)
            snaps2 = progress2.get("filter_step_snapshots") or {}
            return SimpleChatResponse(
                code=200,
                message="success",
                data={
                    "progress": progress2,
                    "next_step": gate_step or int(progress2.get("filter_step") or 1),
                    "max_reached_filter_step": max_reached_filter_step(snaps2),
                    "next_action": "rumination_neg_deep_ended",
                    "opening_zh": "这段讨论先收在这里。你可以先回到左侧表格修改答案，改完再点确认继续。",
                },
            )

        if request.action == "continue":
            # zero_results 弹窗不能 continue（相同数据会循环），按 dismiss 处理
            neg_kind = str(neg.get("kind") or "")
            if neg_kind.startswith("zero_"):
                gate_step = int(neg.get("step") or progress.get("filter_step") or 0)
                merge_rumination_progress_fields(
                    reports_root,
                    report_id,
                    {"rumination_neg_state": None, "pending_table_submit": None},
                )
                if gate_step >= 1:
                    clear_neg_gate_triggered_step(reports_root, report_id, gate_step)
                progress2 = load_rumination_progress(reports_root, report_id)
                return SimpleChatResponse(
                    code=200,
                    message="success",
                    data={"progress": progress2, "next_action": "rumination_neg_dismissed"},
                )
            fallback_table = progress.get("filter_table")
            if (
                (not isinstance(pending, dict) or pending.get("table_data") is None)
                and isinstance(neg, dict)
                and neg.get("status") == "exploring"
                and isinstance(fallback_table, list)
            ):
                pending = {
                    "step": int(neg.get("step") or progress.get("filter_step") or 1),
                    "table_data": fallback_table,
                }
            if not isinstance(pending, dict) or pending.get("table_data") is None:
                raise HTTPException(status_code=400, detail="没有待提交的表格数据，请重新在左侧确认表格")
            sub = RuminationTableSubmitRequest(
                activation_code=request.activation_code,
                thread_id=request.thread_id,
                step=int(pending.get("step") or 1),
                table_data=pending.get("table_data"),
                selected_row_ids=pending.get("selected_row_ids"),
                neg_force_commit=True,
            )
            return await rumination_table_submit(sub, current_user)

        raise HTTPException(status_code=400, detail="无效操作")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("rumination-neg-resolve failed: %s", e)
        raise HTTPException(status_code=500, detail="处理失败，请稍后重试") from e


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

    step = max(1, min(MAX_FILTER_STEP, int(step or 1)))
    snapshots = _rumination_snapshots_copy(progress)

    # step 4 价值观关键词优先从快照读取（保证下拉与对话一致）
    values_list, values_source = resolve_values_for_step4(
        str(reports_root), report_id, record_obj, snapshots
    )
    # 其余维度仍需全量解析（step 1 需 strengths/interests 生成行）
    _v_full, strengths_list, interests_list, _purpose, _sources_full = extract_dimension_lists_for_rumination_table(
        str(reports_root), report_id, record_obj
    )
    passions = interests_list if interests_list else ["热爱1", "热爱2"]
    strengths_list = strengths_list if strengths_list else ["优势1", "优势2"]
    strength_markers = load_strength_markers(str(reports_root), report_id)

    sk = str(step)

    def _persist(rows: List[dict], snap: Dict[str, Any]) -> Dict[str, Any]:
        kw: Dict[str, Any] = dict(
            filter_step_snapshots=snap,
        )
        # 首次拉取第 1 步表时同步进入筛选段，否则前端仅靠 progress 不会请求 get-table
        if step == 1 and (progress.get("main_section") or "opening") in (
            "opening",
            "review",
        ):
            kw["main_section"] = "filter"
            kw["filter_early_terminated"] = False
            kw["filter_step"] = step
            kw["filter_table"] = rows
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
        # 从本步起之后整段作废：删除后续子步快照
        for d in range(step + 1, MAX_FILTER_STEP + 1):
            snapshots.pop(str(d), None)

        # 统一逻辑：所有 step（1-7）恢复 initial 快照，清除 submitted
        rows = deepcopy(initial)
        ent = {**ent, "submitted": None}
        snapshots[sk] = ent
        hr = 1 if step <= 3 else 2
        save_rumination_progress(
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
        merge_rumination_progress_fields(
            reports_root,
            report_id,
            {"pending_table_submit": None, "rumination_neg_state": None},
        )
        clear_neg_gate_triggered_step(reports_root, report_id, step)
        try:
            rum_step = report.get("steps", {}).get("rumination") or {}
            rum_tid = (rum_step.get("selected_session_id") or "").strip()
            if rum_tid:
                conv_mgr = ConversationFileManager(base_dir=str(root / "reports"))
                rum_cat = f"rumination__{rum_tid}"
                await conv_mgr.delete_messages_from_filter_step(report_id, rum_cat, step)
        except Exception as e:
            logger.warning("[rumination] reset_initial: failed to clear messages: %s", e)
        prog = load_rumination_progress(reports_root, report_id)
        if step == 7:
            rows = _rumination_step7_rows_for_widget(rows)
        payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
        return _rumination_get_table_response(prog, payload)

    ent_sub = snapshots.get(sk) or {}
    if ent_sub.get("submitted") is not None:
        rows = deepcopy(ent_sub["submitted"])
        if step == 7:
            rows = _rumination_step7_rows_for_widget(rows)
        prog = _persist(rows, snapshots)
        payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
        return _rumination_get_table_response(prog, payload)

    if step == 1:
        rows = gen_table(strengths_list, passions, strength_markers)
        ent = snapshots.setdefault(sk, {})
        if ent.get("initial") is None:
            ent["initial"] = deepcopy(rows)
            snapshots[sk] = ent
        prog = _persist(rows, snapshots)
        payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
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
        payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
        return _rumination_get_table_response(prog, payload)

    # ── step 3-7: 先查快照，无快照则从前一步 submitted 生成 ──
    # step3 特殊处理：逐行实时编辑模式，filter_table 才是最新的
    if step == 3:
        ft_live = progress.get("filter_table")
        if isinstance(ft_live, list) and ft_live:
            rows = deepcopy(ft_live)
            # 自愈：从 initial 快照补全被前端 redact 清空的原始字段（热爱/优势/匹配性）
            initial_rows = (snapshots.get(sk) or {}).get("initial")
            if isinstance(initial_rows, list) and initial_rows:
                rows = _merge_step3_filter_table(rows, initial_rows)
            prog = _persist(rows, snapshots)
            payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
            return _rumination_get_table_response(prog, payload)

    ent_any = snapshots.get(sk) or {}
    for key in ("submitted", "initial"):
        r0 = ent_any.get(key)
        if r0 is not None:
            rows = deepcopy(r0)
            if step == 7:
                rows = _rumination_step7_rows_for_widget(rows)
            prog = _persist(rows, snapshots)
            payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
            return _rumination_get_table_response(prog, payload)

    # ── neg_gate 进行中：使用 pending_table_submit 的数据作为表格（不重新生成）──
    neg = progress.get("rumination_neg_state") or {}
    pending = progress.get("pending_table_submit")
    if (
        neg.get("status") in ("awaiting_choice", "exploring")
        and isinstance(pending, dict)
        and int(pending.get("step") or 0) == step
        and isinstance(pending.get("table_data"), list)
    ):
        rows = deepcopy(pending["table_data"])
        if step == 7:
            rows = _rumination_step7_rows_for_widget(rows)
        # 保存为 initial 快照（下次不再走此分支），但不写 submitted
        ent_any["initial"] = deepcopy(pending["table_data"])
        snapshots[sk] = ent_any
        save_rumination_progress(
            reports_root, report_id,
            filter_step=step, filter_step_snapshots=snapshots,
        )
        prog = load_rumination_progress(reports_root, report_id)
        payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
        return _rumination_get_table_response(prog, payload)

    # 无快照但 filter_table 存在且 filter_step 指向目标步骤：直接使用（deep_end 后 / 覆盖恢复的兜底）
    # 仅当 filter_step == step 时生效，避免用上一步的 filter_table 错误填充后续步骤
    current_filter_step = progress.get("filter_step") or 0
    if current_filter_step == step and isinstance(progress.get("filter_table"), list):
        rows = deepcopy(progress["filter_table"])
        if step == 7:
            rows = _rumination_step7_rows_for_widget(rows)
        ent_any["initial"] = deepcopy(progress["filter_table"])
        snapshots[sk] = ent_any
        save_rumination_progress(
            reports_root, report_id,
            filter_step=step, filter_step_snapshots=snapshots,
        )
        prog = load_rumination_progress(reports_root, report_id)
        payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
        return _rumination_get_table_response(prog, payload)

    # 无快照：从前一步 submitted 生成
    prev_sk = str(step - 1)
    prev_submitted = (snapshots.get(prev_sk) or {}).get("submitted")
    if prev_submitted is None:
        return _rumination_get_table_response(progress, None)

    rows = None
    if step == 3:
        rows = structure_hypothesis_round1_table(prev_submitted)
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
        # step 4 首次生成时快照价值观关键词 + source
        if step == 4:
            snapshots = save_values_snapshot_to_snapshots(
                snapshots, values_list, values_source, step=4
            )
        snapshots[sk] = ent
    prog = _persist(rows, snapshots)
    payload = _table_widget_payload(step, rows, values_list, progress=prog, values_source=values_source)
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
    rumination_neg_injection: str = "",
    purpose_progress_injection: str = "",
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
    inj = (rumination_neg_injection or "").strip()
    if inj:
        base_prompt = f"{base_prompt}\n{inj}"
    # 使命阶段进度注入
    if (phase or "").strip().lower() == "purpose" and (purpose_progress_injection or "").strip():
        base_prompt = f"{base_prompt}\n\n{purpose_progress_injection.strip()}"
    # rumination 阶段不使用结论卡 pending 协议：仅保留自然对话与表格流程。
    if (phase or "").strip().lower() == "rumination":
        return base_prompt

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

    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    registry.bind_session(report["report_id"], phase_step, logical_session_id)

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

    # rumination 不走 question_bank；其余阶段沿用线程级固定题库。
    if phase_step == "rumination":
        question_bank = ""
    else:
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
    # 使命阶段：加载 purpose_progress 并构建注入块
    purpose_prog_injection = ""
    if phase_step == "purpose":
        try:
            conv_data = await conv_manager.get_conversation_data(session_id, category)
            meta = conv_data.get("metadata") or {}
            prog = normalize_progress(meta.get("purpose_progress"))
            purpose_prog_injection = build_progress_injection(prog)
        except Exception:
            purpose_prog_injection = ""
    system_prompt = _build_system_prompt(
        phase_step,
        question_bank=question_bank,
        basic_info=basic_info,
        prior_context=prior_context,
        template_override=(override_cfg or {}).get("template"),
        extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
        values_info=vi,
        rumination_step_addon=ra,
        rumination_neg_injection="",
        purpose_progress_injection=purpose_prog_injection,
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
        if phase_step != "rumination":
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
            **IDCodec.build_message_ids(
                thread_id=logical_session_id,
                activation_session_id=rec.session_id,
            ),
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
            **IDCodec.build_message_ids(
                thread_id=logical_session_id,
                activation_session_id=rec.session_id,
            ),
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
            "activation": IDCodec.build_activation_client_view(rec, logical_session_id),
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
    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    registry.bind_session(report["report_id"], phase_step, logical_session_id)
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
                "activation": IDCodec.build_activation_client_view(rec, logical_session_id),
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
                **IDCodec.build_message_ids(
                    thread_id=logical_session_id,
                    activation_session_id=rec.session_id,
                ),
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
                "activation": IDCodec.build_activation_client_view(rec, logical_session_id),
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
    # 使命阶段：加载 purpose_progress 并构建注入块
    purpose_prog_injection_i = ""
    if phase_step == "purpose":
        try:
            conv_data_i = await conv_manager.get_conversation_data(session_id, category)
            meta_i = conv_data_i.get("metadata") or {}
            prog_i = normalize_progress(meta_i.get("purpose_progress"))
            purpose_prog_injection_i = build_progress_injection(prog_i)
        except Exception:
            purpose_prog_injection_i = ""
    system_prompt = _build_system_prompt(
        phase_step,
        question_bank=question_bank,
        basic_info=basic_info,
        prior_context=prior_context,
        template_override=(override_cfg or {}).get("template"),
        extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
        values_info=vi_i,
        rumination_step_addon=ra_i,
        rumination_neg_injection="",
        purpose_progress_injection=purpose_prog_injection_i,
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
            **IDCodec.build_message_ids(
                thread_id=logical_session_id,
                activation_session_id=rec.session_id,
            ),
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
            "activation": IDCodec.build_activation_client_view(rec, logical_session_id),
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
    registry.bind_session(report["report_id"], phase_step, logical_session_id)
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
        feedback = "用户选择再聊聊，希望继续完善；上一版待确认草案未采纳。"
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
    # 沉淀阶段重新填写 step1 时，重新生成 phase 级别引导语
    result_data: dict = {}
    if phase_step == "rumination":
        vip_r = getattr(rec, "vip_level", 1) or 1
        llm_r = _get_dialogue_llm_provider(vip_level=vip_r)
        basic_info_r = _load_basic_info_from_activation(request.activation_code)
        prior_r = _load_prior_context_from_activation(
            request.activation_code, phase_step, report
        )
        greeting_text, _ = await synthesize_rumination_entry_greeting(
            llm_r,
            basic_info=basic_info_r,
            prior_block=prior_r,
            normalize_token_usage=_normalize_token_usage,
        )
        result_data["entry_greeting"] = greeting_text

    return SimpleChatResponse(code=200, message="success", data=result_data)


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
    registry.bind_session(report["report_id"], phase_step, logical_session_id)
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
                **IDCodec.build_message_ids(
                    thread_id=logical_session_id,
                    activation_session_id=rec.session_id,
                ),
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
                **IDCodec.build_thread_ref(logical_session_id),
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
            phase_labels = {"values": "价值观", "strengths": "优势", "interests": "热爱", "purpose": "使命"}
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
        # 该阶段无任何已注册线程（用户已全部删除）→ 返回空历史，
        # 避免 fallback 到磁盘上的旧 act_sid 残留文件。
        if not logical_session_id:
            root = get_effective_simple_root(rec)
            registry = ReportRegistry(base_dir=str(root))
            record = registry.get_report_by_id(report["report_id"]) or {}
            step_payload = ((record.get("steps") or {}).get(phase_step)) or {}
            return SimpleHistoryResponse(
                code=200,
                message="success",
                data={
                    "messages": [],
                    "metadata": {
                        **IDCodec.build_history_metadata_ids(
                            thread_id=None,
                            activation_session_id=IDCodec.activation_session_id_from_rec(rec),
                        ),
                        "thread_completed": False,
                        "step_locked": bool(step_payload.get("locked", False)),
                    },
                    "activation": IDCodec.build_activation_client_view(rec, None),
                    "report_id": report["report_id"],
                    "step_id": phase_step,
                },
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
                    **IDCodec.build_history_metadata_ids(
                        thread_id=logical_session_id,
                        activation_session_id=IDCodec.activation_session_id_from_rec(rec),
                    ),
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
                "activation": IDCodec.build_activation_client_view(rec, logical_session_id),
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
    registry = ReportRegistry(base_dir=str(get_effective_simple_root(rec)))
    registry.bind_session(report["report_id"], phase_step, logical_session_id)
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
    front_activation_session_id = IDCodec.read_activation_session_id(
        request.model_dump(exclude_none=True),
        fallback=None,
    )
    if request.client_conclusion_ui:
        logger.debug(
            "[message_stream] client_conclusion_ui thread=%s activation_session_id(front=%s,server=%s) payload=%s",
            logical_session_id,
            front_activation_session_id or "-",
            rec.session_id,
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

        if phase_step == "rumination":
            question_bank = ""
        else:
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
        rumination_neg_inj = ""
        if phase_step == "rumination":
            try:
                rid = report.get("report_id")
                if rid:
                    rp = load_rumination_progress(Path(reports_root), rid)
                    neg_st = rp.get("rumination_neg_state") or {}
                    if neg_st.get("status") == "exploring":
                        inj = str(neg_st.get("injection_zh") or "").strip()
                        if inj:
                            rumination_neg_inj = inj
            except Exception:
                pass
        # 使命阶段：加载 purpose_progress 并构建注入块
        purpose_prog_injection_s = ""
        if phase_step == "purpose":
            try:
                conv_data_s = await conv_manager.get_conversation_data(session_id, category)
                meta_s = conv_data_s.get("metadata") or {}
                prog_s = normalize_progress(meta_s.get("purpose_progress"))
                purpose_prog_injection_s = build_progress_injection(prog_s)
            except Exception:
                purpose_prog_injection_s = ""
        system_prompt = _build_system_prompt(
            phase_step,
            question_bank=question_bank,
            basic_info=basic_info,
            prior_context=prior_context,
            template_override=(override_cfg or {}).get("template"),
            extra_goal_hint=(override_cfg or {}).get("extra_goal_hint", ""),
            values_info=vi_s,
            rumination_step_addon=ra_s,
            rumination_neg_injection=rumination_neg_inj,
            purpose_progress_injection=purpose_prog_injection_s,
        )
        llm_messages = [LLMMessage(role="system", content=system_prompt)]

        # ── 构建历史上下文（rumination 按子步隔离，其他阶段保持原逻辑）──
        rumination_filter_step_val = int(request.rumination_filter_step) if phase_step == "rumination" and request.rumination_filter_step else 0

        if rumination_filter_step_val > 0:
            # Rumination：只取当前子步的消息 + 之前子步的累积 anchor
            step_messages = [
                m for m in history_messages
                if int(m.get("filter_step") or 0) == rumination_filter_step_val
            ]
            trimmed = step_messages[-30:]

            # 加载之前子步的 anchor 并拼接
            try:
                step_anchors = await load_rumination_step_anchors(
                    session_id, category, conv_manager
                )
            except Exception:
                step_anchors = {}
            anchor_parts = []
            for s in range(1, rumination_filter_step_val):
                a = step_anchors.get(str(s))
                if a:
                    anchor_parts.append(f"[子步 {s} 要点] {a}")
            if anchor_parts:
                accumulated = "\n---\n".join(anchor_parts)
                llm_messages.append(
                    LLMMessage(role="assistant", content=f"[此前对话要点]\n{accumulated}")
                )
        else:
            # 非 rumination 阶段：使用原有 anchor + trim 逻辑
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
                    **IDCodec.build_message_ids(
                        thread_id=logical_session_id,
                        activation_session_id=rec.session_id,
                    ),
                    "step_id": phase_step,
                    "filter_step": int(request.rumination_filter_step) if phase_step == "rumination" and request.rumination_filter_step else None,
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
        if phase_step == "rumination" and (
            cmeta.get("state") == CONCLUSION_STATE_PENDING or isinstance(cmeta.get("draft"), dict)
        ):
            await conv_manager.update_metadata(
                session_id,
                category,
                {
                    **_build_conclusion_meta_update(
                        state=CONCLUSION_STATE_NONE,
                        final=cmeta.get("final"),
                        feedback="",
                        shown_at=None,
                        thread_completed=False,
                    ),
                    "conclusion_reject_baseline_user_count": None,
                },
            )
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

        if phase_step != "rumination" and pending_conclusion and not cmeta.get("thread_completed"):
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
                        **IDCodec.build_thread_ref(logical_session_id),
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
                            basic_info=basic_info,
                            prior_context=prior_context,
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
                                **IDCodec.build_message_ids(
                                    thread_id=logical_session_id,
                                    activation_session_id=rec.session_id,
                                ),
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
                                **IDCodec.build_message_ids(
                                    thread_id=logical_session_id,
                                    activation_session_id=rec.session_id,
                                ),
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
                                **IDCodec.build_thread_ref(logical_session_id),
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

            elif pending_state in {"rejected", "continue"}:
                non_confirm_feedback = (user_content or "").strip()
                if not non_confirm_feedback:
                    non_confirm_feedback = (
                        pending_msg if pending_state == "continue" else "用户明确表示需要继续完善"
                    )
                await conv_manager.update_metadata(
                    session_id,
                    category,
                    {
                        **_build_conclusion_meta_update(
                            state=CONCLUSION_STATE_REJECTED,
                            final=cmeta.get("final"),
                            feedback=non_confirm_feedback,
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
                            **IDCodec.build_thread_ref(logical_session_id),
                            "decision_state": pending_state,
                            "pending": pending_conclusion,
                            "feedback": non_confirm_feedback,
                            "decision_msg": pending_msg,
                        },
                    )
                except Exception:
                    pass
                pending_conclusion = None
                rejected_feedback = non_confirm_feedback

        # 同步最新 metadata（含 pending→rejected），并按需注入「每 N 轮」轻量 system 提醒
        conv_data = await conv_manager.get_conversation_data(session_id, category)
        meta = conv_data.get("metadata", {})
        cmeta = _read_conclusion_meta(meta)
        user_count = _count_user_messages(conv_data.get("messages"))
        pending_conclusion = cmeta.get("draft")
        rejected_feedback = cmeta.get("feedback") or ""

        should_try_retrigger = False
        if (
            cmeta.get("state") == CONCLUSION_STATE_REJECTED
            and not cmeta.get("thread_completed")
            and not isinstance(pending_conclusion, dict)
            and phase_step != "rumination"
        ):
            baseline = meta.get("conclusion_reject_baseline_user_count")
            if isinstance(baseline, int) and user_count - baseline >= CONCLUSION_REJECT_NUDGE_USER_TURNS:
                should_try_retrigger = True
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

        # 用户否定后：将状态备注注入 system（避免被当作 assistant 可见话术续写）
        if rejected_feedback and not pending_conclusion:
            rejected_injection = (
                "[内部状态参考·严禁向用户复述]\n"
                "以下文本仅供内部状态参考，严禁向用户复述或引用其中原文。\n"
                + format_rejected_conclusion_injection(rejected_feedback)
            )
            if llm_messages and llm_messages[0].role == "system":
                llm_messages[0] = LLMMessage(
                    role="system",
                    content=llm_messages[0].content + "\n\n" + rejected_injection,
                )
            else:
                llm_messages.append(LLMMessage(role="system", content=rejected_injection))

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
            rfs_stream = int(request.rumination_filter_step or 0) if phase_step == "rumination" else 0
            if phase_step == "rumination":
                stream_markers: List[Tuple[str, str]] = (
                    [("[ROW_STATE_JSON]", "[/ROW_STATE_JSON]")] if rfs_stream == 3 else []
                )
            else:
                stream_markers = [("[STATE_JSON]", "[/STATE_JSON]")]
            stream_hidden_filter = _build_stream_hidden_block_filter(
                block_markers=stream_markers
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

        # 3) 解析模型状态输出（STATE_JSON / ROW_STATE_JSON）并驱动 pending / 子步 3 游标
        raw_full_reply = full_reply
        state_obj = None
        step3_row_unlock_progress: Optional[Dict[str, Any]] = None
        if phase_step == "rumination":
            rfs_parse = int(request.rumination_filter_step or 0)
            if rfs_parse == 3:
                visible_r, row_st = _split_visible_reply_and_row_state(raw_full_reply)
                full_reply = visible_r
                rid_sp = report.get("report_id")
                if row_st and rid_sp:
                    step3_row_unlock_progress = _try_rumination_step3_row_unlock(
                        Path(reports_root), str(rid_sp), row_st
                    )
                # 兜底：AI 未输出 ROW_STATE_JSON 或校验失败时，若当前行假设已完整则自动推进
                if not step3_row_unlock_progress and rid_sp:
                    step3_row_unlock_progress = _try_rumination_step3_auto_unlock(
                        Path(reports_root), str(rid_sp)
                    )
            else:
                full_reply = raw_full_reply
        else:
            visible_reply, state_obj = _split_visible_reply_and_state(raw_full_reply)
            full_reply = visible_reply
            # 使命阶段：解析 purpose_progress 并更新 metadata
            if phase_step == "purpose" and state_obj:
                draft_raw = state_obj.get("draft")
                if isinstance(draft_raw, dict) and "purpose_progress" in draft_raw:
                    try:
                        conv_data_pp = await conv_manager.get_conversation_data(session_id, category)
                        meta_pp = conv_data_pp.get("metadata") or {}
                        cur_prog = normalize_progress(meta_pp.get("purpose_progress"))
                        updated_prog = apply_progress_update(cur_prog, draft_raw["purpose_progress"])
                        await conv_manager.update_metadata(
                            session_id, category,
                            {"purpose_progress": updated_prog},
                        )
                    except Exception:
                        pass

        # 保存助手回复（只保存用户可见文本）
        if full_reply:
            msg_payload = {
                "role": "assistant",
                "content": full_reply,
                **IDCodec.build_message_ids(
                    thread_id=logical_session_id,
                    activation_session_id=rec.session_id,
                ),
                "step_id": phase_step,
                "filter_step": int(request.rumination_filter_step) if phase_step == "rumination" and request.rumination_filter_step else None,
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
                        **IDCodec.build_message_ids(
                            thread_id=logical_session_id,
                            activation_session_id=rec.session_id,
                        ),
                        "step_id": phase_step,
                        "filter_step": int(request.rumination_filter_step) if phase_step == "rumination" and request.rumination_filter_step else None,
                        "agent_id": "coach",
                        "event": "table_output",
                        "table_format": "markdown",
                    },
                )
            if step3_row_unlock_progress:
                yield (
                    "data: "
                    + json.dumps(
                        {"rumination_progress": step3_row_unlock_progress},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
        pending_spawned_in_turn = False
        if state_obj and not cmeta.get("thread_completed"):
            state_name = str(state_obj.get("state") or "").strip().lower()
            draft = state_obj.get("draft")
            if state_name == "pending_ready" and isinstance(draft, dict):
                # 自动出卡统一链路：pending_ready 先走结论生成器，稳定复用文风规则与示例。
                draft_to_save = sanitize_pending_conclusion_draft(phase_step, dict(draft))
                # 使命阶段：用 metadata 的 confirmed_rows 覆盖 LLM 的 experience_value_rows
                if phase_step == "purpose":
                    try:
                        conv_data_pr = await conv_manager.get_conversation_data(session_id, category)
                        meta_pr = conv_data_pr.get("metadata") or {}
                        prog_pr = normalize_progress(meta_pr.get("purpose_progress"))
                        meta_rows = progress_to_experience_value_rows(prog_pr)
                        if meta_rows:
                            draft_to_save["experience_value_rows"] = meta_rows
                    except Exception:
                        pass
                refined_conclusion = None
                reasoning_llm = _get_reasoning_llm_provider(vip_level=vip_level)
                try:
                    refined_conclusion = await asyncio.wait_for(
                        check_dimension_complete(
                            phase_step,
                            conv_history,
                            prior_conclusion=draft_to_save,
                            vip_level=vip_level,
                            llm_provider=reasoning_llm,
                            skip_completion_check=True,
                            basic_info=basic_info,
                            prior_context=prior_context,
                        ),
                        timeout=CONCLUSION_GEN_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    refined_conclusion = None
                except Exception:
                    refined_conclusion = None
                if isinstance(refined_conclusion, dict):
                    draft_to_save = sanitize_pending_conclusion_draft(
                        phase_step, dict(refined_conclusion)
                    )
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
                            **IDCodec.build_thread_ref(logical_session_id),
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
                pending_spawned_in_turn = True
            elif state_name == "continue":
                # 无状态迁移，保持当前会话态
                pass

        # 拒绝/继续后，按轮次触发兜底重试：满足完成条件时自动再次唤起结论卡
        if (
            should_try_retrigger
            and not pending_spawned_in_turn
            and phase_step != "rumination"
            and not cmeta.get("thread_completed")
        ):
            reasoning_llm = _get_reasoning_llm_provider(vip_level=vip_level)
            try:
                retrigger_conclusion = await asyncio.wait_for(
                    check_dimension_complete(
                        phase_step,
                        conv_history,
                        prior_conclusion=None,
                        vip_level=vip_level,
                        llm_provider=reasoning_llm,
                        basic_info=basic_info,
                        prior_context=prior_context,
                    ),
                    timeout=CONCLUSION_GEN_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                retrigger_conclusion = None
            except Exception:
                retrigger_conclusion = None

            if isinstance(retrigger_conclusion, dict):
                draft_to_save = sanitize_pending_conclusion_draft(
                    phase_step, dict(retrigger_conclusion)
                )
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
                            **IDCodec.build_thread_ref(logical_session_id),
                            "pending_conclusion": draft_to_save,
                            "source": "retrigger_after_rejected",
                        },
                    )
                except Exception:
                    pass
                yield (
                    "data: "
                    + json.dumps({"dimension_conclusion": draft_to_save}, ensure_ascii=False)
                    + "\n\n"
                )

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
        # 清理对应的 .lock 文件
        lock_file = file.with_suffix(file.suffix + ".lock")
        lock_file.unlink(missing_ok=True)
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除会话文件失败: {e}")

    updated = registry.remove_session(report_id, phase_step, thread_id) or {}
    step_payload = ((updated.get("steps") or {}).get(phase_step)) or {}

    # 清理残留的 act_sid 对话文件：当 session_ids 清空后，
    # 如果磁盘上仍存在 {phase}__{rec.session_id}.json（历史遗留），
    # 一并删除，防止 GET /history fallback 到该文件。
    remaining_sids = step_payload.get("session_ids") or []
    if not remaining_sids:
        act_sid = (rec.session_id or "").strip()
        if act_sid:
            stale = registry.get_step_session_file(report_id, phase_step, act_sid)
            try:
                if stale.is_file():
                    stale.unlink()
                lock_file = stale.with_suffix(stale.suffix + ".lock")
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass
    return SimpleChatResponse(
        code=200,
        message="success",
        data={
            "deleted": True,
            "step_id": phase_step,
            **IDCodec.build_thread_ref(thread_id),
            "remaining_thread_ids": step_payload.get("session_ids") or [],
            "selected_thread_id": step_payload.get("selected_session_id"),
            "step_locked": bool(step_payload.get("locked", False)),
        },
    )

