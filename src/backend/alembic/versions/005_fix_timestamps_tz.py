"""Fix naive datetime strings to tz-aware (append +00:00)

Revision ID: 005_fix_timestamps_tz
Revises: 004_notification
Create Date: 2026-06-29

背景:
    T2 改造后，所有 DB 时间字段统一写入 tz-aware datetime（带 +00:00）。
    历史 naive 数据需要补上 +00:00 后缀，避免新旧格式混用导致排序/比较错乱。

本 migration 与 scripts/fix_timestamps.py 做的事一致：
    对 SQLite 中所有已知时间列，把不含 '+' 的字符串值追加 '+00:00'。
    幂等：已是 tz-aware 的值不会被二次追加。

注意:
    - 主要面向 SQLite（DateTime 列底层是字符串）。
    - PostgreSQL 的 TIMESTAMP WITH TIME ZONE 列自带时区，本 migration 在 PG 上是 no-op。
    - 跑 alembic upgrade 前请务必备份 app.db。
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers
revision: str = "005_fix_timestamps_tz"
down_revision: Union[str, None] = "004_notification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 所有需要修复的表 -> 列清单（与 scripts/fix_timestamps.py 保持同步）
_TARGET_COLUMNS = {
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


def _fix_sqlite() -> None:
    """对 SQLite 库做幂等 UPDATE：naive 字符串末尾追加 +00:00。"""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    from sqlalchemy import inspect, text  # noqa: WPS433

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, cols in _TARGET_COLUMNS.items():
        if table not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        for column in cols:
            if column not in existing_cols:
                continue
            # 仅对不含 '+' 的字符串值做拼接，避免重复追加
            # 日期部分含 '-' 但不含 '+'，用 INSTR 过滤安全
            sql = text(f"""
                UPDATE [{table}]
                SET [{column}] = [{column}] || '+00:00'
                WHERE [{column}] IS NOT NULL
                  AND typeof([{column}]) = 'text'
                  AND INSTR([{column}], '+') = 0
                """)
            bind.execute(sql)
    bind.commit()


def upgrade() -> None:
    _fix_sqlite()


def downgrade() -> None:
    # 数据修复类 migration 不可逆：回滚不会去掉 +00:00 后缀
    # （去掉后缀会破坏 tz-aware 数据的一致性）
    pass
