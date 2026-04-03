"""
report 注册表（目录版）

结构：
data/simple/reports/{report_id}/
  - record.json                       # report 元信息 + 每个 step 的会话池 + 最终选中
  - {step_id}__{session_id}.json      # 该 step 下某个会话的完整消息

同一 (activation_code, user_id) 在同一 reports_root 下仅保留一份目录：
ensure_report 在文件锁内双检，多余目录按 canonical 规则保留一份后 rmtree 其余。

bind_session / select_session 禁止将同一会话 ID 绑定到「不同激活码+用户」的两份 report（同对重复目录除外；admin_mock 豁免）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from filelock import FileLock as _FileLock
except ImportError:  # 精简 venv 时仍可跑通（如仅跑部分测试）
    _FileLock = None  # type: ignore[misc, assignment]

from app.utils.simple_activation_manager import get_simple_base_dir

logger = logging.getLogger(__name__)


class _FcntlPairLock:
    """POSIX 文件锁后备（无 filelock 包时使用）。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fp = None

    def __enter__(self) -> "_FcntlPairLock":
        import fcntl

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self._path, "a", encoding="utf-8")
        fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *args: object) -> None:
        import fcntl

        if self._fp is not None:
            try:
                fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
            finally:
                self._fp.close()
                self._fp = None


def _pair_file_lock(lock_path: Path):
    if _FileLock is not None:
        return _FileLock(str(lock_path), timeout=30)
    if sys.platform == "win32":
        raise ImportError("请安装 filelock 依赖（Windows 上 report 锁需要）")
    return _FcntlPairLock(lock_path)


STEP_IDS = ["values", "strengths", "interests", "purpose", "rumination"]
STEP_ORDER = {k: i for i, k in enumerate(STEP_IDS)}

# Admin mock 等多 report 共用的占位会话（与 admin_mock.MOCK_SESSION_ID 一致）
_SESSION_ID_CROSS_REPORT_EXEMPT = frozenset({"admin_mock"})


def compute_explore_resume(record: dict) -> dict:
    """
    根据 record.json 推断用户应回到的「当前未完成阶段」及可访问阶段列表。
    规则：按顺序找到第一个未 lock 的 step；之前（含当前）的 step 均视为已解锁可回看。
    若全部 lock，则回到最后一步（沉淀），由前端或报告页收口。
    """
    steps = record.get("steps") or {}
    unlocked: List[str] = []
    for sid in STEP_IDS:
        unlocked.append(sid)
        st = steps.get(sid) or {}
        if not st.get("locked"):
            return {"resume_phase": sid, "unlocked_phases": unlocked}
    return {"resume_phase": STEP_IDS[-1], "unlocked_phases": list(STEP_IDS)}


STEP_ALIASES = {
    "values": "values",
    "value": "values",
    "strength": "strengths",
    "strengths": "strengths",
    "interest": "interests",
    "interests": "interests",
    "purpose": "purpose",
    "rumination": "rumination",
    "combine": "rumination",
    "combination": "rumination",
    "filter": "rumination",
    "refinement": "rumination",
}


class ReportRegistry:
    def __init__(self, base_dir: Optional[str] = None):
        self.simple_base_dir = Path(base_dir) if base_dir else get_simple_base_dir()
        self.simple_base_dir.mkdir(parents=True, exist_ok=True)
        self.reports_root = self.simple_base_dir / "reports"
        self.reports_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def normalize_step_id(step_id: str) -> str:
        return STEP_ALIASES.get((step_id or "").strip().lower(), "values")

    def _report_dir(self, report_id: str) -> Path:
        return self.reports_root / report_id

    def _record_file(self, report_id: str) -> Path:
        return self._report_dir(report_id) / "record.json"

    def _step_session_file(self, report_id: str, step_id: str, session_id: str) -> Path:
        return self._report_dir(report_id) / f"{step_id}__{session_id}.json"

    def _locks_dir(self) -> Path:
        p = self.reports_root / ".locks"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _pair_lock_path(self, activation_code: str, user_id: str) -> Path:
        raw = f"{activation_code}|{user_id}".encode("utf-8")
        h = hashlib.sha256(raw).hexdigest()
        return self._locks_dir() / f"report_{h}.lock"

    def _default_record(self, report_id: str, activation_code: str, user_id: str, created_at: Optional[str] = None) -> dict:
        ts = created_at or self._now_iso()
        return {
            "report_id": report_id,
            "activation_code": activation_code,
            "user_id": user_id,
            "created_at": ts,
            "updated_at": ts,
            "status": "in_progress",
            "final_conclusion": None,
            "steps": {
                sid: {
                    "step_id": sid,
                    "selected_session_id": None,
                    "locked": False,
                    "session_ids": [],
                    "updated_at": ts,
                }
                for sid in STEP_IDS
            },
        }

    def _load_record(self, report_id: str) -> Optional[dict]:
        file = self._record_file(report_id)
        if not file.is_file():
            return None
        try:
            data = json.loads(file.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        rec = self._normalize_record(data)
        rec.setdefault("report_id", report_id)
        return rec

    def _normalize_record(self, data: dict) -> dict:
        steps = data.setdefault("steps", {})
        now = self._now_iso()
        for sid in STEP_IDS:
            step = steps.setdefault(
                sid,
                {
                    "step_id": sid,
                    "selected_session_id": None,
                    "locked": False,
                    "session_ids": [],
                    "updated_at": now,
                },
            )
            step.setdefault("step_id", sid)
            step.setdefault("selected_session_id", None)
            step.setdefault("locked", False)
            step.setdefault("session_ids", [])
            step.setdefault("updated_at", now)
        data.setdefault("status", "in_progress")
        data.setdefault("final_conclusion", None)
        data.setdefault("updated_at", now)
        return data

    def _save_record(self, record: dict) -> None:
        report_id = record.get("report_id")
        if not report_id:
            raise ValueError("record 缺少 report_id")
        report_dir = self._report_dir(report_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        record["updated_at"] = self._now_iso()
        file = self._record_file(report_id)
        file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _iter_records_raw(self) -> List[dict]:
        items: List[dict] = []
        if not self.reports_root.is_dir():
            return items
        for d in self.reports_root.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            rec = self._load_record(d.name)
            if rec:
                items.append(rec)
        return items

    @staticmethod
    def _total_session_ids(record: dict) -> int:
        steps = record.get("steps") or {}
        n = 0
        for sid in STEP_IDS:
            n += len((steps.get(sid) or {}).get("session_ids") or [])
        return n

    def _iter_records(self) -> List[dict]:
        items = self._iter_records_raw()
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return items

    def _matches_activation_user(self, code: str, uid: str) -> List[dict]:
        matches: List[dict] = []
        for rec in self._iter_records_raw():
            if (rec.get("activation_code") or "").upper() == code and rec.get("user_id") == uid:
                matches.append(rec)
        return matches

    def _sort_canonical_matches(self, matches: List[dict]) -> List[dict]:
        if len(matches) <= 1:
            return matches
        ids = [m.get("report_id") for m in matches]
        logger.warning(
            "同一激活码与用户存在多份 report 目录，将固定选用一份: activation_code=%s user_id=%s report_ids=%s",
            matches[0].get("activation_code"),
            matches[0].get("user_id"),
            ids,
        )
        return sorted(
            matches,
            key=lambda r: (
                r.get("created_at") or "9999-12-31T23:59:59.999999Z",
                -self._total_session_ids(r),
                r.get("report_id") or "",
            ),
        )

    def _prune_duplicate_dirs(self, ordered: List[dict]) -> None:
        if len(ordered) <= 1:
            return
        keep_id = (ordered[0].get("report_id") or "").strip()
        for rec in ordered[1:]:
            rid = (rec.get("report_id") or "").strip()
            if not rid or rid == keep_id:
                continue
            d = self._report_dir(rid)
            if d.is_dir():
                logger.error(
                    "删除重复 report 目录: removed_report_id=%s kept_report_id=%s",
                    rid,
                    keep_id,
                )
                shutil.rmtree(d, ignore_errors=True)

    def _session_bound_to_other_activation(
        self, session_id: str, except_report_id: str, same_code: str, same_uid: str
    ) -> Optional[str]:
        """若 session 已出现在「另一组 activation+user」的 report 中，返回对方 report_id。"""
        sess = (session_id or "").strip()
        if not sess or sess in _SESSION_ID_CROSS_REPORT_EXEMPT:
            return None
        ex = (except_report_id or "").strip()
        for rec in self._iter_records_raw():
            rid = (rec.get("report_id") or "").strip()
            if not rid or rid == ex:
                continue
            ocode = (rec.get("activation_code") or "").upper()
            ouid = rec.get("user_id") or ""
            if ocode == same_code and ouid == same_uid:
                continue
            for sid in STEP_IDS:
                sessions = ((rec.get("steps") or {}).get(sid) or {}).get("session_ids") or []
                if sess in sessions:
                    logger.warning(
                        "session_id 已绑定到其他探索报告: session_id=%s other_report_id=%s",
                        sess,
                        rid,
                    )
                    return rid
        return None

    def ensure_report(self, activation_code: str, user_id: str, session_id: Optional[str] = None) -> dict:
        code = (activation_code or "").strip().upper()
        uid = (user_id or "").strip()
        if not code or not uid:
            raise ValueError("activation_code 与 user_id 不能为空")

        lock = _pair_file_lock(self._pair_lock_path(code, uid))
        with lock:
            matches = self._matches_activation_user(code, uid)
            if len(matches) > 1:
                ordered = self._sort_canonical_matches(matches)
                self._prune_duplicate_dirs(ordered)
                matches = self._matches_activation_user(code, uid)

            if matches:
                ordered = self._sort_canonical_matches(matches)
                record = ordered[0]
                rid = record.get("report_id")
                if not rid:
                    raise ValueError("record 缺少 report_id")
                if session_id:
                    self.bind_session(rid, "values", session_id)
                return self._load_record(rid) or record

            report_id = str(uuid.uuid4())
            record = self._default_record(report_id=report_id, activation_code=code, user_id=uid)
            self._save_record(record)
            if session_id:
                self.bind_session(report_id, "values", session_id)
            return self._load_record(report_id) or record

    def get_by_activation_user(self, activation_code: str, user_id: str) -> Optional[dict]:
        code = (activation_code or "").strip().upper()
        uid = (user_id or "").strip()
        matches = self._matches_activation_user(code, uid)
        if not matches:
            return None
        ordered = self._sort_canonical_matches(matches)
        return ordered[0]

    def bind_session(self, report_id: str, step_id: str, session_id: str) -> Optional[dict]:
        sid = self.normalize_step_id(step_id)
        sess = (session_id or "").strip()
        if not sess:
            return None
        record = self._load_record(report_id)
        if not record:
            return None
        code = (record.get("activation_code") or "").upper()
        uid = record.get("user_id") or ""
        conflict = self._session_bound_to_other_activation(sess, report_id, code, uid)
        if conflict:
            raise ValueError(
                f"会话 {sess} 已绑定到其他探索报告（report_id={conflict}），拒绝重复绑定"
            )
        step = record["steps"][sid]
        if sess not in step["session_ids"]:
            step["session_ids"].append(sess)
        step["updated_at"] = self._now_iso()
        self._save_record(record)
        return record

    def remove_session(self, report_id: str, step_id: str, session_id: str) -> Optional[dict]:
        sid = self.normalize_step_id(step_id)
        sess = (session_id or "").strip()
        if not sess:
            return None
        record = self._load_record(report_id)
        if not record:
            return None
        step = record["steps"][sid]
        sessions = [s for s in (step.get("session_ids") or []) if s != sess]
        step["session_ids"] = sessions
        if (step.get("selected_session_id") or "") == sess:
            step["selected_session_id"] = sessions[0] if sessions else None
        step["updated_at"] = self._now_iso()
        self._save_record(record)
        return record

    def select_session(self, report_id: str, step_id: str, session_id: str) -> Optional[dict]:
        sid = self.normalize_step_id(step_id)
        sess = (session_id or "").strip()
        record = self._load_record(report_id)
        if not record:
            return None
        step = record["steps"][sid]
        if step.get("locked"):
            selected = step.get("selected_session_id")
            if selected and selected != sess:
                raise ValueError("该阶段已锁定，不能切换会话")
        code = (record.get("activation_code") or "").upper()
        uid = record.get("user_id") or ""
        if sess not in step["session_ids"]:
            conflict = self._session_bound_to_other_activation(sess, report_id, code, uid)
            if conflict:
                raise ValueError(
                    f"会话 {sess} 已绑定到其他探索报告（report_id={conflict}），拒绝选用"
                )
            step["session_ids"].append(sess)
        step["selected_session_id"] = sess
        step["updated_at"] = self._now_iso()
        self._save_record(record)
        return record

    def lock_step(self, report_id: str, step_id: str) -> Optional[dict]:
        sid = self.normalize_step_id(step_id)
        record = self._load_record(report_id)
        if not record:
            return None
        step = record["steps"][sid]
        step["locked"] = True
        step["updated_at"] = self._now_iso()
        self._save_record(record)
        return record

    def lock_previous_step_when_entering(self, report_id: str, current_step: str) -> Optional[dict]:
        sid = self.normalize_step_id(current_step)
        idx = STEP_ORDER.get(sid, 0)
        if idx <= 0:
            return self._load_record(report_id)
        prev = STEP_IDS[idx - 1]
        record = self._load_record(report_id)
        if not record:
            return None
        prev_step = record["steps"][prev]
        selected = prev_step.get("selected_session_id")
        if not selected:
            raise ValueError("请先确认上一阶段的最终对话，再进入下一阶段")
        prev_step["locked"] = True
        prev_step["updated_at"] = self._now_iso()
        self._save_record(record)
        return record

    def get_selected_session(self, report_id: str, step_id: str) -> Optional[str]:
        sid = self.normalize_step_id(step_id)
        record = self._load_record(report_id)
        if not record:
            return None
        return record["steps"][sid].get("selected_session_id")

    def get_report_by_id(self, report_id: str) -> Optional[dict]:
        return self._load_record(report_id)

    def find_report_step_by_session(self, session_id: str) -> Optional[Tuple[dict, str]]:
        sess = (session_id or "").strip()
        if not sess:
            return None
        for report in self._iter_records():
            for step_id in STEP_IDS:
                sessions = ((report.get("steps") or {}).get(step_id) or {}).get("session_ids") or []
                if sess in sessions:
                    return report, step_id
        return None

    def get_step_session_file(self, report_id: str, step_id: str, session_id: str) -> Path:
        return self._step_session_file(report_id, self.normalize_step_id(step_id), session_id)

    def update_step_anchor_summary(self, report_id: str, step_id: str, anchor: dict) -> bool:
        """更新指定阶段的锚点摘要"""
        sid = self.normalize_step_id(step_id)
        if sid not in STEP_IDS or sid == "rumination":
            return False
        record = self._load_record(report_id)
        if not record:
            return False
        step = record["steps"][sid]
        step["anchor_summary"] = anchor
        step["anchor_updated_at"] = self._now_iso()
        self._save_record(record)
        return True

    def list_reports(self) -> List[dict]:
        return self._iter_records()
