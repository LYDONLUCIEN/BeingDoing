"""feedbacks add due_at and assignee_id

Revision ID: 016_feedback_sla_assignee
Revises: 015_payment_qrcode_text
Create Date: 2026-07-25

反馈 SLA 与处理人：
- due_at: 承诺回复截止时间（bug=3 个工作日 / idea=5 个工作日，跳过周末，
  法定节假日不计算、仅文案提示可能延期）。存量数据为 NULL，不参与超时扫描。
- assignee_id: 处理人（super_admin），admin 后台手动指派。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "016_feedback_sla_assignee"
down_revision: Union[str, None] = "015_payment_qrcode_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，需 batch 模式（copy-and-move）
    # 注意：加列和加外键必须分两个 batch，否则 SQLite 方言会报循环依赖
    with op.batch_alter_table("feedbacks") as batch_op:
        batch_op.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("assignee_id", sa.String(length=36), nullable=True)
        )
    with op.batch_alter_table("feedbacks") as batch_op:
        batch_op.create_foreign_key(
            "fk_feedbacks_assignee_id_users",
            "users",
            ["assignee_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("feedbacks") as batch_op:
        batch_op.drop_constraint(
            "fk_feedbacks_assignee_id_users", type_="foreignkey"
        )
        batch_op.drop_column("assignee_id")
        batch_op.drop_column("due_at")
