"""
试用激活码（Trial Code）工具（P-A，ADR-0008）

规则口径：
- 试用码：注册即送、自动绑定、不过期（expires_at=None）、vip_level=1，
  仅限 values 阶段问答 10 轮（轮=用户消息条数，排除 internal 消息；
  第 10 条正常回复，第 11 条起拦截）。
- 存量码一律 code_type=full，不受任何试用限制。
- 老用户懒补发：GET /simple-auth/journeys 时名下 0 个可用码则自动发一个试用码并绑定。
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.utils.simple_activation_manager import (
    ActivationRecord,
    ActivationStatus,
    SimpleActivationManager,
    get_simple_base_dir,
    get_simple_test_base_dir,
)

logger = logging.getLogger(__name__)

TRIAL_CODE_TYPE = "trial"
FULL_CODE_TYPE = "full"

# 试用码 values 阶段用户消息上限（第 limit+1 条起拦截）
TRIAL_VALUES_USER_MESSAGE_LIMIT = 10


def is_trial_code(rec: Optional[ActivationRecord]) -> bool:
    """是否试用码。存量记录无 code_type 字段时 _load_all 已 setdefault 为 full。"""
    if rec is None:
        return False
    return (getattr(rec, "code_type", None) or FULL_CODE_TYPE) == TRIAL_CODE_TYPE


def create_trial_activation_for_user(
    user: dict,
    manager: Optional[SimpleActivationManager] = None,
) -> ActivationRecord:
    """
    创建试用码并立即绑定到用户（注册即送）。

    - mode=combined（阶段权限由 code_type 门控，mode 为历史遗留字段）
    - expires_at=None（不过期）、vip_level=1
    """
    mgr = manager or SimpleActivationManager(base_dir=str(get_simple_base_dir()))
    rec = mgr.create_activation(mode="combined", code_type=TRIAL_CODE_TYPE, vip_level=1)
    rec = mgr.claim_owner(rec.code, user or {})
    logger.info(
        "试用激活码已发放并绑定: code=%s user_id=%s",
        rec.code,
        (user or {}).get("user_id"),
    )
    return rec


def list_owned_codes(user_id: str, email: str) -> List[str]:
    """
    列出用户名下（owner 匹配）全部可用激活码（排除 deleted/revoked），
    合并生产与测试/沙箱两个索引根。
    """
    owned: List[str] = []
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for code, rec in mgr.list_activations().items():
            if rec.status in {ActivationStatus.DELETED, ActivationStatus.REVOKED}:
                continue
            if (user_id and rec.owner_user_id == user_id) or (
                email and rec.owner_email == email
            ):
                owned.append((code or "").strip().upper())
    return owned


def ensure_trial_code_for_user(user: dict) -> Optional[ActivationRecord]:
    """
    老用户懒补发：名下 0 个可用码时，自动发一个试用码并绑定。

    防并发重复发：绑定后复查，若并发请求已发了别的码，则回收本次多发的码。

    Returns:
        新发的试用码记录；无需补发（或并发下被回收）时返回 None。
    """
    user_id = ((user or {}).get("user_id") or "").strip()
    email = ((user or {}).get("email") or "").strip()
    if not user_id and not email:
        return None
    if list_owned_codes(user_id, email):
        return None

    mgr = SimpleActivationManager(base_dir=str(get_simple_base_dir()))
    rec = mgr.create_activation(mode="combined", code_type=TRIAL_CODE_TYPE, vip_level=1)
    mgr.claim_owner(rec.code, {"user_id": user_id, "email": email})

    # 复查：并发下另一名请求可能已补发成功，此时回收本次多发的码
    owned_after = list_owned_codes(user_id, email)
    if any(code != rec.code for code in owned_after):
        logger.warning(
            "懒补发并发冲突，回收多发试用码: code=%s user_id=%s", rec.code, user_id
        )
        mgr.remove_activation_code(rec.code)
        return None

    logger.info("老用户懒补发试用激活码: code=%s user_id=%s", rec.code, user_id)
    return mgr.get_activation(rec.code)


def get_active_trial_code_for_user(user_id: str) -> Optional[ActivationRecord]:
    """找用户名下 active 试用码（每人至多一个；ADR-0014 消耗升级的目标）。"""
    user_id = (user_id or "").strip()
    if not user_id:
        return None
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for _code, rec in mgr.list_activations().items():
            if rec.owner_user_id != user_id:
                continue
            if not is_trial_code(rec):
                continue
            if rec.status != ActivationStatus.ACTIVE.value:
                continue
            return rec
    return None


def get_started_trial_code(user_id: str) -> Optional[ActivationRecord]:
    """找用户名下「已开聊」（values 用户消息 ≥1 条）的 active 试用码（ADR-0014 弹窗触发条件）。"""
    from app.utils.report_registry import ReportRegistry

    user_id = (user_id or "").strip()
    if not user_id:
        return None
    for base_dir in (get_simple_base_dir(), get_simple_test_base_dir()):
        mgr = SimpleActivationManager(base_dir=str(base_dir))
        for code, rec in mgr.list_activations().items():
            if rec.owner_user_id != user_id:
                continue
            if not is_trial_code(rec):
                continue
            if rec.status != ActivationStatus.ACTIVE.value:
                continue
            registry = ReportRegistry(base_dir=str(base_dir))
            report = registry.get_by_activation_user(code, user_id) or {}
            report_id = (report.get("report_id") or "").strip()
            if report_id and count_values_user_messages(registry, report_id) >= 1:
                return rec
    return None


def count_values_user_messages(registry, report_id: str) -> int:
    """
    统计该 report 全部 values 线程的用户消息总数（排除 internal 协议消息）。

    用于试用码 10 轮门控：轮 = 用户消息条数。
    """
    rid = (report_id or "").strip()
    if not rid:
        return 0
    report = registry.get_report_by_id(rid)
    if not report:
        return 0
    step = ((report.get("steps") or {}).get("values")) or {}
    total = 0
    for sid in step.get("session_ids") or []:
        sid = str(sid or "").strip()
        if not sid:
            continue
        path = registry.get_step_session_file(rid, "values", sid)
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        for msg in data.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "user" and not msg.get("internal"):
                total += 1
    return total
