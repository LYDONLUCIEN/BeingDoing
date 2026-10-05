"""payment refund system: order lines + refunds tables

Revision ID: 023_payment_refund_system
Revises: 022_abuse_detection
Create Date: 2026-10-05

订单退款系统（wiki/开发文档/10-05/订单系统退款设计.md）：
- payment_orders 加 amount_refunded（累计成功退款，分）
- payment_order_lines 订单明细行（优惠分摊口径，退款上限依据）：
  交付时生成；存量 granted 订单由 payment_line_service.ensure_order_lines 惰性回填
- payment_refunds 退款申请单（全退/部分退统一状态机：
  pending_review → refunding → succeeded/failed + withdrawn/rejected）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "023_payment_refund_system"
down_revision: Union[str, None] = "022_abuse_detection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- payment_orders 加累计退款列 ----
    op.add_column(
        "payment_orders",
        sa.Column("amount_refunded", sa.Integer(), nullable=False, server_default="0"),
    )

    # ---- payment_order_lines：订单明细行 ----
    op.create_table(
        "payment_order_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("item_ref", sa.String(length=64), nullable=True),
        sa.Column("price_original_alloc", sa.Integer(), nullable=False),
        sa.Column("coupon_alloc", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_paid_alloc", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="available"),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_order_lines_order_id", "payment_order_lines", ["order_id"])

    # ---- payment_refunds：退款申请单 ----
    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("refund_no", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("originated", sa.String(length=8), nullable=False),
        sa.Column("created_by_admin", sa.String(length=36), nullable=True),
        sa.Column("refund_type", sa.String(length=8), nullable=False),
        sa.Column("requested_amount", sa.Integer(), nullable=False),
        sa.Column("approved_amount", sa.Integer(), nullable=True),
        sa.Column("reason_user", sa.Text(), nullable=True),
        sa.Column("reason_admin", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending_review"),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(), nullable=True),
        sa.Column("failed_reason", sa.Text(), nullable=True),
        sa.Column("channel_response", sa.Text(), nullable=True),
        sa.Column("line_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_refunds_refund_no", "payment_refunds", ["refund_no"], unique=True)
    op.create_index("ix_payment_refunds_order_id", "payment_refunds", ["order_id"])
    op.create_index("ix_payment_refunds_order_no", "payment_refunds", ["order_no"])
    op.create_index("ix_payment_refunds_user_id", "payment_refunds", ["user_id"])
    op.create_index("ix_payment_refunds_status", "payment_refunds", ["status"])


def downgrade() -> None:
    op.drop_index("ix_payment_refunds_status", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_user_id", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_order_no", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_order_id", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_refund_no", table_name="payment_refunds")
    op.drop_table("payment_refunds")
    op.drop_index("ix_payment_order_lines_order_id", table_name="payment_order_lines")
    op.drop_table("payment_order_lines")
    op.drop_column("payment_orders", "amount_refunded")
