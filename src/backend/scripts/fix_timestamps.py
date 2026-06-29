"""
时区历史数据修复脚本（T2 层4）

背景:
    在 T2 改造前，所有 DB 时间字段写入的是 naive datetime（无时区信息），
    SQLite 以字符串形式存储，例如 `2026-01-01 00:00:00.000000`。
    改造后统一写入 tz-aware datetime（带 +00:00 后缀），新数据自带时区。
    为避免新旧数据在同一列里格式不一致导致排序/比较错乱，
    需要把历史 naive 数据一次性补上 `+00:00` 后缀。

作用:
    扫描所有已知时间列，对不带 `+`/`-` 时区标记的字符串值追加 `+00:00`。
    幂等：已是 tz-aware 的值会被跳过；可重复运行。

用法:
    # 干跑（只打印，不写库）
    python scripts/fix_timestamps.py --dry-run

    # 实际写入
    python scripts/fix_timestamps.py

    # 指定数据库 URL（默认读取 app.config.settings.DATABASE_URL）
    python scripts/fix_timestamps.py --db-url "sqlite:///./app.db"

注意:
    1. 跑此脚本前请先停掉后端服务，避免读写竞争。
    2. 跑前建议备份 app.db。
    3. SQLite 的 DateTime 列底层是字符串，本脚本直接对字符串做 UPDATE。
       PostgreSQL 不需要此脚本（TIMESTAMP WITH TIME ZONE 自带时区）。
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 添加项目路径，便于读取 settings.DATABASE_URL
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 所有需要修复的表 -> 列清单（按 models 推导，覆盖全部 DateTime 列）
TARGET_COLUMNS: Dict[str, List[str]] = {
    "users": ["created_at", "updated_at", "last_login_at"],
    "user_profiles": ["created_at", "updated_at"],
    "work_history": ["created_at", "updated_at"],
    "project_experiences": ["created_at", "updated_at"],
    "sessions": ["created_at", "updated_at", "last_activity_at"],
    "progress": ["started_at", "completed_at", "created_at", "updated_at"],
    "questions": ["created_at"],
    "answers": ["created_at", "updated_at"],
    "user_selections": ["created_at", "updated_at"],
    "guide_preferences": ["created_at", "updated_at"],
    "exploration_results": ["created_at", "updated_at"],
    "analytics_chat_turns": ["created_at"],
    "analytics_reports": ["created_at"],
    "analytics_likes": ["created_at"],
    "notification_tasks": ["created_at", "updated_at", "started_at", "finished_at"],
    "notification_recipients": ["created_at"],
    "refresh_tokens": ["created_at", "last_used_at", "expires_at", "revoked_at"],
}

# 时区后缀标记：匹配字符串末尾的 +HH:MM / -HH:MM / Z
_TZ_SUFFIX_RE = re.compile(r"([+-]\d{2}:\d{2}|Z)\s*$")


def _parse_db_url(db_url: Optional[str]) -> str:
    """从参数或 settings 解析出 sqlite3 可用的文件路径 URL。"""
    if db_url:
        url = db_url
    else:
        try:
            from app.config.settings import settings

            url = settings.DATABASE_URL
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"无法读取 DATABASE_URL: {exc}") from exc

    # 支持 sqlite+aiosqlite:///./app.db / sqlite:///./app.db / 纯路径
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            return url[len(prefix) :]
    # 兜底：当作文件路径
    return url


def _is_naive(value: str) -> bool:
    """判断一个 datetime 字符串是否不带时区后缀。"""
    if not value:
        return False
    return _TZ_SUFFIX_RE.search(value) is None


def _append_utc(value: str) -> str:
    """在 naive datetime 字符串末尾追加 +00:00。"""
    # 兼容两种常见格式：
    #   "2026-01-01 00:00:00.000000"     -> "2026-01-01 00:00:00.000000+00:00"
    #   "2026-01-01T00:00:00.000000"     -> "2026-01-01T00:00:00.000000+00:00"
    return f"{value}+00:00"


def _resolve_db_path(db_url: Optional[str]) -> Path:
    """解析 db_url 到一个相对/绝对路径，返回绝对路径。"""
    path_str = _parse_db_url(db_url)
    p = Path(path_str)
    if not p.is_absolute():
        # 相对路径基于 cwd 解析
        p = Path.cwd() / p
    if not p.exists():
        raise SystemExit(f"数据库文件不存在: {p}")
    return p


def _list_target_columns(conn: sqlite3.Connection) -> Dict[str, List[str]]:
    """根据实际 DB schema 过滤出真实存在的列，避免缺表/缺列时报错。"""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cur.fetchall()}

    result: Dict[str, List[str]] = {}
    for table, cols in TARGET_COLUMNS.items():
        if table not in existing_tables:
            continue
        cur.execute(f"PRAGMA table_info('{table}')")
        existing_cols = {row[1] for row in cur.fetchall()}
        real_cols = [c for c in cols if c in existing_cols]
        if real_cols:
            result[table] = real_cols
    return result


def _scan_column(
    conn: sqlite3.Connection, table: str, column: str
) -> Tuple[int, int, List[Tuple[str, str]]]:
    """扫描单列，返回 (总行数, 待修复行数, 待修复样本)。"""
    cur = conn.cursor()
    cur.execute(f"SELECT rowid, [{column}] FROM [{table}] WHERE [{column}] IS NOT NULL")
    total = 0
    pending = 0
    samples: List[Tuple[str, str]] = []
    for rowid, value in cur.fetchall():
        total += 1
        if isinstance(value, str) and _is_naive(value):
            pending += 1
            if len(samples) < 3:
                samples.append((str(rowid), value))
    return total, pending, samples


def _update_column(conn: sqlite3.Connection, table: str, column: str) -> int:
    """对单列做幂等 UPDATE：把 naive 值追加 +00:00。

    SQLite 不支持 UPDATE ... FROM 正则，这里用一次性 UPDATE + 字符串拼接兜底。
    会重复跑也安全：已带 + 的字符串不会再被追加（通过 INSTR 检测）。
    """
    cur = conn.cursor()
    # 仅对不含 '+' 的值做拼接，避免重复追加
    # 注意：日期部分含 '-'，不含 '+'，所以用 INSTR(value, '+') = 0 过滤安全
    cur.execute(f"""
        UPDATE [{table}]
        SET [{column}] = [{column}] || '+00:00'
        WHERE [{column}] IS NOT NULL
          AND typeof([{column}]) = 'text'
          AND INSTR([{column}], '+') = 0
        """)
    return cur.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description="把 DB 中 naive datetime 字符串补上 +00:00")
    parser.add_argument(
        "--db-url", default=None, help="数据库 URL（默认读取 settings.DATABASE_URL）"
    )
    parser.add_argument("--dry-run", action="store_true", help="只扫描打印，不写入")
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db_url)
    print(f"[fix_timestamps] 数据库: {db_path}")
    print(f"[fix_timestamps] 模式: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("-" * 60)

    conn = sqlite3.connect(str(db_path))
    try:
        targets = _list_target_columns(conn)
        if not targets:
            print("[fix_timestamps] 没有需要扫描的表/列，退出。")
            return 0

        total_pending = 0
        for table in sorted(targets):
            for column in targets[table]:
                total, pending, samples = _scan_column(conn, table, column)
                if total == 0:
                    continue
                flag = "需修复" if pending > 0 else "已就绪"
                print(f"[{flag}] {table}.{column}: 共 {total} 行，待修复 {pending} 行")
                for rowid, value in samples:
                    print(f"    rowid={rowid} 旧值={value!r}")

                if not args.dry_run and pending > 0:
                    updated = _update_column(conn, table, column)
                    print(f"    -> 已更新 {updated} 行")
                    total_pending += pending
                else:
                    total_pending += pending

        if not args.dry_run and total_pending > 0:
            conn.commit()
            print("-" * 60)
            print(f"[fix_timestamps] 已提交，共修复 {total_pending} 处（按扫描口径统计）。")
        else:
            print("-" * 60)
            if args.dry_run:
                print(f"[fix_timestamps] DRY RUN 结束，扫描到 {total_pending} 处待修复（未写入）。")
            else:
                print("[fix_timestamps] 没有需要修复的数据。")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
