"""
LLM per-turn 诊断日志服务

每轮 LLM 调用（首期仅接入主聊天流 simple-chat/message/stream）落一条结构化
JSONL 记录，用于复盘「空回复 / 半截回复 / 断连 / 截断」等异常轮次——
2026-09-21 空回复事故的教训：失败轮的 reasoning_content 原文既没落盘也没日志，
只能从 token 数反推，无法还原模型「想了什么」。

存储：
  data/logs/llm_turns/llm_turns-YYYY-MM-DD.jsonl   （按天分文件，保留期按文件删除）

每条记录字段：
  id / ts(UTC) / user_id / activation_code / session_id / thread_id / phase /
  scene / provider / model / outcome / finish_reason / retry_count /
  usage(prompt/completion/reasoning/cache) / attempts(每次尝试摘要) /
  reasoning_content(思维链全文) / content(正文全文，未剥离协议块)

outcome 分类：
  ok                       — 有可见正文
  length                   — 有正文但 finish_reason=length（被 max_tokens 截断）
  empty_content_retried_ok — 首次空 content，原样重试后成功
  empty_content_failed     — 重试后仍空 content（已给前端 error）
  partial                  — 流式中途异常，已落盘半截回复
  error                    — 流式中途异常，无任何可见输出
  disconnected             — 客户端断开（CancelledError）

敏感性：reasoning_content 含用户经历与系统提示词推理，属敏感原文。
本目录不对公网暴露，查询接口仅 super_admin，超保留期文件由每日 job 删除。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.utils.data_paths import get_llm_turn_logs_dir

logger = logging.getLogger(__name__)

_FILE_PREFIX = "llm_turns-"
_FILE_SUFFIX = ".jsonl"

# outcome 常量
OUTCOME_OK = "ok"
OUTCOME_LENGTH = "length"
OUTCOME_EMPTY_RETRIED_OK = "empty_content_retried_ok"
OUTCOME_EMPTY_FAILED = "empty_content_failed"
OUTCOME_PARTIAL = "partial"
OUTCOME_ERROR = "error"
OUTCOME_DISCONNECTED = "disconnected"

ALL_OUTCOMES = (
    OUTCOME_OK,
    OUTCOME_LENGTH,
    OUTCOME_EMPTY_RETRIED_OK,
    OUTCOME_EMPTY_FAILED,
    OUTCOME_PARTIAL,
    OUTCOME_ERROR,
    OUTCOME_DISCONNECTED,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_for_date(d: date) -> Path:
    return get_llm_turn_logs_dir() / f"{_FILE_PREFIX}{d.isoformat()}{_FILE_SUFFIX}"


def append_turn_log(entry: Dict[str, Any]) -> None:
    """追加一条 per-turn 日志（尽力而为，绝不阻断主流程）。

    调用方传入业务字段；id/ts 在此补全（调用方已给则尊重）。
    """
    try:
        record = dict(entry)
        record.setdefault("id", uuid.uuid4().hex)
        record.setdefault("ts", _now_iso())
        p = _file_for_date(datetime.now(timezone.utc).date())
        p.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        logger.exception("写入 LLM turn 日志失败")
    except Exception:
        # 序列化等任何异常都不允许影响主流程
        logger.exception("LLM turn 日志记录异常")


def _iter_files_desc(start: Optional[date], end: Optional[date]) -> List[Path]:
    """按日期倒序列出涉及的日志文件（新→旧）。"""
    log_dir = get_llm_turn_logs_dir()
    if not log_dir.is_dir():
        return []
    files: List[Path] = []
    for p in log_dir.glob(f"{_FILE_PREFIX}*{_FILE_SUFFIX}"):
        try:
            d = date.fromisoformat(p.name[len(_FILE_PREFIX):-len(_FILE_SUFFIX)])
        except ValueError:
            continue
        if start and d < start:
            continue
        if end and d > end:
            continue
        files.append(p)
    files.sort(key=lambda p: p.name, reverse=True)
    return files


def _match(entry: Dict[str, Any], *, activation_code: str, session_id: str,
           outcome: str, user_id: str) -> bool:
    if activation_code and (entry.get("activation_code") or "").upper() != activation_code:
        return False
    if session_id and session_id not in (
        str(entry.get("session_id") or ""),
        str(entry.get("thread_id") or ""),
    ):
        return False
    if outcome and entry.get("outcome") != outcome:
        return False
    if user_id and str(entry.get("user_id") or "") != user_id:
        return False
    return True


def _summarize(entry: Dict[str, Any]) -> Dict[str, Any]:
    """列表视图：截断全文字段为摘要，避免列表接口返回过大。"""
    item = {k: v for k, v in entry.items() if k not in ("reasoning_content", "content")}
    rc = entry.get("reasoning_content") or ""
    cc = entry.get("content") or ""
    item["reasoning_chars"] = len(rc)
    item["content_chars"] = len(cc)
    item["content_preview"] = cc[:120]
    return item


def query_turn_logs(
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
    activation_code: Optional[str] = None,
    session_id: Optional[str] = None,
    outcome: Optional[str] = None,
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    """分页查询 turn 日志（时间倒序，列表为摘要视图）。"""
    code = (activation_code or "").strip().upper()
    sid = (session_id or "").strip()
    oc = (outcome or "").strip()
    uid = (user_id or "").strip()

    matched: List[Dict[str, Any]] = []
    for p in _iter_files_desc(start, end):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _match(entry, activation_code=code, session_id=sid, outcome=oc, user_id=uid):
                matched.append(entry)

    total = len(matched)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    s = (page - 1) * page_size
    items = [_summarize(e) for e in matched[s:s + page_size]]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def get_turn_detail(log_id: str) -> Optional[Dict[str, Any]]:
    """按 id 取单条全文（含 reasoning_content / content）。"""
    log_id = (log_id or "").strip()
    if not log_id:
        return None
    for p in _iter_files_desc(None, None):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("id") == log_id:
                return entry
    return None


def cleanup_expired_logs(retention_days: int) -> int:
    """删除超出保留期的日志文件，返回删除数量。"""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
    removed = 0
    for p in _iter_files_desc(None, None):
        try:
            d = date.fromisoformat(p.name[len(_FILE_PREFIX):-len(_FILE_SUFFIX)])
        except ValueError:
            continue
        if d < cutoff:
            try:
                p.unlink()
                removed += 1
            except OSError:
                logger.exception("删除过期 LLM turn 日志失败: %s", p)
    if removed:
        logger.info("LLM turn 日志保留期清理：删除 %d 个文件（保留 %d 天）", removed, retention_days)
    return removed
