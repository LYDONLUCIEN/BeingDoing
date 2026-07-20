"""
简单激活码管理器（不依赖数据库，使用文件持久化）

用于「简单对话模式」：
- 通过激活码识别一个简单会话
- 每个激活码对应一个 session_id，用于对话文件管理
- 记录创建时间 / 过期时间 / 模式（values / strengths / interests / combined）

注意：
- 激活码过期后，历史文件仍然保留在 data/simple 下
- activations.json 只作为索引，方便通过 code 找到 session_id 等元信息

产品策略（探索 report）：
- 用户一旦开始探索并生成 report 目录后，终端用户不得自助删除激活码及关联报告数据。
- soft_delete / permanent_delete / 回收站永久删除 仅供管理员、系统任务或运维脚本调用；
  调用时传入 caller_role='end_user' 将显式拒绝。默认 caller_role='admin' 以保持脚本与现有行为兼容。
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
import logging
from typing import Dict, List, Optional, Tuple

from app.utils.helpers import parse_iso_to_utc


logger = logging.getLogger(__name__)


class ActivationStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DELETED = "deleted"


# 允许执行「软删/回收站永久删」等破坏探索数据的调用方角色（默认走 admin，兼容历史脚本）
_ACTIVATION_DELETE_CALLER_ROLES = frozenset({"admin", "system", "script", "migration"})


def assert_activation_delete_caller_allowed(caller_role: str) -> None:
    """
    终端用户不得删除已生成的探索 report 及激活索引。
    管理员/系统/脚本应使用 admin、system、script 或 migration。
    """
    role = (caller_role or "").strip().lower()
    if role in _ACTIVATION_DELETE_CALLER_ROLES:
        return
    if role == "end_user":
        raise PermissionError(
            "产品策略：终端用户不可删除已生成的探索报告及激活数据，请联系管理员。"
        )
    raise PermissionError(f"不允许的激活数据删除调用角色: {caller_role!r}")


@dataclass
class ActivationRecord:
    code: str
    session_id: str
    mode: str
    created_at: str
    expires_at: Optional[str]  # None = 不过期（试用码）
    last_activity_at: str
    activation_session_id: Optional[str] = None
    status: str = ActivationStatus.ACTIVE
    owner_user_id: Optional[str] = None
    owner_email: Optional[str] = None
    claimed_at: Optional[str] = None
    deleted_at: Optional[str] = None
    purge_after: Optional[str] = None
    source: Optional[str] = None
    vip_level: int = 1  # 1=DeepSeek, 2=Kimi/Qwen
    # 管理员调试沙箱：独立存储于 data/test/simple/sandboxes/{fork_id}/
    is_sandbox: bool = False
    sandbox_root: Optional[str] = None  # 相对 data/test/simple，如 sandboxes/uuid
    fork_id: Optional[str] = None
    forked_from_code: Optional[str] = None
    forked_at: Optional[str] = None
    forked_by_user_id: Optional[str] = None
    sandbox_expires_at: Optional[str] = None
    # 通用工作区字段（兼容后续 admin 常驻工作区）
    workspace_kind: Optional[str] = None  # fork | resident
    workspace_root: Optional[str] = (
        None  # 相对 data/test/simple，如 admin_workspaces/{admin_user_id}
    )
    # activation_code -> report_id 快速索引（权威仍以 reports/{report_id}/record.json 为准）
    report_id: Optional[str] = None
    report_index_updated_at: Optional[str] = None
    # ── 套餐与试用体系（ADR-0008；存量码一律 code_type=full）──
    code_type: str = "full"  # trial | full
    package_type: Optional[str] = None  # None | quarterly | annual（决定延期价格档）
    source_order_id: Optional[str] = None  # 交付来源订单（赠品码/升级追溯）
    purchaser_user_id: Optional[str] = None  # 所属人（购买者）；激活人看 owner_user_id
    report_authorized: bool = False  # 激活人一键授权报告给所属人


@dataclass
class ActivationRecycleRecord:
    activation_code: str
    session_id: str
    mode: str
    original_record: dict
    deleted_at: str
    purge_after: str
    deleted_by_user_id: Optional[str] = None
    deleted_by_email: Optional[str] = None


def get_simple_base_dir() -> Path:
    """生产业务数据根目录（真实用户数据）。"""
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "data" / "simple"


def get_simple_test_base_dir() -> Path:
    """测试/调试数据根目录（admin sandbox/workspace/replay）。"""
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "data" / "test" / "simple"


def _looks_like_debug_activation_code(code: Optional[str]) -> bool:
    c = (code or "").strip().upper()
    return c.startswith("SBX") or c.startswith("ADM")


def is_debug_workspace_record(rec: Optional["ActivationRecord"]) -> bool:
    if rec is None:
        return False
    if bool(getattr(rec, "is_sandbox", False)):
        return True
    kind = (getattr(rec, "workspace_kind", None) or "").strip().lower()
    if kind in {"fork", "resident"}:
        return True
    return _looks_like_debug_activation_code(getattr(rec, "code", None))


def get_activation_manager_for_code(code: Optional[str]) -> "SimpleActivationManager":
    """
    按激活码前缀选择索引：
    - SBX/ADM 默认走 test 根
    - 其他走 prod 根
    """
    if _looks_like_debug_activation_code(code):
        return SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    return SimpleActivationManager(base_dir=str(get_simple_base_dir()))


def get_activation_with_manager(
    code: str,
) -> Tuple["SimpleActivationManager", Optional["ActivationRecord"]]:
    """
    兼容双根读取：
    - 若前缀看起来是 debug code，优先 test 后回退 prod
    - 否则优先 prod 后回退 test（兼容迁移期）
    """
    c = (code or "").strip().upper()
    prod_mgr = SimpleActivationManager(base_dir=str(get_simple_base_dir()))
    test_mgr = SimpleActivationManager(base_dir=str(get_simple_test_base_dir()))
    if _looks_like_debug_activation_code(c):
        rec = test_mgr.get_activation(c)
        if rec:
            return test_mgr, rec
        return prod_mgr, prod_mgr.get_activation(c)
    rec = prod_mgr.get_activation(c)
    if rec:
        return prod_mgr, rec
    return test_mgr, test_mgr.get_activation(c)


def get_effective_simple_root(rec: Optional["ActivationRecord"] = None) -> Path:
    """
    解析激活码记录对应的数据根：
    - 业务激活码：data/simple
    - 调试激活码（SBX/ADM/fork/resident）：data/test/simple
    """
    base = get_simple_test_base_dir() if is_debug_workspace_record(rec) else get_simple_base_dir()
    if rec is not None and getattr(rec, "workspace_root", None):
        root = (base / rec.workspace_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    if rec is not None and getattr(rec, "is_sandbox", False) and rec.sandbox_root:
        root = (base / rec.sandbox_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    return base


def bind_session_id_for_ensure_report(rec: Optional["ActivationRecord"]) -> Optional[str]:
    """
    供 ReportRegistry.ensure_report(..., session_id=...) 使用。

    新版严格语义下，activation_session_id 仅用于激活码级别的附属数据命名空间，
    不再注入到步骤会话池（steps.*.session_ids）中，避免与 thread_id 混用。
    """
    return None


def _default_base_dir() -> Path:
    return get_simple_base_dir()


class SimpleActivationManager:
    """简单激活码会话管理器（文件存储实现）"""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir) if base_dir else _default_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._activations_file = self.base_dir / "activations.json"
        self._recycle_file = self.base_dir / "activations_recycle_bin.json"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        """
        解析 ISO8601 字符串为 offset-aware UTC datetime。

        实际逻辑委托给 :func:`app.utils.helpers.parse_iso_to_utc`，
        兼容 ``Z`` 后缀 / 显式 offset / naive 历史字符串三类格式；
        naive 统一按 UTC 解释，不回写磁盘。
        """
        return parse_iso_to_utc(value)

    def _load_all(self) -> Dict[str, ActivationRecord]:
        if not self._activations_file.exists():
            return {}
        try:
            content = self._activations_file.read_text(encoding="utf-8")
            raw = json.loads(content or "{}")
        except (json.JSONDecodeError, OSError):
            raw = {}
        records: Dict[str, ActivationRecord] = {}
        for code, data in raw.items():
            try:
                data = dict(data)
                # strict IDs: activation_session_id is canonical; keep legacy session_id persisted for now.
                activation_sid = data.get("activation_session_id")
                session_sid = data.get("session_id")
                if not activation_sid and session_sid:
                    data["activation_session_id"] = session_sid
                if not session_sid and activation_sid:
                    data["session_id"] = activation_sid
                data.setdefault("vip_level", 1)
                data.setdefault("is_sandbox", False)
                data.setdefault("sandbox_root", None)
                data.setdefault("fork_id", None)
                data.setdefault("forked_from_code", None)
                data.setdefault("forked_at", None)
                data.setdefault("forked_by_user_id", None)
                data.setdefault("sandbox_expires_at", None)
                data.setdefault("workspace_kind", None)
                data.setdefault("workspace_root", None)
                data.setdefault("report_id", None)
                data.setdefault("report_index_updated_at", None)
                # 套餐与试用体系：存量记录一律视为完整码（ADR-0008）
                data.setdefault("code_type", "full")
                data.setdefault("package_type", None)
                data.setdefault("source_order_id", None)
                data.setdefault("purchaser_user_id", None)
                data.setdefault("report_authorized", False)
                records[code] = ActivationRecord(**data)
            except (TypeError, ValueError):
                continue
        return records

    def _save_all(self, records: Dict[str, ActivationRecord]) -> None:
        serializable = {code: asdict(rec) for code, rec in records.items()}
        self._activations_file.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_recycle_bin(self) -> Dict[str, ActivationRecycleRecord]:
        if not self._recycle_file.exists():
            return {}
        try:
            content = self._recycle_file.read_text(encoding="utf-8")
            raw = json.loads(content or "{}")
        except (json.JSONDecodeError, OSError):
            raw = {}
        records: Dict[str, ActivationRecycleRecord] = {}
        for code, data in raw.items():
            try:
                records[code] = ActivationRecycleRecord(**data)
            except TypeError:
                continue
        return records

    def _save_recycle_bin(self, records: Dict[str, ActivationRecycleRecord]) -> None:
        serializable = {code: asdict(rec) for code, rec in records.items()}
        self._recycle_file.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list_activations(self) -> Dict[str, ActivationRecord]:
        """
        返回所有激活码记录（仅后端 Admin 使用）。
        注意：不会自动删除过期记录，status 字段中包含 active / expired / revoked。
        """
        return self._load_all()

    def create_activation(
        self,
        mode: str,
        ttl_minutes: int = 60,
        code_type: str = "full",
        vip_level: Optional[int] = None,
        package_type: Optional[str] = None,
        no_expiry: bool = False,
    ) -> ActivationRecord:
        """
        创建一个新的激活会话

        Args:
            mode: 模式（values / strengths / interests / combined）
            ttl_minutes: 有效期（分钟）；code_type=trial 或 no_expiry=True 时忽略
            code_type: trial（试用码，不过期，默认 vip_level=1）| full（完整码）
            vip_level: LLM 档位；缺省时 trial=1，full 保持历史默认 1
            package_type: 套餐类型（quarterly | annual），决定延期价格档与赠品码有效期时长
            no_expiry: True 时 expires_at=None（赠品码首次激活时才落有效期）

        Returns:
            ActivationRecord
        """
        records = self._load_all()
        code_type = (code_type or "full").strip().lower()
        if code_type not in {"trial", "full"}:
            raise ValueError(f"不支持的 code_type: {code_type}")
        package_type = (package_type or "").strip().lower() or None
        if package_type not in {None, "quarterly", "annual"}:
            raise ValueError(f"不支持的 package_type: {package_type}")

        # 简单生成一个 10 位激活码（大写字母+数字）
        import random
        import string

        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choices(alphabet, k=10))
            if code not in records:
                break

        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        if code_type == "trial" or no_expiry:
            # 不过期：试用码永久；赠品码首次激活（claim）时才落有效期
            expires_at_iso: Optional[str] = None
        else:
            expires_at_iso = (now + timedelta(minutes=ttl_minutes)).isoformat()

        record = ActivationRecord(
            code=code,
            session_id=session_id,
            activation_session_id=session_id,
            mode=mode,
            created_at=now.isoformat(),
            expires_at=expires_at_iso,
            last_activity_at=now.isoformat(),
            status=ActivationStatus.ACTIVE,
            vip_level=int(vip_level) if vip_level is not None else 1,
            code_type=code_type,
            package_type=package_type,
        )
        records[code] = record
        self._save_all(records)
        return record

    def create_activation_batch(
        self, mode: str, ttl_minutes: int = 60, count: int = 1
    ) -> List[ActivationRecord]:
        count = max(1, min(int(count), 500))
        created: List[ActivationRecord] = []
        for _ in range(count):
            created.append(self.create_activation(mode=mode, ttl_minutes=ttl_minutes))
        return created

    def get_activation(self, code: str) -> Optional[ActivationRecord]:
        """根据激活码获取记录（不会自动删除过期记录）。
        查找时自动 trim 并转为大写（生成的码为大写），方便用户输入。"""
        if not code or not isinstance(code, str):
            return None
        raw = code.strip()
        if not raw:
            return None
        # 激活码生成时为大写+数字，查找时统一转大写
        normalized = raw.upper()
        records = self._load_all()
        rec = records.get(normalized) or records.get(raw)
        if not rec:
            return None

        # 不过期码（试用码，expires_at=None）直接返回
        if not rec.expires_at:
            return rec
        # 自动标记状态为 expired（但不删除）
        try:
            expires_dt = self._parse_dt(rec.expires_at)
        except (ValueError, TypeError):
            return rec
        if rec.status == ActivationStatus.ACTIVE and datetime.now(timezone.utc) > expires_dt:
            rec.status = ActivationStatus.EXPIRED
            records[normalized] = rec
            self._save_all(records)
        return rec

    def touch_activity(self, code: str) -> None:
        """更新最后活跃时间（仅在 ACTIVE 时更新）"""
        records = self._load_all()
        norm = (code or "").strip().upper()
        rec = records.get(norm) or records.get(code)
        if not rec:
            return
        if rec.status != ActivationStatus.ACTIVE:
            return
        now = datetime.now(timezone.utc).isoformat()
        rec.last_activity_at = now
        records[norm or code] = rec
        self._save_all(records)

    def update_status(self, codes: List[str], status: str, actor: Optional[dict] = None) -> int:
        """批量更新状态（active / expired / revoked），记录审计日志。"""
        status = (status or "").strip().lower()
        if status not in {
            ActivationStatus.ACTIVE.value,
            ActivationStatus.EXPIRED.value,
            ActivationStatus.REVOKED.value,
            ActivationStatus.DELETED.value,
        }:
            raise ValueError("不支持的状态")
        from app.utils.activation_audit import EVENT_STATUS_CHANGED, append_activation_audit

        records = self._load_all()
        changed = 0
        for raw in codes or []:
            code = (raw or "").strip().upper()
            rec = records.get(code)
            if not rec:
                continue
            if rec.status == status:
                continue
            old_status = rec.status
            rec.status = status
            if status == ActivationStatus.DELETED.value:
                rec.deleted_at = self._now_iso()
            records[code] = rec
            changed += 1
            append_activation_audit(
                EVENT_STATUS_CHANGED,
                code,
                actor_user_id=(actor or {}).get("user_id"),
                actor_email=(actor or {}).get("email"),
                detail={"old_status": old_status, "new_status": status},
            )
        if changed:
            self._save_all(records)
        return changed

    def extend_and_activate(
        self,
        codes: List[str],
        extend_days: int,
        actor: Optional[dict] = None,
    ) -> Dict[str, int]:
        """
        批量延期并自动激活：
        - 仅处理 active / expired
        - revoked / deleted 跳过（按产品约束）
        - 新 expires_at = max(now, 原 expires_at) + extend_days
        """
        days = int(extend_days or 0)
        if days <= 0:
            raise ValueError("extend_days 必须大于 0")

        from app.utils.activation_audit import EVENT_EXTENDED, append_activation_audit

        records = self._load_all()
        changed = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        for raw in codes or []:
            code = (raw or "").strip().upper()
            rec = records.get(code)
            if not rec:
                skipped += 1
                continue

            if rec.status in {ActivationStatus.REVOKED.value, ActivationStatus.DELETED.value}:
                skipped += 1
                continue

            try:
                old_expires_dt = self._parse_dt(rec.expires_at) if rec.expires_at else now
            except (ValueError, TypeError):
                old_expires_dt = now

            base_dt = old_expires_dt if old_expires_dt > now else now
            new_expires_dt = base_dt + timedelta(days=days)

            old_status = rec.status
            old_expires = rec.expires_at
            rec.expires_at = new_expires_dt.isoformat()
            rec.status = ActivationStatus.ACTIVE.value
            rec.deleted_at = None
            rec.purge_after = None
            records[code] = rec
            changed += 1

            append_activation_audit(
                EVENT_EXTENDED,
                code,
                actor_user_id=(actor or {}).get("user_id"),
                actor_email=(actor or {}).get("email"),
                detail={
                    "extend_days": days,
                    "old_status": old_status,
                    "new_status": rec.status,
                    "old_expires_at": old_expires,
                    "new_expires_at": rec.expires_at,
                },
            )

        if changed:
            self._save_all(records)
        return {"changed": changed, "skipped": skipped}

    def upgrade_to_full(
        self,
        code: str,
        package_type: str,
        duration_days: int,
        *,
        source_order_id: Optional[str] = None,
        purchaser_user_id: Optional[str] = None,
        actor: Optional[dict] = None,
    ) -> ActivationRecord:
        """试用码付费升级为完整码（ADR-0008）

        - code_type: trial → full；vip_level=2
        - package_type 写入（决定延期价格档）
        - 有效期从付款时刻起算：expires_at = now + duration_days
        - 记录来源订单与所属人（已有值不覆盖）
        """
        norm = (code or "").strip().upper()
        package_type = (package_type or "").strip().lower()
        if package_type not in {"quarterly", "annual"}:
            raise ValueError(f"不支持的 package_type: {package_type}")
        days = int(duration_days or 0)
        if days <= 0:
            raise ValueError("duration_days 必须大于 0")

        records = self._load_all()
        rec = records.get(norm)
        if not rec:
            raise ValueError("激活码不存在")
        if rec.status in {ActivationStatus.REVOKED.value, ActivationStatus.DELETED.value}:
            raise ValueError("激活码已作废或已删除，无法升级")

        now = datetime.now(timezone.utc)
        old_snapshot = {
            "code_type": rec.code_type,
            "vip_level": rec.vip_level,
            "expires_at": rec.expires_at,
        }
        rec.code_type = "full"
        rec.vip_level = 2
        rec.package_type = package_type
        rec.expires_at = (now + timedelta(days=days)).isoformat()
        rec.status = ActivationStatus.ACTIVE.value
        rec.last_activity_at = now.isoformat()
        if source_order_id and not rec.source_order_id:
            rec.source_order_id = source_order_id
        if purchaser_user_id and not rec.purchaser_user_id:
            rec.purchaser_user_id = purchaser_user_id
        records[norm] = rec
        self._save_all(records)

        from app.utils.activation_audit import append_activation_audit

        append_activation_audit(
            "paid_upgraded_to_full",
            norm,
            actor_user_id=(actor or {}).get("user_id"),
            actor_email=(actor or {}).get("email"),
            detail={
                "package_type": package_type,
                "duration_days": days,
                "source_order_id": source_order_id,
                "old": old_snapshot,
                "new_expires_at": rec.expires_at,
            },
        )
        logger.info("激活码付费升级为完整码: code=%s package=%s days=%d", norm, package_type, days)
        return rec

    def extend_validity(
        self,
        code: str,
        days: int,
        *,
        actor: Optional[dict] = None,
    ) -> ActivationRecord:
        """延期激活（ADR-0008）：expires_at = max(当前到期, now) + days

        expires_at=None（未激活的赠品码）时从 now 起算。
        """
        norm = (code or "").strip().upper()
        days = int(days or 0)
        if days <= 0:
            raise ValueError("days 必须大于 0")

        records = self._load_all()
        rec = records.get(norm)
        if not rec:
            raise ValueError("激活码不存在")
        if rec.status in {ActivationStatus.REVOKED.value, ActivationStatus.DELETED.value}:
            raise ValueError("激活码已作废或已删除，无法延期")

        from app.utils.activation_audit import EVENT_EXTENDED, append_activation_audit

        now = datetime.now(timezone.utc)
        try:
            old_expires_dt = self._parse_dt(rec.expires_at) if rec.expires_at else now
        except (ValueError, TypeError):
            old_expires_dt = now
        base_dt = old_expires_dt if old_expires_dt > now else now
        old_expires = rec.expires_at
        rec.expires_at = (base_dt + timedelta(days=days)).isoformat()
        rec.status = ActivationStatus.ACTIVE.value
        rec.last_activity_at = now.isoformat()
        records[norm] = rec
        self._save_all(records)

        append_activation_audit(
            EVENT_EXTENDED,
            norm,
            actor_user_id=(actor or {}).get("user_id"),
            actor_email=(actor or {}).get("email"),
            detail={
                "extend_days": days,
                "renewal": True,
                "old_expires_at": old_expires,
                "new_expires_at": rec.expires_at,
            },
        )
        logger.info("激活码延期激活: code=%s days=%d new_expires=%s", norm, days, rec.expires_at)
        return rec

    def set_purchase_source(
        self,
        code: str,
        *,
        source_order_id: Optional[str] = None,
        purchaser_user_id: Optional[str] = None,
    ) -> ActivationRecord:
        """记录激活码的购买来源（来源订单 + 所属人），供团队分析的购买链路追溯（ADR-0010）"""
        norm = (code or "").strip().upper()
        records = self._load_all()
        rec = records.get(norm)
        if not rec:
            raise ValueError("激活码不存在")
        if source_order_id:
            rec.source_order_id = source_order_id
        if purchaser_user_id:
            rec.purchaser_user_id = purchaser_user_id
        records[norm] = rec
        self._save_all(records)
        return rec

    def set_report_authorized(
        self, code: str, authorized: bool, *, actor: Optional[dict] = None
    ) -> ActivationRecord:
        """激活人一键授权/撤销报告给所属人（ADR-0010：仅授权报告，对话不可分享）"""
        norm = (code or "").strip().upper()
        records = self._load_all()
        rec = records.get(norm)
        if not rec:
            raise ValueError("激活码不存在")
        rec.report_authorized = bool(authorized)
        records[norm] = rec
        self._save_all(records)

        from app.utils.activation_audit import append_activation_audit

        append_activation_audit(
            "report_authorization_changed",
            norm,
            actor_user_id=(actor or {}).get("user_id"),
            actor_email=(actor or {}).get("email"),
            detail={"report_authorized": rec.report_authorized},
        )
        logger.info("报告授权变更: code=%s authorized=%s", norm, rec.report_authorized)
        return rec

    def claim_owner(self, code: str, user: dict) -> ActivationRecord:
        """
        首次绑定激活码归属到当前用户。

        安全策略：原子性读-改-写，内部重新校验归属，防止 TOCTOU 竞态覆盖。
        - 若激活码已有归属者且非当前用户，抛 PermissionError（而非静默覆盖）。
        - 若归属者已一致，仅刷新 last_activity_at（幂等安全）。
        """
        norm = (code or "").strip().upper()
        records = self._load_all()
        rec = records.get(norm) or records.get(code)
        if not rec:
            raise ValueError("激活码不存在")

        uid = (user or {}).get("user_id")
        email = (user or {}).get("email")

        # ---- 归属安全校验：防止竞态覆盖 ----
        if rec.owner_user_id or rec.owner_email:
            # 已有归属者，仅当请求者完全匹配时允许（幂等刷新）
            if rec.owner_user_id and uid != rec.owner_user_id:
                raise PermissionError(
                    f"归属冲突：激活码 {norm} 已被 user_id={rec.owner_user_id} 绑定，"
                    f"当前请求 user_id={uid}"
                )
            if rec.owner_email and email != rec.owner_email:
                raise PermissionError(
                    f"归属冲突：激活码 {norm} 已被 email={rec.owner_email} 绑定，"
                    f"当前请求 email={email}"
                )

        now = datetime.now(timezone.utc).isoformat()
        old_owner_user_id = rec.owner_user_id
        old_owner_email = rec.owner_email
        is_new_claim = not bool(old_owner_user_id or old_owner_email)
        rec.owner_user_id = uid
        rec.owner_email = email
        rec.claimed_at = rec.claimed_at or now
        rec.last_activity_at = now

        # 套餐赠品码：首次激活时落有效期（ADR-0008：赠品码有效期从激活起算）
        if is_new_claim and not rec.expires_at:
            pkg = (getattr(rec, "package_type", None) or "").strip().lower()
            if pkg in {"quarterly", "annual"}:
                from app.config.settings import settings as _settings

                days = (
                    _settings.QUARTERLY_DAYS if pkg == "quarterly" else _settings.ANNUAL_DAYS
                )
                rec.expires_at = (
                    datetime.now(timezone.utc) + timedelta(days=days)
                ).isoformat()

        records[norm or code] = rec
        self._save_all(records)

        # ---- 审计日志：归属变更 ----
        from app.utils.activation_audit import (
            EVENT_OWNER_CLAIMED,
            append_activation_audit,
        )

        append_activation_audit(
            EVENT_OWNER_CLAIMED,
            norm,
            actor_user_id=uid,
            actor_email=email,
            detail={
                "old_owner_user_id": old_owner_user_id,
                "old_owner_email": old_owner_email,
                "new_owner_user_id": uid,
                "new_owner_email": email,
                "is_new_claim": not bool(old_owner_user_id or old_owner_email),
            },
        )

        return rec

    def transfer_owner(
        self,
        code: str,
        new_user_id: str,
        new_email: Optional[str],
        *,
        actor: Optional[dict] = None,
    ) -> "ActivationRecord":
        """
        管理员迁移激活码归属(原子操作)。

        与 claim_owner 的区别:claim_owner 禁止转移已有 owner;transfer_owner 专门用于
        已有 owner 的激活码迁移,且同时改 activations.json 和 canonical report 的 record.json。

        步骤:
            1. 校验激活码存在 + 目标 user_id 非空
            2. 幂等:owner 已是目标用户则直接返回
            3. 原子改 activations.json 的 owner_user_id/owner_email
            4. 同步改 canonical report 的 record.json.user_id(委托 ReportRegistry)
            5. 写审计日志 EVENT_OWNER_TRANSFERRED

        Parameters
        ----------
        code : str
            激活码(自动 trim/upper)。
        new_user_id : str
            新归属者 user_id。
        new_email : Optional[str]
            新归属者 email。
        actor : Optional[dict]
            操作者(管理员),用于审计。{"user_id":..., "email":...}

        Returns
        -------
        ActivationRecord
            迁移后的激活码记录。
        """
        norm = (code or "").strip().upper()
        uid = (new_user_id or "").strip()
        if not norm:
            raise ValueError("激活码不能为空")
        if not uid:
            raise ValueError("new_user_id 不能为空")

        records = self._load_all()
        rec = records.get(norm) or records.get(code)
        if not rec:
            raise ValueError("激活码不存在")

        old_owner_user_id = rec.owner_user_id
        old_owner_email = rec.owner_email

        # 幂等:已是目标 owner
        if old_owner_user_id == uid and (new_email is None or old_owner_email == new_email):
            return rec

        now = datetime.now(timezone.utc).isoformat()
        rec.owner_user_id = uid
        if new_email is not None:
            rec.owner_email = new_email
        rec.claimed_at = rec.claimed_at or now
        rec.last_activity_at = now
        records[norm or code] = rec
        self._save_all(records)

        # 同步 canonical report 的 user_id(失败不阻断归属变更,仅记日志)
        report_id = getattr(rec, "report_id", None)
        if report_id:
            try:
                from app.utils.report_registry import ReportRegistry
                registry = ReportRegistry(base_dir=str(self.base_dir))
                changed = registry.change_report_user_id(
                    report_id=report_id,
                    new_user_id=uid,
                    activation_code=norm,
                )
                if changed is None:
                    logger.warning(
                        "迁移归属:canonical report 不存在,仅改了 activations.json。"
                        "code=%s report_id=%s",
                        norm, report_id,
                    )
            except Exception as e:
                logger.error(
                    "迁移归属:改 record.json user_id 失败(activations.json 已更新)。"
                    "code=%s report_id=%s error=%s",
                    norm, report_id, e,
                )

        # 审计日志
        from app.utils.activation_audit import (
            EVENT_OWNER_TRANSFERRED,
            append_activation_audit,
        )

        actor_uid = (actor or {}).get("user_id") if actor else None
        actor_email = (actor or {}).get("email") if actor else None
        append_activation_audit(
            EVENT_OWNER_TRANSFERRED,
            norm,
            actor_user_id=actor_uid,
            actor_email=actor_email,
            detail={
                "old_owner_user_id": old_owner_user_id,
                "old_owner_email": old_owner_email,
                "new_owner_user_id": uid,
                "new_owner_email": new_email,
                "report_id": report_id,
            },
        )

        return rec

    def is_owner(self, rec: ActivationRecord, user: dict) -> bool:
        """校验当前用户是否为激活码归属者。未绑定时返回 True。"""
        if not rec.owner_user_id and not rec.owner_email:
            return True

        uid = (user or {}).get("user_id")
        email = (user or {}).get("email")
        if rec.owner_user_id and uid == rec.owner_user_id:
            return True
        if rec.owner_email and email == rec.owner_email:
            return True
        return False

    def soft_delete_to_recycle_bin(
        self,
        codes: List[str],
        deleted_by: Optional[dict] = None,
        retention_days: int = 30,
        *,
        caller_role: str = "admin",
    ) -> int:
        """
        删除激活码到垃圾桶（软删除）：
        - 从 activations.json 移除
        - 写入 activations_recycle_bin.json

        产品策略：禁止终端用户删除；caller_role='end_user' 将抛出 PermissionError。
        管理员/脚本请使用默认 caller_role='admin'。
        """
        assert_activation_delete_caller_allowed(caller_role)
        records = self._load_all()
        recycle = self._load_recycle_bin()
        now = datetime.now(timezone.utc)
        deleted_at = now.isoformat()
        purge_after = (now + timedelta(days=retention_days)).isoformat()
        changed = 0

        for raw in codes or []:
            code = (raw or "").strip().upper()
            rec = records.get(code)
            if not rec:
                continue
            # 删除后保留在主记录中，仅状态变更
            rec.status = ActivationStatus.DELETED.value
            rec.deleted_at = deleted_at
            rec.purge_after = purge_after
            records[code] = rec
            recycle[code] = ActivationRecycleRecord(
                activation_code=code,
                session_id=rec.session_id,
                mode=rec.mode,
                original_record=asdict(rec),
                deleted_at=deleted_at,
                purge_after=purge_after,
                deleted_by_user_id=(deleted_by or {}).get("user_id"),
                deleted_by_email=(deleted_by or {}).get("email"),
            )
            changed += 1
            # 审计日志：软删除
            from app.utils.activation_audit import EVENT_SOFT_DELETED, append_activation_audit

            append_activation_audit(
                EVENT_SOFT_DELETED,
                code,
                actor_user_id=(deleted_by or {}).get("user_id"),
                actor_email=(deleted_by or {}).get("email"),
                detail={
                    "owner_user_id": rec.owner_user_id,
                    "owner_email": rec.owner_email,
                    "caller_role": caller_role,
                    "purge_after": purge_after,
                },
            )

        if changed:
            self._save_all(records)
            self._save_recycle_bin(recycle)
        return changed

    def list_recycle_bin(self) -> Dict[str, ActivationRecycleRecord]:
        return self._load_recycle_bin()

    def restore_from_recycle_bin(self, codes: List[str], actor: Optional[dict] = None) -> int:
        """从垃圾桶恢复到 activations.json，记录审计日志。"""
        from app.utils.activation_audit import EVENT_RESTORED, append_activation_audit

        records = self._load_all()
        recycle = self._load_recycle_bin()
        changed = 0
        for raw in codes or []:
            code = (raw or "").strip().upper()
            recycled = recycle.pop(code, None)
            if not recycled:
                continue
            existing = records.get(code)
            if existing:
                rec = existing
            else:
                try:
                    rec = ActivationRecord(**recycled.original_record)
                except TypeError:
                    continue
            rec.status = ActivationStatus.ACTIVE.value
            rec.deleted_at = None
            rec.purge_after = None
            records[code] = rec
            changed += 1
            append_activation_audit(
                EVENT_RESTORED,
                code,
                actor_user_id=(actor or {}).get("user_id"),
                actor_email=(actor or {}).get("email"),
                detail={
                    "owner_user_id": rec.owner_user_id,
                    "owner_email": rec.owner_email,
                    "deleted_at": recycled.deleted_at,
                },
            )
        if changed:
            self._save_all(records)
            self._save_recycle_bin(recycle)
        return changed

    def permanent_delete_from_recycle_bin(
        self,
        codes: List[str],
        reports_root: Optional[Path] = None,
        *,
        caller_role: str = "admin",
        actor: Optional[dict] = None,
    ) -> int:
        """
        从垃圾桶立即永久删除指定激活码及其所有相关数据：
        - report 目录
        - flat session 目录
        - 从 activations 和 recycle 移除

        产品策略：禁止终端用户删除；caller_role='end_user' 将抛出 PermissionError。
        """
        assert_activation_delete_caller_allowed(caller_role)
        import shutil

        recycle = self._load_recycle_bin()
        records = self._load_all()
        root = reports_root if reports_root is not None else (self.base_dir / "reports")
        deleted_count = 0
        for raw in codes or []:
            code = (raw or "").strip().upper()
            rec = recycle.get(code)
            if not rec:
                continue
            if root.is_dir():
                for d in root.iterdir():
                    if not d.is_dir():
                        continue
                    rf = d / "record.json"
                    if not rf.is_file():
                        continue
                    try:
                        rec_data = json.loads(rf.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError, TypeError):
                        continue
                    if (rec_data.get("activation_code") or "").upper() == code:
                        shutil.rmtree(d, ignore_errors=True)
            sess_dir = self.base_dir / rec.session_id
            if rec.session_id and sess_dir.exists() and sess_dir.is_dir():
                shutil.rmtree(sess_dir, ignore_errors=True)
            recycle.pop(code, None)
            records.pop(code, None)
            deleted_count += 1
            # 审计日志：永久删除
            from app.utils.activation_audit import EVENT_PERMANENT_DELETED, append_activation_audit

            append_activation_audit(
                EVENT_PERMANENT_DELETED,
                code,
                actor_user_id=(actor or {}).get("user_id"),
                actor_email=(actor or {}).get("email"),
                detail={
                    "owner_user_id": rec.owner_user_id,
                    "owner_email": rec.owner_email,
                    "caller_role": caller_role,
                },
            )
        if deleted_count:
            self._save_recycle_bin(recycle)
            self._save_all(records)
        return deleted_count

    def purge_recycle_bin(self, now: Optional[datetime] = None) -> int:
        """
        物理清理垃圾桶过期数据：
        - 超过 purge_after 的记录从垃圾桶删除
        - 同时删除 data/simple/{session_id} 对话目录
        """
        recycle = self._load_recycle_bin()
        now = now or datetime.now(timezone.utc)
        to_delete_codes: List[str] = []

        for code, rec in recycle.items():
            try:
                purge_dt = self._parse_dt(rec.purge_after)
            except ValueError:
                continue
            if now >= purge_dt:
                to_delete_codes.append(code)
                session_dir = self.base_dir / rec.session_id
                if session_dir.exists() and session_dir.is_dir():
                    shutil.rmtree(session_dir, ignore_errors=True)

        if not to_delete_codes:
            return 0

        for code in to_delete_codes:
            recycle.pop(code, None)
            # 彻底清理后从主记录移除
            records = self._load_all()
            if code in records:
                records.pop(code, None)
                self._save_all(records)
        self._save_recycle_bin(recycle)
        return len(to_delete_codes)

    def put_activation(self, record: ActivationRecord) -> None:
        """写入或覆盖一条激活码记录（用于沙箱注册等）。"""
        records = self._load_all()
        norm = (record.code or "").strip().upper()
        record = ActivationRecord(**{**asdict(record), "code": norm})
        records[norm] = record
        self._save_all(records)

    def remove_activation_code(self, code: str) -> bool:
        """从 activations.json 永久移除一条记录（不经过回收站）。"""
        records = self._load_all()
        norm = (code or "").strip().upper()
        if norm not in records:
            return False
        del records[norm]
        self._save_all(records)
        return True

    def upsert_from_db_rows(self, rows: List[dict]) -> int:
        """
        从数据库同步激活码记录到 activations.json。
        仅补齐缺失，不覆盖已有字段（避免破坏人工维护状态）。
        """
        records = self._load_all()
        changed = 0
        for row in rows or []:
            code = (row.get("activation_code") or "").strip().upper()
            session_id = (row.get("session_id") or "").strip()
            if not code or not session_id:
                continue
            if code in records:
                continue
            now = self._now_iso()
            records[code] = ActivationRecord(
                code=code,
                session_id=session_id,
                mode=row.get("mode") or "combined",
                created_at=row.get("created_at") or now,
                expires_at=row.get("expires_at") or now,
                last_activity_at=row.get("last_activity_at") or now,
                status=row.get("status") or ActivationStatus.REVOKED.value,
                source="db_sync",
                vip_level=int(row.get("vip_level") or 1),
            )
            changed += 1
        if changed:
            self._save_all(records)
        return changed
