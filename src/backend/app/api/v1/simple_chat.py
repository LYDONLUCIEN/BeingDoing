"""
简单模式对话 API

特点：
- 不使用 LangGraph
- 通过一个较长的 system_prompt + 历史消息，分模块（values/strengths/interests）引导用户
- 会话由「激活码」标识，对话历史保存在 data/simple 下
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional
import asyncio
import json
import random
import logging
import re

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.llmapi import get_default_llm_provider, LLMMessage
from app.api.v1.auth import get_current_user, _is_debug_admin
from app.config.settings import settings
from app.core.knowledge.loader import KnowledgeLoader
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    ActivationStatus,
    bind_session_id_for_ensure_report,
    get_effective_simple_root,
)
from app.utils.sandbox_fork import assert_sandbox_not_expired
from app.utils.conversation_file_manager import ConversationFileManager
from app.core.dimension_completion_checker import (
    check_dimension_complete,
    detect_explicit_completion,
    _should_run_completion_check,
)
from app.services.analytics_service import AnalyticsService
from app.utils.report_registry import ReportRegistry, STEP_IDS, STEP_ORDER
from app.utils.rumination_progress import (
    load_rumination_progress,
    save_rumination_progress,
)
from app.utils.rumination_ops import (
    gen_table,
    filter_strength,
    filter_match,
    extract_from_prior_context,
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

# 每阶段随机抽取的题目数量
SIMPLE_QUESTION_SAMPLE_SIZE = 6
# 发送给 LLM 的历史消息最大轮数（减少 token、加快响应）
MAX_HISTORY_TURNS = 20
# 并发 LLM 调用限制（0=不限制）
_LLM_SEM = None


def _get_llm_semaphore():
    global _LLM_SEM
    if _LLM_SEM is None:
        n = getattr(settings, "LLM_MAX_CONCURRENT", 0) or 0
        _LLM_SEM = asyncio.Semaphore(n) if n > 0 else None
    return _LLM_SEM


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


def _skip_expired_for_debug(rec, user: Optional[dict]) -> bool:
    """Debug 管理员可跳过过期检查"""
    return (
        getattr(settings, "DEBUG_MODE", False)
        and _is_debug_admin(user)
        and rec.status == ActivationStatus.EXPIRED
    )


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
    沙箱激活码使用 data/simple/sandboxes/{fork_id}/ 作为存储根。
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

    # 进入新阶段前，锁定上一阶段（提交进入下一步后不可修改）
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
        return "values"  # rumination 综合四维，复用 values 题库
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


def _looks_like_markdown_table(text: str) -> bool:
    if not text:
        return False
    has_row = bool(re.search(r"^\s*\|.+\|\s*$", text, flags=re.MULTILINE))
    has_sep = bool(re.search(r"^\s*\|[\s:\-|]+\|\s*$", text, flags=re.MULTILINE))
    return has_row and has_sep


def _assistant_indicates_completion(text: str) -> bool:
    """
    检测助手回复是否在语义上宣告“已完成/可出总结卡”。
    用于兜底触发结论卡生成，避免用户看到“完成了”却没有卡片。
    """
    if not text:
        return False
    lowered = text.lower()
    completion_markers = [
        "完成了",
        "已完成",
        "完成本轮",
        "可以结束",
        "输出答题卡",
        "生成答题卡",
        "总结如下",
        "探索结论",
        "最终结论",
        "请确认下方摘要",
    ]
    return any(marker in text for marker in completion_markers) or any(
        marker in lowered for marker in ["conclusion", "summary card", "final summary"]
    )


def _normalize_token_usage(usage: Optional[dict]) -> dict:
    usage = usage or {}
    in_tokens = int(usage.get("prompt_tokens") or 0)
    out_tokens = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (in_tokens + out_tokens))
    return {
        "prompt_tokens": in_tokens,
        "completion_tokens": out_tokens,
        "total_tokens": total,
    }


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
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code)
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
    manager = SimpleActivationManager()
    rec = manager.get_activation(activation_code)
    if not rec:
        return ""
    root = get_effective_simple_root(rec)
    reports_root = str(root / "reports")
    if report and report.get("report_id"):
        text = load_prior_context_for_report(report["report_id"], phase, reports_root)
        if text:
            return text
    return load_prior_context(rec.session_id, phase, str(root))


@router.get("/survey")
def get_survey(
    activation_code: str,
    current_user: dict = Depends(get_current_user),
):
    """获取指定激活码下的调研问卷数据（用户级，仅 1 份）"""
    manager = SimpleActivationManager()
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
    manager = SimpleActivationManager()
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
    manager = SimpleActivationManager()
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
    manager = SimpleActivationManager()
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
    activation_code: str
    thread_id: str
    step: int
    table_data: List[dict]


@router.get("/rumination-progress", response_model=SimpleChatResponse)
def get_rumination_progress(
    activation_code: str,
    current_user: dict = Depends(get_current_user),
):
    """获取 rumination 阶段进度"""
    try:
        manager = SimpleActivationManager()
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
    manager = SimpleActivationManager()
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


@router.post("/rumination-table-submit", response_model=SimpleChatResponse)
def rumination_table_submit(
    request: RuminationTableSubmitRequest,
    current_user: dict = Depends(get_current_user),
):
    """提交 rumination 筛选表格数据，更新 progress，并可能返回下一步表格。"""
    manager = SimpleActivationManager()
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
    step = max(1, min(9, request.step))
    progress = save_rumination_progress(
        reports_root, report_id, filter_step=step, filter_table=request.table_data
    )

    next_table = None
    table_data = request.table_data
    if step == 1 and table_data:
        filtered = filter_strength(table_data)
        if filtered:
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
            save_rumination_progress(
                reports_root, report_id, filter_table=step2_rows
            )

    data: dict = {"progress": progress, "next_step": step}
    if next_table:
        data["next_table_widget"] = next_table

    return SimpleChatResponse(code=200, message="success", data=data)


@router.get("/rumination-get-table", response_model=SimpleChatResponse)
def rumination_get_table(
    activation_code: str,
    step: Optional[int] = 1,
    current_user: dict = Depends(get_current_user),
):
    """获取 rumination 筛选流程的当前步骤表格（进入筛选时或下一步）"""
    manager = SimpleActivationManager()
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
    _, strengths_list, interests_list = extract_from_prior_context(prior_context)
    passions = interests_list if interests_list else ["热爱1", "热爱2"]
    strengths_list = strengths_list if strengths_list else ["优势1", "优势2"]

    step = max(1, min(9, step or 1))
    if step == 1:
        rows = gen_table(strengths_list, passions)
        payload = _build_table_widget_payload(
            step=1,
            rows=rows,
            columns=[
                {"key": "id", "label": "id"},
                {"key": "热爱", "label": "热爱"},
                {"key": "优势", "label": "优势"},
                {
                    "key": "优势标记",
                    "label": "优势标记",
                    "options": ["有充实感，与成功有关", "有充实感", "不确定"],
                },
            ],
            editable_cols=["优势标记"],
            guide_text="请确认您的热爱与优势列表。如需修改，可直接在表格中编辑标记。确认后我们将进行匹配分析。",
        )
    else:
        prev_table = progress.get("filter_table") or []
        if step == 2:
            filtered = filter_strength(prev_table)
            rows = filter_match(filtered)
            payload = _build_table_widget_payload(
                step=2,
                rows=rows,
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
        else:
            payload = None

    return SimpleChatResponse(
        code=200, message="success", data={"table_widget": payload}
    )


def _build_system_prompt(
    phase: str,
    question_bank: str = "",
    basic_info: str = "暂无",
    prior_context: str = "",
) -> str:
    """
    根据阶段构建 system prompt。
    phase: values | strengths | interests
    question_bank: 从 question.md 随机抽取的题目文本
    basic_info: 来访者基本信息（调研问卷）
    prior_context: 上一阶段咨询结果（values → 空；strengths → values 结果；interests → strengths+values 结果）
    """
    prior_block = f"\n\n以下是该来访者在上一轮咨询中的谈话结果，供你参考：\n{prior_context}" if prior_context.strip() else ""

    if phase == "values":
        return f"""你是一名专业的职业规划咨询师，正在进行第一轮咨询。本轮咨询的目标是：**帮助用户发现并确认对其职业发展最重要的5个价值观关键词**。

请严格遵循以下咨询流程和方法。

### 咨询流程

1. **开场提问**：直接询问用户："你能否直接告诉我，在你心中对你最重要的5个价值观关键词是什么？"（例如：成就感、稳定、创新、人际关系等）
2. **记录初始答案**：
   - 如果用户给出了任何关键词（无论数量多少），请全部记录下来，并标记为"用户自述"。
   - 如果用户无法给出任何关键词，或给出的不足5个，请记录下来，并继续下一步。
3. **深度提问探索**：进入正式的问题探索环节。
   - **提问原则**：每次只向用户提出**一个**问题。问题可以不局限于工作，可以涉及生活、过往经历、未来畅想等，目的是从用户的回答中挖掘潜在的价值观。
   - **追问技巧**：根据用户的回答进行追问，引导用户深入思考，直到用户自己能清晰地总结出："这对我来说，意味着[价值观关键词]很重要。"
   - **记录关键词**：每从一个问题中提炼出关键词，就记录下来，并标记为"探索发现"。
4. **整合与确认**：
   - **对比初始答案**：将"探索发现"的关键词与第一步中用户"用户自述"的关键词进行对比。
   - 如果重复出现，则在该关键词旁记录"权重+1"。
   - 如果出现全新的关键词，向用户确认："通过刚才的讨论，我们发现了[新关键词]这个价值观，你觉得它对你来说重要吗？可以加入你的价值观列表吗？"
5. **收敛判断**：持续进行提问探索，直到满足以下任一条件：
   - **收敛条件**：无论再提出什么新问题，都无法从用户的回答中提炼出任何新的价值观关键词。
   - **数量上限**：提出的独立新问题（不包括追问）累计达到10个。
   - **注意**：达到5个关键词并不代表收敛，必须确认无法再发现新的关键词才算收敛。
6. **排序与整合**：
   - **引导排序**：当关键词收敛后，请用户对所有已确认的关键词（包括用户自述和探索发现的）进行优先级排序。
   - **合并与删减**：如果关键词过多（超过5个），引导用户合并含义相近的词，或删减相对不重要的词，并请用户给出自己对每个关键词的理解和解释。如果合并后数量**少于5个**，则需继续重复步骤3-5的提问探索。
   - **核对差异**：在用户给出排序后，将其排序结果与你记录过程中的"权重"进行对比。如果存在明显差异，向用户提问以澄清原因；如果无差异，则直接采用用户的排序。
7. **最终确认**：向用户呈现最终结果："我们最终确定了对你最重要的5个价值观关键词，按优先级排序是：1. [关键词]（你的解释），2. [关键词]（你的解释）…… 你确认这个结果吗？"
8. **结束对话**：用户确认后，本轮咨询结束。告知用户："恭喜你完成了第一轮价值观探索。下一轮我们将进入优势探索，帮助你发现你的核心能力。我们下次见。"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要直接替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **完整收敛**：务必确认无论问什么都无法再提取新词，才算收敛，不能因为凑够5个就停止。
- **完成即引导答题卡**：当你判断用户已明确确认完成时，必须明确告知“将生成本维度答题卡总结”，不要只说“完成了”而不说明下一步。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你的价值观是什么」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "strengths":
        return f"""你是一名专业的职业规划咨询师，正在进行第二轮咨询。本轮咨询的目标是：**帮助用户发现并确认其最突出的10个优势**。

请先以友好、专业的态度与用户打招呼，然后按照以下流程和方法开展咨询。

### 咨询流程

1. **开场提问**：直接询问用户："你自己认为你的优势有哪些？请尽量列举。"
   - 如果用户给出了任何答案，请全部记录下来，标记为"用户自述"。
   - 如果用户无法给出任何答案，或给出的数量不足，请记录下来，并继续下一步。
2. **深度提问探索**：进入正式的问题探索环节。
   - **提问原则**：每次只向用户提出**一个**问题。问题可以不局限于工作，可以涉及生活、过往经历、未来畅想等，目的是从用户的回答中挖掘潜在的优势。
   - **追问技巧**：根据用户的回答进行追问，引导用户深入思考，直到用户自己能清晰地总结出："这对我来说，意味着[某项优势]是我的一个优势。"
3. **记录与确认**：
   - 每从一个问题中提炼出一个优势，就记录下来，并标记为"探索发现"。
   - **对比初始答案**：将"探索发现"的优势与第一步中用户"用户自述"的优势进行对比。
   - 如果重复出现，则在该优势旁记录"权重+1"。
   - 如果出现全新的优势，向用户确认："通过刚才的讨论，我们发现[新优势]可能是你的一个优势，你认可吗？可以加入你的优势列表吗？"
4. **重复提问直至达成10个**：持续进行提问探索，直到用户确认的优势累计达到**10个**。提取出的优势之间不能有重复。
5. **标记优势**：当用户确认了10个优势后，向用户解释标记体系的含义，并引导用户对每个优势进行标记。
   - **a. 有充实感，与成功有关**：你不仅做这件事时感到充实、有活力，而且它通常能带来好的结果或成就。
   - **b. 有充实感**：你做这件事时感到充实、充满能量，但并不一定每次都带来成功。
   - **c. 目前还不确定**：你对自己是否具备这个优势，或者使用时是否有充实感，还不太确定。
6. **确认标记结果**：当所有10个优势都标记完毕后，向用户呈现最终列表及对应的标记，询问用户是否确认。
7. **结束对话**：用户确认后，告知用户："恭喜你完成了第二轮优势探索。下一轮我们将进入热爱探索，帮助你发现你的激情所在。我们下次见！"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要直接替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **确保10个优势**：必须通过提问挖掘，直到用户认可并确认了10个不重复的优势。
- **提问差异化**：避免重复问类似问题，要变换角度，防止用户思维僵化或"钻牛角尖"。
- **完成即引导答题卡**：当你判断用户已明确确认完成时，必须明确告知“将生成本维度答题卡总结”，不要只说“完成了”而不说明下一步。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你的优势有哪些」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "interests":
        return f"""你是一名专业的职业规划咨询师，正在进行第三轮咨询。本轮咨询的目标是：**帮助用户发现3个"热爱"——即用户真正感兴趣、充满好奇的领域（以名词形式呈现，例如：自然环境、自我认知、足球、艺术创作等）**。

请先以亲切、专业的语气向用户介绍本次咨询的主题，然后严格遵循以下流程和方法开展咨询。

### 咨询流程

1. **开场提问**：直接询问用户："你自己认为，你有哪些热爱的事情或领域？请列举一些你真正感兴趣、充满好奇的方向。"
   - 如果用户给出了答案，请分析是否符合"热爱"的定义（感兴趣、好奇的领域，名词形式）。如果符合，记录下来，标记为"用户自述"。
   - 如果用户无法给出任何答案，或给出的答案不符合定义，则记录下来，并继续下一步。
2. **深度提问探索**：进入正式的问题探索环节。
   - **提问原则**：每次只向用户提出**一个**问题。问题可以不局限于工作，可以涉及生活、过往经历、未来畅想等，目的是从用户的回答中挖掘潜在的热爱领域。
   - **追问技巧**：根据用户的回答进行追问，引导用户深入思考，直到用户自己能清晰地总结出："我发现自己对[某个领域]真的很感兴趣/充满好奇。"
3. **记录与确认**：
   - 每从一个问题中提炼出一个热爱领域，就记录下来，并标记为"探索发现"。
   - **对比初始答案**：将"探索发现"的热爱与第一步中用户"用户自述"的热爱进行对比。
   - 如果重复出现，则在该热爱旁记录"权重+1"。
   - 如果出现全新的热爱，向用户确认："通过刚才的讨论，我们发现你对[新领域]似乎很有热情，你觉得可以把它列入你的热爱清单吗？"
4. **收集候选热爱清单**：
   - 持续进行提问探索，直到收集到的热爱领域（包括用户自述和探索发现的）达到**至少6个**。
   - 询问用户："目前我们列出了X个你热爱的领域（列出清单），你觉得这些是否全面表达了你所有的热爱？有没有什么重要的领域被遗漏了？"
   - 如果用户认为有遗漏，继续提问帮助用户补充，直到用户觉得清单已基本全面（或总数量达到12个左右，作为上限参考）。
   - **注意**：提取出的热爱领域不能重复，确保每个都是独特的。
5. **引导用户选出TOP 3**：
   - 当候选清单确定后（N≥6），请用户从中选出最重要的3个，作为"核心热爱"。
   - 你可以这样引导："在这些热爱的领域中，哪三个是你最想深入探索、最不愿意放弃的？为什么？"
   - 如果用户对选择感到困难，可以通过追问帮助其厘清优先级。
   - 如果用户不认可某一项热爱，需要重新确认该热爱是否应保留在候选清单中，必要时通过提问重新挖掘替代项。
6. **确认最终结果**：当用户明确选出TOP 3后，向用户呈现最终结果："你最终确认的3个核心热爱是：1. [热爱A]，2. [热爱B]，3. [热爱C]。你确认这个结果吗？"
7. **结束对话**：用户确认后，告知用户："恭喜你完成了第三轮热爱探索。下一轮我们将进入使命探索，帮助你找到你的人生召唤。我们下次见！"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要直接替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **提问差异化**：避免重复问类似问题，要变换角度，防止用户思维僵化或"钻牛角尖"。
- **热爱的形式**：确保提炼出的热爱是名词形式的领域，例如"人工智能"、"心理学"、"户外运动"等，而不是形容词或抽象感受。
- **完成即引导答题卡**：当你判断用户已明确确认完成时，必须明确告知“将生成本维度答题卡总结”，不要只说“完成了”而不说明下一步。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你的热爱有哪些」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "purpose":
        return f"""你是一名专业的职业规划咨询师，正在进行第四轮咨询。本轮咨询的目标是：**帮助用户发现其工作使命——即用户最希望为他人提供的核心价值**。

请先以祝贺和鼓励的语气开启对话，告知用户即将完成整个探索旅程，然后按照以下流程和方法开展咨询。

### 咨询流程

1. **开场与回顾**：
   - 亲切地向用户表示恭喜："恭喜你即将完成整个职业探索旅程！本轮我们将一起发现你的工作使命——你内心深处最希望为他人提供的价值。"
   - 帮助用户回忆第一轮咨询中确认的5个价值观关键词。参考下方"来访者上一轮咨询结果"中的价值观相关内容，向用户复述："还记得我们在第一轮一起探索出的对你最重要的5个价值观吗？它们是：[从上一轮结果中提取的5个价值观关键词]。在接下来的讨论中，我们会用到它们。"
2. **梳理价值经历**：
   - 引导用户梳理出**10个曾经为他人提供价值的经历**。这些经历可以来自工作、学习、志愿活动、日常生活等任何方面。
   - 提问示例："请你回想一下，在过去的生活或工作中，有哪些你曾经为他人提供帮助、解决问题或带来积极影响的经历？可以列出10个，每个用一两句话简单描述。"
   - 如果用户一时想不出10个，可以通过提问引导，但避免替用户决定。
3. **匹配价值观（逐个经历进行）**：
   - 针对每一段经历，与用户一起分析：在这段经历中，你提供或试图提供的价值，对应着第一轮中的哪个（或哪些）价值观关键词？
   - 向用户确认匹配是否准确，如果用户认可则记录；如果不认可，继续引导用户思考更匹配的价值观，直到用户确认。
   - 处理完一段经历后，继续下一段，直到10段经历全部匹配完成。（若用户实在想不出10段，可适当放宽至8-9段。）
4. **统计与总结**：
   - 完成经历分析后，统计每个价值观关键词出现的次数。
   - 根据统计结果，为用户整理一份使命总结，内容包括：
     - **（1）经历-价值观对应表格**：第一列是每段经历的简要概括，第二列是该经历对应的价值观关键词。
     - **（2）核心使命陈述**：用一句话概括你最希望传递的核心价值观；对这句话进行展开说明；用一句话概括你希望通过工作传递的最终目的。
5. **确认总结**：向用户展示上述总结，询问是否认可，有没有需要调整的地方。根据用户反馈调整，直到用户完全认可。
6. **结束对话**：用户确认后，告知用户："太棒了！你已经完成了使命探索。接下来我们将进行最后一轮对话——帮助你整合所有发现，找到具体的职业发展方向。我们下次见！"

### 重要准则

- **引导而非灌输**：始终给用户思考和回答的空间，不要替用户下结论。
- **一次一问**：严格遵守每轮对话只提一个问题。
- **提问差异化**：在引导用户回忆经历时，变换提问角度，避免重复。
- **经历数量**：尽量引导至10段经历，若用户实在想不出可适当放宽到8-9段。
- **匹配准确**：在匹配价值观时，一定要得到用户的明确认可。
- **完成即引导答题卡**：当你判断用户已明确确认完成时，必须明确告知“将生成本维度答题卡总结”，不要只说“完成了”而不说明下一步。
- 【对话续写】若对话已有历史，必须在已有探索基础上继续深挖，禁止重复开场式提问（如「你为什么而工作」）或泛泛寒暄，应基于用户已有回答进行追问和深化。

### 题库参考

以下题库可供选择，你也可以根据对话情境灵活提问：
{question_bank}

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    if phase == "rumination":
        return f"""你是一名专业的职业规划咨询师，正在进行最后一轮咨询——沉淀阶段。本轮的目标是：**综合用户之前探索的价值观、优势、热爱和使命，帮助用户确定三个最终职业发展方向**。

### 咨询流程概览

1. **开场白**：亲切问候，祝贺用户进入最后一轮，说明本次目标，询问是否准备好开始。
2. **回顾**（按顺序）：回顾价值观、优势、热爱、工作目的，每项确认后再进入下一项，询问是否需要微调。
3. **筛选**：回顾完成后，将进入表格筛选流程（热爱×优势匹配、假设生成、价值过滤、激情过滤、现实过滤、相似过滤），逐步缩小方向。
4. **最终选择**：从筛选结果中引导用户选出最想做的三件事。
5. **推荐与发展**：为每个方向推荐具体的职业发展可能性。
6. **结束对话**：共情总结，询问下一步计划，调用结束流程。

### 重要准则

- 每次只提一个问题，给用户充分的回答空间。
- 当用户卡顿时，提供温和的引导，而非直接给答案。
- 判断对话结束条件：用户已选出 top 3 方向并确认。
- 【对话续写】若对话已有历史，在已有基础上继续，禁止重复开场。

来访者基本信息：{basic_info}{prior_block}

请直接用中文和用户继续这一轮对话。"""

    return _build_system_prompt("values", question_bank, basic_info, prior_context)


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
    manager = SimpleActivationManager()
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

    # 读取历史消息（只取当前分类）
    history_messages: List[dict] = await conv_manager.get_messages(
        session_id=session_id,
        category=category,
    )

    llm = get_default_llm_provider()

    # 从 question.md 按阶段随机抽取题目，动态注入提示词
    question_bank = _get_random_questions_for_phase(phase_step)
    basic_info = _load_basic_info_from_activation(request.activation_code)
    prior_context = _load_prior_context_from_activation(
        request.activation_code, phase_step, report
    )
    system_prompt = _build_system_prompt(phase_step, question_bank=question_bank, basic_info=basic_info, prior_context=prior_context)
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
    manager = SimpleActivationManager()
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

    # 没有历史：生成一条首轮引导问题
    llm = get_default_llm_provider()
    question_bank = _get_random_questions_for_phase(phase_step)
    basic_info = _load_basic_info_from_activation(request.activation_code)
    prior_context = _load_prior_context_from_activation(
        request.activation_code, phase_step, report
    )
    system_prompt = _build_system_prompt(phase_step, question_bank=question_bank, basic_info=basic_info, prior_context=prior_context)
    llm_messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content="我是来访者，你需要向我提问。以下是我的基本信息：暂无。请给出第一轮温柔而具体的引导问题，让我开始思考。"),
    ]
    token_usage = _normalize_token_usage(None)
    try:
        response = await llm.chat(llm_messages, temperature=0.7)
        reply_text = (response.content or "").strip()
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
    manager = SimpleActivationManager()
    phase_val = (request.phase or "values").strip() or "values"
    rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
        manager=manager,
        activation_code=request.activation_code,
        current_user=current_user,
        phase=phase_val,
        thread_id=request.thread_id,
    )
    step_meta = ((report.get("steps") or {}).get(phase_step) or {})
    if step_meta.get("locked"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该阶段已锁定，不能再修改")
    await conv_manager.update_metadata(
        report["report_id"], category,
        {
            "thread_completed": False,
            "pending_conclusion": None,
        },
    )
    return SimpleChatResponse(code=200, message="success", data={})


@router.post("/thread/complete", response_model=SimpleChatResponse)
async def mark_thread_complete(
    request: ThreadCompleteRequest,
    current_user: dict = Depends(get_current_user),
):
    """标记某对话为已完成（用户点击「确认没有问题」后调用）"""
    manager = SimpleActivationManager()
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
    dimension_conclusion = metadata.get("dimension_conclusion")
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
    await conv_manager.update_metadata(report["report_id"], category, {"thread_completed": True})
    if dimension_conclusion:
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
    manager = SimpleActivationManager()
    phase_val = (phase or "values").strip() or "values"
    phase_step = ReportRegistry.normalize_step_id(phase_val)
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
        completed = bool(meta.get("thread_completed"))
        threads.append({
            "id": tid,
            "title": f"对话 {idx + 1}",
            "status": "completed" if completed else "in-progress",
            "messages": [],  # 列表不返回消息体，由 /history 按需加载
            "createdAt": ts_ms or int(datetime.now(timezone.utc).timestamp() * 1000),
            "dimensionConclusion": meta.get("dimension_conclusion"),
            "selected": tid == selected_id,
        })

    return SimpleHistoryResponse(
        code=200,
        message="success",
        data={
            "threads": threads,
            "report_id": report_id,
            "step_id": phase_step,
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
        manager = SimpleActivationManager()
        phase_val = (phase or "values").strip() or "values"
        rec, report, phase_step, logical_session_id, category, conv_manager = _resolve_report_context(
            manager=manager,
            activation_code=activation_code,
            current_user=current_user,
            phase=phase_val,
            thread_id=thread_id,
        )
        session_id = report["report_id"]

        conv_data = await conv_manager.get_conversation_data(session_id, category)
        history_messages = conv_data.get("messages", [])
        metadata = conv_data.get("metadata", {})

        return SimpleHistoryResponse(
            code=200,
            message="success",
            data={
                "messages": history_messages,
                "metadata": {
                    "session_id": logical_session_id,
                    "thread_completed": metadata.get("thread_completed", False),
                    "dimension_conclusion": metadata.get("dimension_conclusion"),
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
    manager = SimpleActivationManager()
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

    async def event_stream() -> AsyncIterator[str]:
        llm = get_default_llm_provider(vip_level=vip_level)
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

        question_bank = _get_random_questions_for_phase(phase_step)
        basic_info = _load_basic_info_from_activation(request.activation_code)
        prior_context = _load_prior_context_from_activation(
            request.activation_code, phase_step, report
        )
        system_prompt = _build_system_prompt(phase_step, question_bank=question_bank, basic_info=basic_info, prior_context=prior_context)
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

        # 1) 若有上一轮后台检测的 pending_conclusion，综合本轮输入重新生成并展示
        conv_data = await conv_manager.get_conversation_data(session_id, category)
        meta = conv_data.get("metadata", {})
        pending_conclusion = meta.get("pending_conclusion")
        conv_history = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in conv_data.get("messages", [])
        ]
        user_count = sum(1 for m in conv_data.get("messages", []) if m.get("role") == "user")
        conclusion_shown_at = meta.get("conclusion_shown_at_turn")

        if pending_conclusion and not meta.get("thread_completed"):
            # 综合本轮用户输入 + 上一轮结论，重新生成确定性结论
            try:
                dimension_conclusion = await check_dimension_complete(
                    phase_step, conv_history, prior_conclusion=pending_conclusion, vip_level=vip_level
                )
            except Exception as e:
                # 上游 LLM 异常时，降级为继续普通对话，避免流接口 500。
                logger.exception("check_dimension_complete(regenerate) failed, continue chat stream: %s", e)
                dimension_conclusion = None
            if dimension_conclusion:
                await conv_manager.update_metadata(
                    session_id, category,
                    {
                        "conclusion_shown_at_turn": user_count,
                        "dimension_conclusion": dimension_conclusion,
                        "pending_conclusion": None,
                    },
                )
                transition_msg = "好的，根据我们的对话，我为你整理出本维度的探索结论，请确认下方摘要是否准确。"
                yield f"data: {{\"chunk\": {json.dumps(transition_msg, ensure_ascii=False)} }}\n\n"
                full_reply = transition_msg
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
                yield f"data: {{\"dimension_conclusion\": {json.dumps(dimension_conclusion, ensure_ascii=False)} }}\n\n"
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
                    await AnalyticsService.record_chat_turn(session_id=logical_session_id, dimension=phase_step, user_input_chars=len(user_content or ""), llm_input_tokens=0, llm_output_tokens=0, log_index=None)
                except Exception:
                    pass
                yield f"data: {{\"done\": true, \"response\": {json.dumps(full_reply, ensure_ascii=False)} }}\n\n"
                return
            # 若 regenerate 返回 None，清除 pending 并继续正常流程
            await conv_manager.update_metadata(session_id, category, {"pending_conclusion": None})

        # 2) 无 pending 时：显式完成 或 轮数条件 → 同步检测
        dimension_conclusion = None
        if not meta.get("thread_completed"):
            try:
                explicit_result = bool(
                    user_content and await detect_explicit_completion(phase_step, user_content, conv_history)
                )
            except Exception as e:
                # 显式完成检测是增强能力，不应因上游 LLM 异常中断主对话流。
                logger.exception("detect_explicit_completion failed, continue chat stream: %s", e)
                explicit_result = False
            should_check = _should_run_completion_check(
                user_count, conclusion_shown_at,
                include_explicit=True, explicit_result=explicit_result,
            )
            if should_check:
                try:
                    dimension_conclusion = await check_dimension_complete(phase_step, conv_history, vip_level=vip_level)
                except Exception as e:
                    # 维度收敛检测失败时降级为继续普通对话，避免前端出现 500 卡死。
                    logger.exception("check_dimension_complete failed, continue chat stream: %s", e)
                    dimension_conclusion = None
                if dimension_conclusion:
                    await conv_manager.update_metadata(
                        session_id, category,
                        {"conclusion_shown_at_turn": user_count, "dimension_conclusion": dimension_conclusion},
                    )

        if dimension_conclusion:
            transition_msg = "好的，根据我们的对话，我为你整理出本维度的探索结论，请确认下方摘要是否准确。"
            yield f"data: {{\"chunk\": {json.dumps(transition_msg, ensure_ascii=False)} }}\n\n"
            full_reply = transition_msg
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
            yield f"data: {{\"dimension_conclusion\": {json.dumps(dimension_conclusion, ensure_ascii=False)} }}\n\n"
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
                await AnalyticsService.record_chat_turn(session_id=logical_session_id, dimension=phase_step, user_input_chars=len(user_content or ""), llm_input_tokens=0, llm_output_tokens=0, log_index=None)
            except Exception:
                pass
            yield f"data: {{\"done\": true, \"response\": {json.dumps(full_reply, ensure_ascii=False)} }}\n\n"
            return

        try:
            sem = _get_llm_semaphore()
            stream_coro = llm.chat_stream(llm_messages, temperature=0.7)
            if sem:
                async with sem:
                    async for chunk in stream_coro:
                        if not chunk:
                            continue
                        full_reply += chunk
                        yield f"data: {{\"chunk\": {json.dumps(chunk, ensure_ascii=False)} }}\n\n"
            else:
                async for chunk in stream_coro:
                    if not chunk:
                        continue
                    full_reply += chunk
                    yield f"data: {{\"chunk\": {json.dumps(chunk, ensure_ascii=False)} }}\n\n"
        except Exception as e:
            err = str(e)
            yield f"data: {{\"error\": {json.dumps(err, ensure_ascii=False)} }}\n\n"
            return
        stream_usage = _normalize_token_usage(getattr(llm, "_last_stream_usage", None))

        # 保存完整助手回复
        if full_reply:
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
                    "token_usage": stream_usage,
                },
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

        # 3) 本轮结束前再做一次同步检测（兜底）：若判定完成，必须当轮弹出答题卡
        post_turn_conclusion = None
        try:
            conv_data_after_reply = await conv_manager.get_conversation_data(session_id, category)
            meta_after_reply = conv_data_after_reply.get("metadata", {})
            if not meta_after_reply.get("thread_completed"):
                user_count_after_reply = sum(
                    1 for m in conv_data_after_reply.get("messages", []) if m.get("role") == "user"
                )
                shown_at_after_reply = meta_after_reply.get("conclusion_shown_at_turn")
                should_check_after_reply = (
                    _should_run_completion_check(user_count_after_reply, shown_at_after_reply)
                    or _assistant_indicates_completion(full_reply)
                )
                if should_check_after_reply:
                    conv_history_after_reply = [
                        {"role": m.get("role", "user"), "content": m.get("content", "")}
                        for m in conv_data_after_reply.get("messages", [])
                    ]
                    post_turn_conclusion = await check_dimension_complete(
                        phase_step, conv_history_after_reply, vip_level=vip_level
                    )
                    if post_turn_conclusion:
                        await conv_manager.update_metadata(
                            session_id,
                            category,
                            {
                                "conclusion_shown_at_turn": user_count_after_reply,
                                "dimension_conclusion": post_turn_conclusion,
                                "pending_conclusion": None,
                            },
                        )
                        transition_msg = "好的，根据我们的对话，我为你整理出本维度的探索结论，请确认下方摘要是否准确。"
                        await conv_manager.append_message(
                            session_id=session_id,
                            category=category,
                            message={
                                "role": "assistant",
                                "content": transition_msg,
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
                                "content": json.dumps(post_turn_conclusion, ensure_ascii=False),
                                "session_id": logical_session_id,
                                "step_id": phase_step,
                                "agent_id": "coach",
                                "event": "dimension_conclusion",
                                "card_type": "dimension_conclusion",
                                "card_payload": post_turn_conclusion,
                            },
                        )
                        yield f"data: {{\"chunk\": {json.dumps(transition_msg, ensure_ascii=False)} }}\n\n"
                        yield f"data: {{\"dimension_conclusion\": {json.dumps(post_turn_conclusion, ensure_ascii=False)} }}\n\n"
                        _trigger_anchor_refiner(
                            session_id,
                            phase_step,
                            category,
                            conv_manager,
                            storage_root,
                            dimension_conclusion=post_turn_conclusion,
                            vip_level=vip_level,
                        )
        except Exception:
            post_turn_conclusion = None

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

        # 4) 后台异步检测：仅在本轮未产出结论卡时，更新 pending_conclusion 判定
        async def _background_completion_check() -> None:
            try:
                if post_turn_conclusion:
                    return
                conv_data = await conv_manager.get_conversation_data(session_id, category)
                meta = conv_data.get("metadata", {})
                if meta.get("thread_completed"):
                    return
                user_count = sum(1 for m in conv_data.get("messages", []) if m.get("role") == "user")
                conclusion_shown_at = meta.get("conclusion_shown_at_turn")
                if not _should_run_completion_check(user_count, conclusion_shown_at):
                    return
                conv_history = [
                    {"role": m.get("role", "user"), "content": m.get("content", "")}
                    for m in conv_data.get("messages", [])
                ]
                conclusion = await check_dimension_complete(phase_step, conv_history, vip_level=vip_level)
                if conclusion:
                    await conv_manager.update_metadata(
                        session_id, category, {"pending_conclusion": conclusion}
                    )
                else:
                    await conv_manager.update_metadata(
                        session_id, category, {"pending_conclusion": None}
                    )
            except Exception:
                pass

        asyncio.create_task(_background_completion_check())

        # 埋点：记录对话轮次
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

