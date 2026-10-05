"""
支付与会员相关数据模型（P1 建表，P2 支付闭环 / P3 会员启用）

包含以下表：
- payment_order_lines: 订单明细行（优惠分摊口径，退款上限依据，2026-10-05）
- payment_refunds: 退款申请单（全退/部分退统一状态机，2026-10-05）
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
        amount_refunded: 累计成功退款（分，恒 ≤ amount_paid；等于 amount_paid 时 status=refunded）
        coupon_id: 使用的折扣券 ID（外键 → coupons.id，可空）
        channel: 支付渠道（wechat / alipay）
        status: 订单状态（pending/paid/granted/partially_refunded/closed/cancelled/refunding/refunded）
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
    # 累计成功退款（分）；不变式：amount_refunded == amount_paid ⇔ status == refunded
    amount_refunded = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # 关系
    coupon = relationship("Coupon", foreign_keys=[coupon_id])


class PaymentOrderLine(Base):
    """订单明细行（优惠分摊口径，2026-10-05 退款系统）

    交付（granted）时生成并落库分摊，退款只读取、不重算；存量 granted 订单
    首次访问退款能力时惰性回填（payment_line_service.ensure_order_lines）。

    分摊算法：同单内各行商品等价 → 原价/券/实付均按行数等分、尾差归最后一行，
    保证 Σ行 == 订单总额（不变式，见设计文档 2.2）。券面额超折后价时各行
    amount_paid_alloc 可为 0（Σ 仍等于订单实付），不为负。

    Attributes:
        id: 行 ID（UUID，主键）
        order_id: 订单 ID（外键 → payment_orders.id）
        line_no: 行号（1 起）
        item_type: 行商品类型（code 激活码 / consultation_service 咨询 / renewal_service 延期）
        item_ref: 行关联实体（码值 / booking_id / 目标码）
        price_original_alloc: 分摊原价（分）
        coupon_alloc: 优惠分摊额（分，会员折扣+券合计，Σ = amount_discount）
        amount_paid_alloc: 分摊实付（分，退款上限取此值）
        status: available 未动可退 / used 生成时已被用（激活/消耗/已预约）/ refunded 已随退款作废
        refunded_at: 随退款作废时间
        created_at: 创建时间

    注意：status 是退款驱动流转的持久记录（available → refunded）；
    「申请后码被激活」等竞态由审批/查询时实时重验码状态兜底，不回写本列。
    """

    __tablename__ = "payment_order_lines"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        String(36), ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no = Column(Integer, nullable=False)
    item_type = Column(String(32), nullable=False)
    item_ref = Column(String(64), nullable=True)
    price_original_alloc = Column(Integer, nullable=False)
    coupon_alloc = Column(Integer, default=0, nullable=False)
    amount_paid_alloc = Column(Integer, nullable=False)
    status = Column(String(16), default="available", nullable=False)
    refunded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class PaymentRefund(Base):
    """退款申请单（全退/部分退统一状态机，2026-10-05）

    状态机：
        pending_review →（批准并执行）→ refunding → succeeded / failed（可重试，同 refund_no）
        pending_review → withdrawn（用户撤回）/ rejected（admin 驳回，必填理由）

    幂等与审计：refund_no = order_no + "R" + 3 位序号（即支付宝 out_request_no），
    唯一索引兜底；申请额/批准额分列，调整必填 reason_admin；渠道回执留
    channel_response；批准时关联行快照存 line_snapshot。

    Attributes:
        id: 退款单 ID（UUID，主键）
        refund_no: 退款单号（唯一，渠道幂等号）
        order_id / order_no: 关联原订单
        user_id: 申请人（= 订单主人）
        originated: user 用户自提 / admin 代录
        created_by_admin: 代录 admin 用户 ID
        refund_type: full 全退 / partial 部分退
        requested_amount: 申请金额（分）
        approved_amount: 批准金额（分，= 执行金额）
        reason_user: 用户申请理由
        reason_admin: 审批意见 / 驳回理由 / 金额调整理由
        status: pending_review/approved/refunding/succeeded/failed/rejected/withdrawn
        reviewed_by / reviewed_at: 审批 admin 及时间
        executed_at / succeeded_at: 渠道调用 / 渠道确认成功时间
        failed_reason: 渠道失败原因
        channel_response: 渠道回执（JSON 文本，审计留存）
        line_snapshot: 批准时关联行快照（JSON 文本）
        created_at / updated_at: 通用时间戳
    """

    __tablename__ = "payment_refunds"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    refund_no = Column(String(32), unique=True, nullable=False, index=True)
    order_id = Column(
        String(36), ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_no = Column(String(32), nullable=False, index=True)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    originated = Column(String(8), nullable=False)
    created_by_admin = Column(String(36), nullable=True)
    refund_type = Column(String(8), nullable=False)
    requested_amount = Column(Integer, nullable=False)
    approved_amount = Column(Integer, nullable=True)
    reason_user = Column(Text, nullable=True)
    reason_admin = Column(Text, nullable=True)
    status = Column(String(16), default="pending_review", nullable=False, index=True)
    reviewed_by = Column(String(36), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    succeeded_at = Column(DateTime, nullable=True)
    failed_reason = Column(Text, nullable=True)
    channel_response = Column(Text, nullable=True)
    line_snapshot = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Coupon(Base):
    """折扣券表

    固定金额（分）、无门槛抵扣码；有有效期（expires_at，默认 90 天，admin 可调），
    可绑定归属用户（owner_user_id，None=未绑定流通券），核销一次即作废。

    Attributes:
        id: 券 ID（UUID，主键）
        code: 券码（12 位大写字母+数字，唯一）
        amount: 面额（分）
        status: 状态（unused/locked/used/void；expired 为 unused 的惰性派生态，不落库）
        expires_at: 过期时间（unused 且 expires_at<now 即视为已过期；locked 免疫）
        owner_user_id: 归属用户 ID（发放即绑定/下单认领；None=未绑定流通券）
        voided_at: 作废时间（软删除，admin 可恢复）
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
    expires_at = Column(DateTime, nullable=True)
    owner_user_id = Column(String(36), nullable=True, index=True)
    voided_at = Column(DateTime, nullable=True)
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
