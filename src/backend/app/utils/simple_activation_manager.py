"""
简单激活码管理器（不依赖数据库，使用文件持久化）

用于「简单对话模式」：
- 通过激活码识别一个简单会话
- 每个激活码对应一个 session_id，用于对话文件管理
- 记录创建时间 / 过期时间 / 模式（values / strengths / interests / combined）

注意：
- 激活码过期后，历史文件仍然保留在 data/simple 下
- activations.json 只作为索引，方便通过 code 找到 session_id 等元信息
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, List
import shutil


class ActivationStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DELETED = "deleted"


@dataclass
class ActivationRecord:
    code: str
    session_id: str
    mode: str
    created_at: str
    expires_at: str
    last_activity_at: str
    status: str = ActivationStatus.ACTIVE
    owner_user_id: Optional[str] = None
    owner_email: Optional[str] = None
    claimed_at: Optional[str] = None
    deleted_at: Optional[str] = None
    purge_after: Optional[str] = None
    source: Optional[str] = None
    vip_level: int = 1  # 1=DeepSeek, 2=Kimi/Qwen
    # 管理员调试沙箱：独立存储于 data/simple/sandboxes/{fork_id}/
    is_sandbox: bool = False
    sandbox_root: Optional[str] = None  # 相对 data/simple，如 sandboxes/uuid
    fork_id: Optional[str] = None
    forked_from_code: Optional[str] = None
    forked_at: Optional[str] = None
    forked_by_user_id: Optional[str] = None
    sandbox_expires_at: Optional[str] = None
    # 通用工作区字段（兼容后续 admin 常驻工作区）
    workspace_kind: Optional[str] = None  # fork | resident
    workspace_root: Optional[str] = None  # 相对 data/simple，如 admin_workspaces/{admin_user_id}


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
    """使用项目根目录下的 data/simple，避免依赖当前工作目录。供激活码、对话、调研等统一使用。"""
    project_root = Path(__file__).resolve().parents[4]
    return project_root / "data" / "simple"


def get_effective_simple_root(rec: Optional["ActivationRecord"] = None) -> Path:
    """
    正式激活码使用 data/simple；沙箱激活码使用 data/simple/sandboxes/{fork_id}/。
    """
    base = get_simple_base_dir()
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

    沙箱 Fork 已从源端完整克隆 record.json（含各 step 的 session_ids），不应再把
    「问卷/附属目录用」的 rec.session_id 追加进 values，否则会污染克隆状态。
    """
    if rec is None:
        return None
    if getattr(rec, "is_sandbox", False):
        return None
    sid = (rec.session_id or "").strip()
    return sid or None


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
        return datetime.utcnow().isoformat() + "Z"

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
    ) -> ActivationRecord:
        """
        创建一个新的激活会话

        Returns:
            ActivationRecord
        """
        records = self._load_all()

        # 简单生成一个 10 位激活码（大写字母+数字）
        import random
        import string

        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choices(alphabet, k=10))
            if code not in records:
                break

        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=ttl_minutes)

        record = ActivationRecord(
            code=code,
            session_id=session_id,
            mode=mode,
            created_at=now.isoformat() + "Z",
            expires_at=expires_at.isoformat() + "Z",
            last_activity_at=now.isoformat() + "Z",
            status=ActivationStatus.ACTIVE,
            vip_level=1,
        )
        records[code] = record
        self._save_all(records)
        return record

    def create_activation_batch(self, mode: str, ttl_minutes: int = 60, count: int = 1) -> List[ActivationRecord]:
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

        # 自动标记状态为 expired（但不删除）
        try:
            expires_dt = datetime.fromisoformat(rec.expires_at.replace("Z", ""))
        except ValueError:
            return rec
        if rec.status == ActivationStatus.ACTIVE and datetime.utcnow() > expires_dt:
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
        now = datetime.utcnow().isoformat() + "Z"
        rec.last_activity_at = now
        records[norm or code] = rec
        self._save_all(records)

    def update_status(self, codes: List[str], status: str) -> int:
        """批量更新状态（active / expired / revoked）"""
        status = (status or "").strip().lower()
        if status not in {
            ActivationStatus.ACTIVE.value,
            ActivationStatus.EXPIRED.value,
            ActivationStatus.REVOKED.value,
            ActivationStatus.DELETED.value,
        }:
            raise ValueError("不支持的状态")
        records = self._load_all()
        changed = 0
        for raw in codes or []:
            code = (raw or "").strip().upper()
            rec = records.get(code)
            if not rec:
                continue
            if rec.status == status:
                continue
            rec.status = status
            if status == ActivationStatus.DELETED.value:
                rec.deleted_at = self._now_iso()
            records[code] = rec
            changed += 1
        if changed:
            self._save_all(records)
        return changed

    def claim_owner(self, code: str, user: dict) -> ActivationRecord:
        """首次绑定激活码归属到当前用户。"""
        norm = (code or "").strip().upper()
        records = self._load_all()
        rec = records.get(norm) or records.get(code)
        if not rec:
            raise ValueError("激活码不存在")

        now = datetime.utcnow().isoformat() + "Z"
        rec.owner_user_id = (user or {}).get("user_id")
        rec.owner_email = (user or {}).get("email")
        rec.claimed_at = rec.claimed_at or now
        rec.last_activity_at = now
        records[norm or code] = rec
        self._save_all(records)
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

    def soft_delete_to_recycle_bin(self, codes: List[str], deleted_by: Optional[dict] = None, retention_days: int = 30) -> int:
        """
        删除激活码到垃圾桶（软删除）：
        - 从 activations.json 移除
        - 写入 activations_recycle_bin.json
        """
        records = self._load_all()
        recycle = self._load_recycle_bin()
        now = datetime.utcnow()
        deleted_at = now.isoformat() + "Z"
        purge_after = (now + timedelta(days=retention_days)).isoformat() + "Z"
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

        if changed:
            self._save_all(records)
            self._save_recycle_bin(recycle)
        return changed

    def list_recycle_bin(self) -> Dict[str, ActivationRecycleRecord]:
        return self._load_recycle_bin()

    def restore_from_recycle_bin(self, codes: List[str]) -> int:
        """从垃圾桶恢复到 activations.json"""
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
        if changed:
            self._save_all(records)
            self._save_recycle_bin(recycle)
        return changed

    def permanent_delete_from_recycle_bin(
        self, codes: List[str], reports_root: Optional[Path] = None
    ) -> int:
        """
        从垃圾桶立即永久删除指定激活码及其所有相关数据：
        - report 目录
        - flat session 目录
        - 从 activations 和 recycle 移除
        """
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
        now = now or datetime.utcnow()
        to_delete_codes: List[str] = []

        for code, rec in recycle.items():
            try:
                purge_dt = datetime.fromisoformat(rec.purge_after.replace("Z", ""))
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
            code = ((row.get("activation_code") or "").strip().upper())
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

