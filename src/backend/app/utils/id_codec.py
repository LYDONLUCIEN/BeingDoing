"""
ID field codec for backward-compatible read/write.

This module centralizes compatibility logic for:
- report_id
- thread_id
- activation_session_id (legacy alias: session_id)
"""

from typing import Any, Dict, Optional


class IDCodec:
    """Static helpers to avoid scattered legacy field checks."""

    @staticmethod
    def read_activation_session_id(payload: Any, fallback: Optional[str] = None) -> Optional[str]:
        """Read explicit activation_session_id only (no legacy session_id fallback).

        Generic payloads often use legacy ``session_id`` for *thread* semantics; treating it as
        activation would be wrong.
        """
        if isinstance(payload, dict):
            v = payload.get("activation_session_id")
            if isinstance(v, str) and v.strip():
                return v.strip()
        return fallback

    @staticmethod
    def read_activation_session_id_from_activation_record(payload: Any) -> Optional[str]:
        """activation.json / ActivationRecord style: legacy ``session_id`` means activation storage."""
        if isinstance(payload, dict):
            v = payload.get("activation_session_id")
            if isinstance(v, str) and v.strip():
                return v.strip()
            legacy = payload.get("session_id")
            if isinstance(legacy, str) and legacy.strip():
                return legacy.strip()
        return None

    @staticmethod
    def read_thread_id(payload: Any, fallback: Optional[str] = None) -> Optional[str]:
        if isinstance(payload, dict):
            v = payload.get("thread_id")
            if isinstance(v, str) and v.strip():
                return v.strip()
            legacy = payload.get("session_id")
            if isinstance(legacy, str) and legacy.strip():
                return legacy.strip()
        return fallback

    @staticmethod
    def build_message_ids(
        thread_id: Optional[str],
        activation_session_id: Optional[str],
        include_legacy: bool = True,
    ) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if thread_id:
            out["thread_id"] = thread_id
            if include_legacy:
                # Keep legacy key for old readers; semantics are thread_id in message context.
                out["session_id"] = thread_id
        if activation_session_id:
            out["activation_session_id"] = activation_session_id
        return out

    @staticmethod
    def build_activation_response_ids(
        activation_session_id: Optional[str],
        include_legacy: bool = True,
    ) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if activation_session_id:
            out["activation_session_id"] = activation_session_id
            if include_legacy:
                out["session_id"] = activation_session_id
        return out

    @staticmethod
    def build_activation_client_view(rec: Any, logical_thread_id: str) -> Dict[str, Any]:
        """Nested ``activation`` object in simple-chat API responses.

        Historically ``activation.session_id`` carried the *thread* id (misnamed). We keep that
        for backward compatibility and add explicit ``thread_id`` + ``activation_session_id``.
        """
        activation_sid = (getattr(rec, "session_id", None) or "").strip()
        tid = (logical_thread_id or "").strip()
        out: Dict[str, Any] = {
            "activation_code": getattr(rec, "code", "") or "",
            "thread_id": tid,
            "activation_session_id": activation_sid,
            # legacy: many clients read activation.session_id as the current thread id
            "session_id": tid,
            "mode": getattr(rec, "mode", None),
            "created_at": getattr(rec, "created_at", None),
            "expires_at": getattr(rec, "expires_at", None),
            "status": getattr(rec, "status", None),
        }
        return out

    @staticmethod
    def build_history_metadata_ids(
        thread_id: Optional[str],
        activation_session_id: Optional[str],
        include_legacy: bool = True,
    ) -> Dict[str, str]:
        """ID block for history metadata payload."""
        out: Dict[str, str] = {}
        tid = (thread_id or "").strip()
        if tid:
            out["thread_id"] = tid
            if include_legacy:
                out["session_id"] = tid
        aid = (activation_session_id or "").strip()
        if aid:
            out["activation_session_id"] = aid
        return out

    @staticmethod
    def build_thread_ref(thread_id: Optional[str]) -> Dict[str, str]:
        """Small payload helper for note/log API blocks that only carry thread reference."""
        tid = (thread_id or "").strip()
        return {"thread_id": tid} if tid else {}

    @staticmethod
    def build_note_container_root(report_id: str) -> Dict[str, str]:
        """Root keys for ``*__note/note.json`` files (top-level legacy session_id == report_id)."""
        rid = (report_id or "").strip()
        return {"report_id": rid, "session_id": rid}

    @staticmethod
    def activation_session_id_from_rec(rec: Any) -> str:
        """ActivationRecord / rec object: ``session_id`` attribute is activation storage id."""
        return (getattr(rec, "session_id", None) or "").strip()

    @staticmethod
    def storage_category(phase: str, thread_id: str) -> str:
        """File stem category: ``{phase}__{thread_id}`` (simple-chat step session file)."""
        return f"{(phase or '').strip()}__{(thread_id or '').strip()}"

    @staticmethod
    def build_conversation_file_root_ids(report_id: str) -> Dict[str, str]:
        """Top-level keys for ``{report_id}/{phase}__{thread}.json`` conversation files."""
        rid = (report_id or "").strip()
        return {"report_id": rid, "session_id": rid}

    @staticmethod
    def read_report_id_from_conversation_root(data: Any) -> Optional[str]:
        """Conversation JSON root: prefer ``report_id``, else legacy top-level ``session_id`` (= report_id)."""
        if not isinstance(data, dict):
            return None
        v = data.get("report_id")
        if isinstance(v, str) and v.strip():
            return v.strip()
        legacy = data.get("session_id")
        if isinstance(legacy, str) and legacy.strip():
            return legacy.strip()
        return None

    @staticmethod
    def normalize_message_on_read(msg: Any) -> Any:
        """Message row: ensure ``thread_id`` is populated from legacy row ``session_id`` when missing."""
        if not isinstance(msg, dict):
            return msg
        out = dict(msg)
        if not (out.get("thread_id") or "").strip():
            legacy = out.get("session_id")
            if isinstance(legacy, str) and legacy.strip():
                out["thread_id"] = legacy.strip()
        return out

    @staticmethod
    def normalize_conversation_data_on_read(data: Any, fallback_report_id: str) -> Dict[str, Any]:
        """After loading a conversation JSON file: set ``report_id`` on root and normalize messages."""
        if not isinstance(data, dict):
            rid = (fallback_report_id or "").strip()
            return {
                **IDCodec.build_conversation_file_root_ids(rid),
                "category": "",
                "messages": [],
                "metadata": {},
            }
        out = dict(data)
        rid = IDCodec.read_report_id_from_conversation_root(out) or (fallback_report_id or "").strip()
        if rid:
            if not (out.get("report_id") or "").strip():
                out["report_id"] = rid
        msgs = out.get("messages")
        if isinstance(msgs, list):
            out["messages"] = [
                IDCodec.normalize_message_on_read(m) if isinstance(m, dict) else m for m in msgs
            ]
        return out
