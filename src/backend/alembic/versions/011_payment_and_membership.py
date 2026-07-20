"""add payment_orders, coupons, subscriptions tables + membership columns

Revision ID: 011_payment_and_membership
Revises: 010_feedback_and_notifications
Create Date: 2026-07-19

支付模块 P1（计划见 tasks/payment-module-plan.md 第二节）：
- payment_orders: 支付订单（P2 支付闭环用，本期建表）
- coupons: 折扣券（通用码、固定金额分、无门槛、永久有效、核销一次即作废）
- subscriptions: 会员订阅（P3 用，本期建表）
- users 加列：membership_plan / membership_expires_at（会员缓存字段，P3 维护）
- notification_tasks 加列：attach_coupon（邮件群发附折扣券开关）
- notification_recipients 加列：coupon_code（逐收件人分到的券码）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011_payment_and_membership"
down_revision: Union[str, None] = "010_feedback_and_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- coupons ----
    op.create_table(
        "coupons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="unused",
        ),
        sa.Column("locked_order_id", sa.String(length=36), nullable=True),
        sa.Column("used_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("used_order_id", sa.String(length=36), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="admin",
        ),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coupons_code", "coupons", ["code"], unique=True)
    op.create_index("ix_coupons_status", "coupons", ["status"])

    # ---- payment_orders ----
    op.create_table(
        "payment_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_no", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("product_type", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount_original", sa.Integer(), nullable=False),
        sa.Column("amount_discount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_paid", sa.Integer(), nullable=False),
        sa.Column("coupon_id", sa.String(length=36), nullable=True),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("channel_transaction_id", sa.String(length=64), nullable=True),
        sa.Column("delivered_code", sa.String(length=16), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_orders_order_no", "payment_orders", ["order_no"], unique=True)
    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_index("ix_payment_orders_status", "payment_orders", ["status"])

    # ---- subscriptions ----
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("plan_type", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
        sa.Column("channel", sa.String(length=16), nullable=True),
        sa.Column("agreement_no", sa.String(length=64), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # ---- users 加列（会员缓存字段，P3 维护）----
    op.add_column(
        "users",
        sa.Column(
            "membership_plan",
            sa.String(length=16),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "users",
        sa.Column("membership_expires_at", sa.DateTime(), nullable=True),
    )

    # ---- 邮件群发附折扣券 ----
    op.add_column(
        "notification_tasks",
        sa.Column(
            "attach_coupon",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "notification_recipients",
        sa.Column("coupon_code", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_recipients", "coupon_code")
    op.drop_column("notification_tasks", "attach_coupon")

    op.drop_column("users", "membership_expires_at")
    op.drop_column("users", "membership_plan")

    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index("ix_payment_orders_status", table_name="payment_orders")
    op.drop_index("ix_payment_orders_user_id", table_name="payment_orders")
    op.drop_index("ix_payment_orders_order_no", table_name="payment_orders")
    op.drop_table("payment_orders")

    op.drop_index("ix_coupons_status", table_name="coupons")
    op.drop_index("ix_coupons_code", table_name="coupons")
    op.drop_table("coupons")
