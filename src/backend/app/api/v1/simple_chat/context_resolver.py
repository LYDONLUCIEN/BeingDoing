"""
上下文解析：激活码校验、报告初始化、线程选择、权限检查。
"""
import json
import logging
import uuid
from typing import Optional

from fastapi import HTTPException, status

from app.config.settings import settings
from app.api.v1.auth import _is_debug_admin
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    ActivationStatus,
    bind_session_id_for_ensure_report,
    get_effective_simple_root,
    get_activation_with_manager,
)
from app.utils.sandbox_fork import assert_sandbox_not_expired
from app.utils.conversation_file_manager import ConversationFileManager
from app.utils.report_registry import ReportRegistry
from app.utils.admin_policy import is_admin_debug_policy_enabled
from app.utils.admin_prompt_lab import resolve_simple_chat_prompt_override
from app.utils.admin_policy import is_admin_sandbox_enabled
from app.utils.super_admin import is_super_admin_user
from app.utils.activation_audit import (
    append_activation_audit,
    EVENT_OWNER_DENIED,
    EVENT_OWNER_VERIFIED,
)
from app.utils.survey_storage import (
    load_basic_info_by_user,
    load_basic_info,
    format_basic_info_for_prompt,
    load_prior_context_for_report,
    load_prior_context,
)
from app.utils.id_codec import IDCodec

logger = logging.getLogger(__name__)


def storage_category(phase: str, session_id: str) -> str:
    """存储用 category：每个 step-session 一份文件。"""
    return IDCodec.storage_category(phase, session_id)


def step_session_message_count(
    registry: ReportRegistry, report_id: str, phase_step: str, sid: str
) -> int:
    """某 step 下 thread 对话文件中的消息条数。"""
    if not sid or not report_id:
        return 0
    path = registry.get_step_session_file(report_id, phase_step, sid)
    if not path.is_file():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        data = IDCodec.normalize_conversation_data_on_read(raw, report_id)
        return len(data.get("messages") or [])
    except (OSError, json.JSONDecodeError, TypeError):
        return 0


def resolve_default_logical_thread_id(
    registry: ReportRegistry,
    report: dict,
    phase_step: str,
    thread_id: Optional[str],
    activation_storage_session_id: str,
) -> str:
    """
    解析当前阶段使用的对话线程 id。
    策略：显式 thread_id → selected_session_id → 消息数最多的文件
    → 非 activation_storage_session_id 的候选 → 新建 thread_id。
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
        # session_ids 为空时不 fallback 到 act_sid，避免已删线程从残留文件复活
        return ""
    best_sid = None
    best_n = -1
    for sid in candidates:
        n = step_session_message_count(registry, rid, phase_step, sid)
        if n > best_n:
            best_n = n
            best_sid = sid
    if best_n > 0 and best_sid:
        return best_sid
    non_act = [s for s in candidates if s != act_sid]
    if non_act:
        return non_act[0]
    return f"t_{uuid.uuid4().hex}"


def resolve_activation_for_user(
    manager: SimpleActivationManager,
    activation_code: str,
    current_user: dict,
):
    """激活码访问控制：首次使用绑定用户，后续仅归属用户可访问。"""
    rec = manager.get_activation(activation_code)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="激活码不存在")
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
                "endpoint": "context_resolver.resolve_activation_for_user",
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该激活码已被其他用户使用")
    if rec.status in {ActivationStatus.REVOKED, ActivationStatus.DELETED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="激活码不可用")
    if not rec.owner_user_id and not rec.owner_email:
        rec = manager.claim_owner(rec.code, current_user)
    else:
        # 审计日志：归属校验通过
        append_activation_audit(
            EVENT_OWNER_VERIFIED,
            activation_code,
            actor_user_id=uid,
            actor_email=email,
            detail={"endpoint": "context_resolver.resolve_activation_for_user"},
        )
    try:
        assert_sandbox_not_expired(rec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return rec


def resolve_report_context(
    manager: SimpleActivationManager,
    activation_code: str,
    current_user: dict,
    phase: str,
    thread_id: Optional[str] = None,
):
    """统一解析：activation -> report -> step-session 存储上下文。"""
    rec = resolve_activation_for_user(manager, activation_code, current_user)
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

    try:
        phase_step = ReportRegistry.resolve_simple_chat_phase(phase)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    logical_session_id = resolve_default_logical_thread_id(
        registry,
        report,
        phase_step,
        thread_id,
        IDCodec.activation_session_id_from_rec(rec),
    )

    if not can_bypass_flow_limits(current_user, rec):
        try:
            registry.lock_previous_step_when_entering(report["report_id"], phase_step)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if logical_session_id:
        registry.bind_session(report["report_id"], phase_step, logical_session_id)
    category = storage_category(phase_step, logical_session_id)
    conv_manager = ConversationFileManager(base_dir=str(root / "reports"))
    return rec, report, phase_step, logical_session_id, category, conv_manager


def skip_expired_for_debug(rec, user: Optional[dict]) -> bool:
    """Debug 管理员可跳过过期检查"""
    return (
        getattr(settings, "DEBUG_MODE", False)
        and _is_debug_admin(user)
        and rec.status == ActivationStatus.EXPIRED
    )


def can_bypass_flow_limits(current_user: Optional[dict], rec) -> bool:
    """管理员调试豁免（受统一 policy 开关控制）。"""
    if not is_admin_debug_policy_enabled():
        return False
    if not is_super_admin_user(current_user):
        return False
    workspace_kind = (getattr(rec, "workspace_kind", None) or "").strip().lower()
    if workspace_kind in {"fork", "resident"}:
        return True
    return bool(getattr(rec, "is_sandbox", False))


def resolve_prompt_lab_override_for_request(rec, current_user: Optional[dict]) -> Optional[dict]:
    """sandbox_only：仅 super_admin + 调试工作区 + policy 开启时生效。"""
    if not is_admin_sandbox_enabled():
        return None
    if not is_super_admin_user(current_user):
        return None
    workspace_kind = (getattr(rec, "workspace_kind", None) or "").strip().lower()
    is_workspace = workspace_kind in {"fork", "resident"} or bool(getattr(rec, "is_sandbox", False))
    if not is_workspace:
        return None
    resolved = resolve_simple_chat_prompt_override(getattr(rec, "code", ""))
    if not resolved:
        return None
    template, extra_goal_hint, meta = resolved
    return {"template": template, "extra_goal_hint": extra_goal_hint, "meta": meta}


def get_user_id_from_activation(rec) -> Optional[str]:
    """从激活码记录解析 user_id"""
    uid = (getattr(rec, "owner_user_id", None) or "").strip()
    if uid:
        return uid
    email = (getattr(rec, "owner_email", None) or "").strip()
    if email:
        return email
    return None


def load_basic_info_from_activation(activation_code: str) -> str:
    """根据激活码加载 basic_info，格式化为提示词用文本"""
    _manager, rec = get_activation_with_manager(activation_code)
    if not rec:
        return "暂无"
    user_id = get_user_id_from_activation(rec)
    if user_id:
        data = load_basic_info_by_user(user_id)
        if data:
            return format_basic_info_for_prompt(data)
    base = str(get_effective_simple_root(rec))
    data = load_basic_info(IDCodec.activation_session_id_from_rec(rec), base)
    return format_basic_info_for_prompt(data)


def load_prior_context_from_activation(
    activation_code: str, phase: str, report: Optional[dict] = None
) -> str:
    """根据激活码和阶段加载上一轮咨询结果"""
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


def is_step_locked(registry: ReportRegistry, report_id: str, phase_step: str) -> bool:
    record = registry.get_report_by_id(report_id) or {}
    step = ((record.get("steps") or {}).get(phase_step)) or {}
    return bool(step.get("locked", False))


def assert_step_editable(
    *,
    registry: ReportRegistry,
    report_id: str,
    phase_step: str,
    current_user: Optional[dict],
    rec,
) -> None:
    if can_bypass_flow_limits(current_user, rec):
        return
    if is_step_locked(registry, report_id, phase_step):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该阶段已提交并锁定，不能再修改，请继续下一阶段",
        )

