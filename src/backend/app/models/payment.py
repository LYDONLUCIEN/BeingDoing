"""
支付与会员相关数据模型（P1 建表，P2 支付闭环 / P3 会员启用）

包含三张表：
- payment_orders: 支付订单（购买者、商品、渠道、金额、状态）
- coupons: 折扣券（通用码、固定金额、无门槛、永久有效、核销一次即作废）
- subscriptions: 会员订阅（P3 用，本期仅建表）

金额一律整数分存储。券状态机：unused → locked（下单锁定）→ used（支付成功核销）；
订单关闭/取消时 locked → unused 释放。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class PaymentOrder(Base):
    """支付订单表

    Attributes:
        id: 订单 ID（UUID，主键）
        order_no: 商户订单号（唯一，前缀+时间戳+随机生成）
        user_id: 购买者用户 ID（外键 → users.id）
        product_type: 商品类型（activation_code / membership_monthly / membership_lifetime）
        quantity: 数量（v1 恒为 1，预留）
        amount_original: 原价（分）
        amount_discount: 抵扣金额（分）
        amount_paid: 实付金额（分）
        coupon_id: 使用的折扣券 ID（外键 → coupons.id，可空）
        channel: 支付渠道（wechat / alipay）
        status: 订单状态（pending/paid/granted/closed/cancelled/refunding/refunded）
        channel_transaction_id: 渠道交易号
        delivered_code: 交付的激活码
        qr_code: 渠道预下单返回的支付二维码串（供订单详情/继续支付）
        paid_at / closed_at / refunded_at: 支付 / 关单 / 退款时间
        created_at / updated_at: 通用时间戳
    """

    __tablename__ = "payment_orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_no = Column(String(32), unique=True, nullable=False, index=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_type = Column(String(32), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    amount_original = Column(Integer, nullable=False)
    amount_discount = Column(Integer, default=0, nullable=False)
    amount_paid = Column(Integer, nullable=False)
    coupon_id = Column(String(36), ForeignKey("coupons.id"), nullable=True)
    channel = Column(String(16), nullable=False)
    status = Column(String(16), default="pending", nullable=False, index=True)
    channel_transaction_id = Column(String(64), nullable=True)
    delivered_code = Column(String(16), nullable=True)
    # 列名保留 qr_code（兼容历史），实际存支付跳转 URL/凭证（page.pay URL 约 800~1000 字符，故用 Text）
    qr_code = Column(Text, nullable=True)
    # 商品特定载荷（JSON 文本）：renewal={target_code, added_days}；
    # annual={gift_codes: [...]}；consultation={booking_id}（P-B，迁移 013）
    meta = Column(Text, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # 关系
    coupon = relationship("Coupon", foreign_keys=[coupon_id])


class Coupon(Base):
    """折扣券表

    通用券码（不绑定用户）：固定金额（分）、无门槛、永久有效、核销一次即作废。

    Attributes:
        id: 券 ID（UUID，主键）
        code: 券码（12 位大写字母+数字，唯一）
        amount: 面额（分）
        status: 状态（unused/locked/used，locked=下单锁定中）
        locked_order_id: 锁定它的订单 ID（locked 时填）
        used_by_user_id: 核销用户 ID
        used_order_id: 核销订单 ID
        used_at: 核销时间
        source: 来源（admin / email_auto）
        created_by: 创建人用户 ID（admin 创建时填）
        created_at: 创建时间
    """

    __tablename__ = "coupons"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(32), unique=True, nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    status = Column(String(16), default="unused", nullable=False, index=True)
    locked_order_id = Column(String(36), nullable=True)
    used_by_user_id = Column(String(36), nullable=True)
    used_order_id = Column(String(36), nullable=True)
    used_at = Column(DateTime, nullable=True)
    source = Column(String(16), default="admin", nullable=False)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ConsultationBooking(Base):
    """报告解读咨询预约单（P-B 建表，P-D 完善问卷/预约流程）

    Attributes:
        id: 预约单 ID（UUID，主键）
        order_id: 来源支付订单（外键 → payment_orders.id）
        user_id: 购买用户 ID（外键 → users.id）
        report_id: 问卷中选择的报告 ID（可空，待填问卷）
        topics: 想讨论的主题/期望（文本）
        time_slots: 候选时间段（JSON 文本）
        contact: 联系方式
        note: 备注
        status: 状态机（pending_survey/submitted/scheduled/completed/cancelled）
        scheduled_at: 管理员确认的预约时间
        admin_note: 管理员备注
        created_at / updated_at: 通用时间戳
    """

    __tablename__ = "consultation_bookings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        String(36), ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_id = Column(String(64), nullable=True)
    topics = Column(Text, nullable=True)
    time_slots = Column(Text, nullable=True)
    contact = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(24), default="pending_survey", nullable=False, index=True)
    scheduled_at = Column(DateTime, nullable=True)
    admin_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class TeamAnalysis(Base):
    """团队分析记录（P-B 建表，P-E 实现生成逻辑）

    Attributes:
        id: 分析 ID（UUID，主键）
        user_id: 发起用户（所属人）ID（外键 → users.id）
        title: 分析标题
        code_list: 参与分析的激活码列表（JSON 文本）
        report_ids: 参与分析的报告 ID 列表（JSON 文本）
        status: 状态（generating/done/failed）
        result_markdown: 分析结果（Markdown）
        error: 失败原因
        created_at: 创建时间
    """

    __tablename__ = "team_analyses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(255), nullable=False)
    code_list = Column(Text, nullable=True)
    report_ids = Column(Text, nullable=True)
    status = Column(String(16), default="generating", nullable=False)
    result_markdown = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Subscription(Base):
    """会员订阅表（P3 用，本期仅建表）

    Attributes:
        id: 订阅 ID（UUID，主键）
        user_id: 用户 ID（外键 → users.id）
        plan_type: 套餐类型（monthly / lifetime）
        status: 状态（active / cancelled / expired）
        channel: 扣款渠道（wechat / alipay）
        agreement_no: 代扣签约号
        auto_renew: 是否自动续费（永久会员为 False）
        current_period_start / current_period_end: 当前周期起止
        cancelled_at: 取消（解约）时间
        created_at / updated_at: 通用时间戳
    """

    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_type = Column(String(16), nullable=False)
    status = Column(String(16), default="active", nullable=False, index=True)
    channel = Column(String(16), nullable=True)
    agreement_no = Column(String(64), nullable=True)
    auto_renew = Column(Boolean, default=True, nullable=False)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
