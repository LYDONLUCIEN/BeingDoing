"""payment_orders add meta column + consultation_bookings / team_analyses tables

Revision ID: 013_packages_consultation_team
Revises: 012_payment_order_qrcode
Create Date: 2026-07-20

套餐商品化 P-B（ADR-0008，计划见 tasks/packages-trial-plan.md 第二节）：
- payment_orders 加列 meta TEXT（JSON）：product 特定载荷——
  renewal={target_code, added_days}；annual={gift_codes: [...]}；consultation={booking_id}
- consultation_bookings：报告解读咨询预约单
  （状态机 pending_survey/submitted/scheduled/completed/cancelled）
- team_analyses：团队分析记录（P-E 实现生成逻辑，本期建表）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013_packages_consultation_team"
down_revision: Union[str, None] = "012_payment_order_qrcode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- payment_orders 加 meta 列 ----
    op.add_column("payment_orders", sa.Column("meta", sa.Text(), nullable=True))

    # ---- consultation_bookings ----
    op.create_table(
        "consultation_bookings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=True),
        sa.Column("topics", sa.Text(), nullable=True),
        sa.Column("time_slots", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending_survey",
        ),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_consultation_bookings_order_id", "consultation_bookings", ["order_id"]
    )
    op.create_index(
        "ix_consultation_bookings_user_id", "consultation_bookings", ["user_id"]
    )
    op.create_index(
        "ix_consultation_bookings_status", "consultation_bookings", ["status"]
    )

    # ---- team_analyses ----
    op.create_table(
        "team_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("code_list", sa.Text(), nullable=True),
        sa.Column("report_ids", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="generating",
        ),
        sa.Column("result_markdown", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_analyses_user_id", "team_analyses", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_team_analyses_user_id", table_name="team_analyses")
    op.drop_table("team_analyses")

    op.drop_index("ix_consultation_bookings_status", table_name="consultation_bookings")
    op.drop_index("ix_consultation_bookings_user_id", table_name="consultation_bookings")
    op.drop_index("ix_consultation_bookings_order_id", table_name="consultation_bookings")
    op.drop_table("consultation_bookings")

    op.drop_column("payment_orders", "meta")
