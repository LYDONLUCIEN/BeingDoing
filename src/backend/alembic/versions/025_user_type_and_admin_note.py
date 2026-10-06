"""users add user_type + admin_note

Revision ID: 025_user_type_admin_note
Revises: 024_coupon_multi_redemption
Create Date: 2026-10-06

用户类型标签与后台备注（2026-10-06 admin 数据导出需求）：
- users.user_type：real（真实用户，默认）/ beta（内测用户）/ test（测试账号）/ admin（管理员账号）
  存量用户与新建用户默认 real，由管理员手动把内部账号标出
- users.admin_note：管理员备注（后台维护，随用户全量导出打包）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "025_user_type_admin_note"
down_revision: Union[str, None] = "024_coupon_multi_redemption"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 用户类型枚举（代码层校验，DB 存字符串保持灵活）
VALID_USER_TYPES = ("real", "beta", "test", "admin")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "user_type", sa.String(length=16), nullable=False, server_default="real"
        ),
    )
    op.add_column("users", sa.Column("admin_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "admin_note")
    op.drop_column("users", "user_type")
