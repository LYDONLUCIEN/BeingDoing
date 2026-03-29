"""
report 注册表（目录版）

结构：
data/simple/reports/{report_id}/
  - record.json                       # report 元信息 + 每个 step 的会话池 + 最终选中
  - {step_id}__{session_id}.json      # 该 step 下某个会话的完整消息
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.utils.simple_activation_manager import get_simple_base_dir


STEP_IDS = ["values", "strengths", "interests", "purpose", "rumination"]
STEP_ORDER = {k: i for i, k in enumerate(STEP_IDS)}

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
        rec.setdefault("report_id", report_id)  # 确保旧格式 record 也有 report_id
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

    def _iter_records(self) -> List[dict]:
        items: List[dict] = []
        if not self.reports_root.is_dir():
            return items
        for d in self.reports_root.iterdir():
            if not d.is_dir():
                continue
            rec = self._load_record(d.name)
            if rec:
                items.append(rec)
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return items

    def ensure_report(self, activation_code: str, user_id: str, session_id: Optional[str] = None) -> dict:
        code = (activation_code or "").strip().upper()
        uid = (user_id or "").strip()
        if not code or not uid:
            raise ValueError("activation_code 与 user_id 不能为空")

        existed = self.get_by_activation_user(code, uid)
        if existed:
            if session_id:
                self.bind_session(existed["report_id"], "values", session_id)
            return existed

        report_id = str(uuid.uuid4())
        record = self._default_record(report_id=report_id, activation_code=code, user_id=uid)
        self._save_record(record)
        if session_id:
            self.bind_session(report_id, "values", session_id)
        return self._load_record(report_id) or record

    def get_by_activation_user(self, activation_code: str, user_id: str) -> Optional[dict]:
        code = (activation_code or "").strip().upper()
        uid = (user_id or "").strip()
        for rec in self._iter_records():
            if (rec.get("activation_code") or "").upper() == code and rec.get("user_id") == uid:
                return rec
        return None

    def bind_session(self, report_id: str, step_id: str, session_id: str) -> Optional[dict]:
        sid = self.normalize_step_id(step_id)
        sess = (session_id or "").strip()
        if not sess:
            return None
        record = self._load_record(report_id)
        if not record:
            return None
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
        if sess not in step["session_ids"]:
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
