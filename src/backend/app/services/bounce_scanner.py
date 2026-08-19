"""
退信扫描服务

职责：
1. 通过 IMAP 连接发件邮箱，扫描最近的退信邮件（DSN, RFC 3464）
2. 解析出失败的收件人地址 + 状态码
3. 判定 hard / soft，UPSERT 到 email_bounces 表
4. 维护 watermark（last_uid），避免重复扫描

设计要点：
- IMAP 用标准库 imaplib（同步） + asyncio.to_thread 包成异步
- 扫描幂等：watermark + UPSERT，失败重跑无副作用
- watermark 丢失时按 lookback_hours 兜底（默认 48h）
- 解析失败的邮件存原文到 data/bounce_unparsed/，待人工补规则
- 不重试：失败记日志，下次 cron 自动追上（lookback 兜底）
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.message import Message
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config.settings import settings
from app.models.database import AsyncSessionLocal
from app.models.email_bounce import EmailBounce

logger = logging.getLogger(__name__)


# 退信候选过滤关键词（From / Subject 命中任一即认为是退信）
BOUNCE_FROM_PATTERNS = [
    r"mailer-daemon",
    r"postmaster",
    r"mail delivery",
    r"delivery status",
    r"noreply.*delivery",
    r"163\.com",  # 163 系统退信
]
BOUNCE_SUBJECT_PATTERNS = [
    r"delivery (status )?notification",
    r"undeliver",
    r"returned mail",
    r"mail delivery fail",
    r"投递失败",
    r"退信",
    r"无法送达",
    r"delivery failure",
]

# RFC 3464 DSN 状态码 → hard / soft 判定
# 5.1.x = user does not exist（hard）
# 5.2.x = mailbox full（soft）
# 5.3.x = message too big / routing（soft）
# 5.4.x = network routing（soft）
# 5.5.x = protocol / invalid address（hard）
# 5.6.x = content rejected（soft）
# 5.7.x = policy / spam block（soft，可申诉）
HARD_STATUS_CODES = {"5.1.0", "5.1.1", "5.1.2", "5.1.3", "5.5.0", "5.5.2", "5.5.4"}
SOFT_STATUS_PREFIXES = ("5.2.", "5.3.", "5.4.", "5.6.", "5.7.")


class BounceScanner:
    """退信扫描器

    用法：
        result = await BounceScanner.scan_once()
        # result: {"scanned": int, "parsed": int, "added": int, "failed": int}
    """

    # 状态文件路径（存 last_uid watermark）
    STATE_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "data",
        "bounce_scan_state.json",
    )
    # 解析失败邮件存档目录
    UNPARSED_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "data",
        "bounce_unparsed",
    )

    # ─── 对外主入口 ──────────────────────────────────────────

    @classmethod
    async def scan_once(cls) -> Dict[str, Any]:
        """扫描一次，返回结果统计

        Returns:
            {
                "scanned": 检查的邮件数,
                "candidates": 命中退信候选的邮件数,
                "parsed": 成功解析的 DSN 数,
                "added": 新增/更新到 email_bounces 的邮箱数,
                "unparsed": 解析失败存档的邮件数,
                "last_uid": 本次扫描到的最大 UID,
                "error": 错误信息（无错误为 None）
            }
        """
        imap_cfg = cls._resolve_imap_config()
        if not imap_cfg["host"] or not imap_cfg["user"] or not imap_cfg["pass"]:
            return {
                "scanned": 0,
                "candidates": 0,
                "parsed": 0,
                "added": 0,
                "unparsed": 0,
                "last_uid": None,
                "error": "IMAP 未配置：请设置 BOUNCE_IMAP_HOST/USER/PASS（或复用 SMTP_*）",
            }

        try:
            result = await cls._do_scan(imap_cfg)
            logger.info("bounce scan done: %s", result)
            return result
        except Exception as e:
            logger.exception("bounce scan failed: %s", e)
            return {
                "scanned": 0,
                "candidates": 0,
                "parsed": 0,
                "added": 0,
                "unparsed": 0,
                "last_uid": None,
                "error": f"{type(e).__name__}: {e}",
            }

    # ─── 内部实现 ──────────────────────────────────────────

    @staticmethod
    def _resolve_imap_config() -> Dict[str, Any]:
        """合并 BOUNCE_IMAP_* 和 SMTP_* 的配置（前者优先）"""
        return {
            "host": settings.BOUNCE_IMAP_HOST,
            "port": int(settings.BOUNCE_IMAP_PORT or 993),
            "user": settings.BOUNCE_IMAP_USER or settings.SMTP_USER,
            "pass": settings.BOUNCE_IMAP_PASS or settings.SMTP_PASS,
        }

    @classmethod
    async def _do_scan(cls, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """同步 IMAP 操作包到 to_thread"""
        return await cls._run_in_thread(cls._sync_scan, cfg)

    @staticmethod
    def _run_in_thread(func, *args):
        import asyncio

        return asyncio.to_thread(func, *args)

    @classmethod
    def _sync_scan(cls, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """同步扫描（在 worker thread 里执行）

        流程：
        1. 连接 IMAP，选 INBOX
        2. 计算 last_uid + lookback 时间，构造搜索条件
        3. 拉取候选邮件，逐封解析 DSN
        4. UPSERT email_bounces
        5. 更新 watermark
        """
        last_uid = cls._load_watermark()
        lookback_date = (
            datetime.now() - timedelta(hours=settings.BOUNCE_SCAN_LOOKBACK_HOURS)
        ).strftime("%d-%b-%Y")

        conn = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
        try:
            conn.login(cfg["user"], cfg["pass"])
            # 163/126 等网易邮箱要求登录后先发送 IMAP ID（RFC 2971）自报家门，
            # 否则 select 被拒："Unsafe Login. Please contact kefu@188.com for help"
            imaplib.Commands["ID"] = ("AUTH",)
            conn._simple_command(
                "ID", '("name" "openlife-bounce-scanner" "version" "1.0")'
            )
            conn.select("INBOX")

            # 搜索条件：日期 >= lookback AND UID > last_uid
            # imaplib 的 search 不直接支持 UID 复合，先用 date 搜，代码层再过滤 UID
            typ, data = conn.search(None, f'(SINCE "{lookback_date}")')
            if typ != "OK":
                return {
                    "scanned": 0,
                    "candidates": 0,
                    "parsed": 0,
                    "added": 0,
                    "unparsed": 0,
                    "last_uid": last_uid,
                    "error": f"IMAP search failed: {typ}",
                }

            all_uids = [u for u in data[0].split() if u]
            # 过滤已扫描过的 UID
            new_uids = [int(u) for u in all_uids if int(u) > last_uid] if last_uid else [int(u) for u in all_uids]

            scanned = 0
            candidates = 0
            parsed = 0
            added = 0
            unparsed = 0
            max_uid = last_uid or 0

            for uid in new_uids:
                scanned += 1
                typ, msg_data = conn.fetch(str(uid).encode(), "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)

                # 退信候选过滤
                if not cls._is_bounce_candidate(msg):
                    max_uid = max(max_uid, uid)
                    continue
                candidates += 1

                # 解析 DSN
                recipients = cls._parse_dsn(msg)
                if not recipients:
                    unparsed += 1
                    cls._save_unparsed(uid, msg, raw)
                    max_uid = max(max_uid, uid)
                    continue
                parsed += len(recipients)

                # UPSERT 到数据库（同步版本，包在调用线程里跑同步 SQLAlchemy）
                added_count = cls._upsert_recipients_sync(recipients)
                added += added_count

                max_uid = max(max_uid, uid)

            # 更新 watermark
            if max_uid > (last_uid or 0):
                cls._save_watermark(max_uid)

            return {
                "scanned": scanned,
                "candidates": candidates,
                "parsed": parsed,
                "added": added,
                "unparsed": unparsed,
                "last_uid": max_uid,
                "error": None,
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass
            try:
                conn.logout()
            except Exception:
                pass

    # ─── 退信候选识别 ──────────────────────────────────────

    @classmethod
    def _is_bounce_candidate(cls, msg: Message) -> bool:
        """根据 From / Subject / Content-Type 判断是否是退信邮件"""
        from_hdr = (msg.get("From", "") or "").lower()
        subject_hdr = (msg.get("Subject", "") or "").lower()
        ct = (msg.get("Content-Type", "") or "").lower()

        # multipart/report; report-type=delivery-status 是标准 DSN 标志
        if "report-type=delivery-status" in ct or "multipart/report" in ct:
            return True

        # From 命中
        if any(re.search(p, from_hdr) for p in BOUNCE_FROM_PATTERNS):
            return True

        # Subject 命中
        if any(re.search(p, subject_hdr) for p in BOUNCE_SUBJECT_PATTERNS):
            return True

        return False

    # ─── DSN 解析（RFC 3464） ──────────────────────────────

    @classmethod
    def _parse_dsn(cls, msg: Message) -> List[Dict[str, Any]]:
        """解析 DSN 报告，返回 [{email, status_code, reason}, ...]

        RFC 3464 结构（multipart/report）：
        - Part 1: human-readable 说明
        - Part 2: delivery-status（含 Final-Recipient / Status / Diagnostic-Code）
        - Part 3: 原邮件或邮件头

        非 multipart 的退信（如某些服务商自定义格式）尝试从正文里正则提取。
        """
        results: List[Dict[str, Any]] = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = (part.get_content_type() or "").lower()
                if "delivery-status" in ct:
                    results.extend(cls._parse_delivery_status_part(part))
        else:
            # 非 multipart，尝试从纯文本正文里 regex 提取
            try:
                body = cls._get_text_body(msg)
                results.extend(cls._parse_text_body(body))
            except Exception:
                pass

        return results

    @classmethod
    def _parse_delivery_status_part(cls, part: Message) -> List[Dict[str, Any]]:
        """解析 delivery-status 部分，里面有一个或多个 per-recipient 状态块"""
        results: List[Dict[str, Any]] = []
        try:
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            else:
                text = str(payload)
        except Exception:
            return results

        # delivery-status 由空行分隔的多个块，每块包含 Final-Recipient / Status / Diagnostic-Code
        # 按空行切分块
        blocks = re.split(r"\n\s*\n", text)
        current_email: Optional[str] = None
        current_status: Optional[str] = None
        current_diag: Optional[str] = None

        for block in blocks:
            # 提取 Final-Recipient
            m = re.search(
                r"Final-Recipient:\s*(?:rfc822\s*;)?\s*([^\s\n]+)",
                block,
                re.IGNORECASE,
            )
            if m:
                # 如果上一个块已有 email，先 flush
                if current_email:
                    results.append(
                        cls._make_recipient_dict(current_email, current_status, current_diag)
                    )
                current_email = m.group(1).strip().lower()
                # 同块继续找 status
                sm = re.search(r"Status:\s*([0-9.]+)", block, re.IGNORECASE)
                current_status = sm.group(1).strip() if sm else None
                dm = re.search(r"Diagnostic-Code:\s*(.+?)(?:\n\s*\n|$)", block, re.IGNORECASE | re.DOTALL)
                current_diag = dm.group(1).strip() if dm else None
            else:
                # 没有 Final-Recipient 的块，可能是补充 Diagnostic-Code
                if current_email and not current_diag:
                    dm = re.search(r"Diagnostic-Code:\s*(.+?)(?:\n\s*\n|$)", block, re.IGNORECASE | re.DOTALL)
                    if dm:
                        current_diag = dm.group(1).strip()

        # flush 最后一个
        if current_email:
            results.append(
                cls._make_recipient_dict(current_email, current_status, current_diag)
            )

        return results

    @staticmethod
    def _make_recipient_dict(
        email_addr: str, status: Optional[str], diag: Optional[str]
    ) -> Dict[str, Any]:
        return {
            "email": email_addr.lower().strip(),
            "status_code": status,
            "reason": diag or status or None,
        }

    @classmethod
    def _parse_text_body(cls, body: str) -> List[Dict[str, Any]]:
        """非 DSN 格式的退信（如 163 自定义格式），从纯文本里正则提取邮箱"""
        results: List[Dict[str, Any]] = []
        if not body:
            return results

        # 启发式：找 "收件人：xxx@xxx" 或 "Original-Recipient" 或直接搜邮箱前后有失败关键词
        # 优先匹配中文常见 163 退信格式："收件人地址：xxx@xxx.com"
        patterns = [
            r"收件人[地址:：\s]+([\w.+-]+@[\w.-]+)",
            r"Original-Recipient:\s*rfc822\s*;\s*([\w.+-]+@[\w.-]+)",
            r"Final-Recipient:\s*rffc?822\s*;\s*([\w.+-]+@[\w.-]+)",
            r"无法发送到[地址:：\s]*([\w.+-]+@[\w.-]+)",
            r"不存在[的邮箱]*[：:\s]+([\w.+-]+@[\w.-]+)",
        ]
        found: set[str] = set()
        for p in patterns:
            for m in re.finditer(p, body, re.IGNORECASE):
                found.add(m.group(1).lower().strip())

        for em in found:
            results.append({"email": em, "status_code": None, "reason": body[:200]})

        return results

    @staticmethod
    def _get_text_body(msg: Message) -> str:
        """提取邮件的纯文本部分（text/plain），没有就退回 html"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        return payload.decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
            # 没有 plain，取 html
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        return payload.decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
            return ""
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
            return str(payload or "")

    # ─── 判定 hard / soft ──────────────────────────────────

    @classmethod
    def _classify(cls, status_code: Optional[str]) -> str:
        """根据 DSN 状态码判定 hard / soft

        无状态码默认 hard（宁可错杀，群发质量优先）
        """
        if not status_code:
            return "hard"
        if status_code in HARD_STATUS_CODES:
            return "hard"
        if any(status_code.startswith(p) for p in SOFT_STATUS_PREFIXES):
            return "soft"
        # 其他 5.x.x 默认 soft（待人工 review）
        return "soft"

    # ─── UPSERT 到 email_bounces ──────────────────────────

    @classmethod
    def _upsert_recipients_sync(cls, recipients: List[Dict[str, Any]]) -> int:
        """同步版本 UPSERT，供 _sync_scan 在同一线程内调用

        规则：
        - hard 退信 → status='blocked', bounce_type='hard'
        - soft 退信 → bounce_count+1，达到 SOFT_THRESHOLD 升级 blocked
        - 已 unblocked 的邮箱再退信 → 重新 block（hard）或继续累计（soft）
        """
        if not recipients:
            return 0

        # 同步引擎（与异步 AsyncSessionLocal 同库）
        from app.models.database import database_url
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.orm import Session as SyncSession

        sync_url = str(database_url).replace("+aiosqlite", "").replace("+asyncpg", "")
        sync_engine = _ce(sync_url)
        added = 0
        try:
            with SyncSession(sync_engine) as session:
                for r in recipients:
                    em = r["email"]
                    bounce_type = cls._classify(r.get("status_code"))
                    reason = (r.get("reason") or "")[:500] or None
                    now = datetime.now(timezone.utc)

                    existing = session.execute(
                        select(EmailBounce).where(EmailBounce.email == em)
                    ).scalar_one_or_none()

                    if existing is None:
                        # 新增
                        is_blocked = (
                            bounce_type == "hard"
                            or 1 >= settings.BOUNCE_SCAN_SOFT_THRESHOLD
                        )
                        session.add(
                            EmailBounce(
                                email=em,
                                bounce_type=bounce_type,
                                status="blocked" if is_blocked else "unblocked",
                                bounce_count=1,
                                last_bounce_at=now,
                                reason=reason,
                                source="auto",
                            )
                        )
                        added += 1
                    else:
                        # 更新
                        existing.bounce_count = (existing.bounce_count or 0) + 1
                        existing.last_bounce_at = now
                        if reason:
                            existing.reason = reason
                        # type 跟随最新的退信类型
                        existing.bounce_type = bounce_type
                        if bounce_type == "hard":
                            existing.status = "blocked"
                        elif existing.bounce_count >= settings.BOUNCE_SCAN_SOFT_THRESHOLD:
                            existing.status = "blocked"
                        # soft 未达阈值：保持当前 status（manual unblocked 的不会自动翻回）
                        added += 1
                session.commit()
        finally:
            sync_engine.dispose()
        return added

    # ─── watermark 持久化 ──────────────────────────────────

    @classmethod
    def _load_watermark(cls) -> Optional[int]:
        """读取上次扫描到的 last_uid"""
        try:
            if not os.path.exists(cls.STATE_FILE):
                return None
            with open(cls.STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return int(data.get("last_uid", 0)) or None
        except Exception as e:
            logger.warning("load bounce watermark failed: %s", e)
            return None

    @classmethod
    def _save_watermark(cls, last_uid: int) -> None:
        """持久化 watermark"""
        try:
            os.makedirs(os.path.dirname(cls.STATE_FILE), exist_ok=True)
            with open(cls.STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"last_uid": int(last_uid), "updated_at": datetime.now(timezone.utc).isoformat()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("save bounce watermark failed: %s", e)

    # ─── 解析失败存档 ──────────────────────────────────────

    @classmethod
    def _save_unparsed(cls, uid: int, msg: Message, raw: bytes) -> None:
        """解析失败的退信邮件存档，方便后续人工 review 补规则"""
        try:
            os.makedirs(cls.UNPARSED_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            subject = (msg.get("Subject", "") or "").replace("/", "_")[:50]
            fname = f"uid{uid}_{ts}_{subject}.eml"
            path = os.path.join(cls.UNPARSED_DIR, fname)
            with open(path, "wb") as f:
                f.write(raw)
            logger.info("saved unparsed bounce: %s", path)
        except Exception as e:
            logger.warning("save unparsed bounce failed: %s", e)
