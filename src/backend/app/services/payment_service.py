"""
支付订单服务（P2a：支付宝闭环；P-B：套餐商品化，ADR-0008）

职责：
1. 商品与金额：商品目录（季度套餐/年度套餐、延期、咨询）；会员价（先折）→ 减券面额（后券）→ 下限 0 元
2. create_order：下单（order_no 唯一重试）→ 锁券 → 调渠道下单存 qr_code（支付跳转 URL）；
   0 元单不调渠道，直接走支付成功交付（status granted）。旧 SKU activation_code 已下架
3. handle_alipay_notify：验签 → 查单 → 校验金额 → 幂等交付（TRADE_SUCCESS / TRADE_FINISHED）
4. cancel_order / close_timeout_orders：关单（尝试渠道 close_order，失败仅记日志）+ 释放券
5. admin_refund：套餐订单任一码被激活/消耗则整单不可退，全部未动可退并作废全部码（ADR-0014）；
   延期交付即已用不可退；咨询仅未预约可退（退款取消预约单）；
   历史 activation_code 订单维持原规则（码未被 claim 可退，成功作废码）

设计要点：
- 金额一律整数分；order_no = "X" + UTC 14 位时间戳 + 6 位随机大写 hex（21 字符）
- 交付幂等：已 granted 直接返回，重复回调不重复发码
- 业务约束违反抛 ValueError（路由转 400）；订单不存在抛 OrderNotFoundError（路由转 404）；
  渠道未配置 get_channel 抛 RuntimeError（路由转 503）
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select

from app.config.settings import settings
from app.core.payment import get_channel
from app.core.payment.base import NotifyResult  # noqa: F401（供测试/调用方引用）
from app.models.database import AsyncSessionLocal
from app.models.feedback import Notification
from app.models.payment import ConsultationBooking, Coupon, PaymentOrder
from app.models.user import User
from app.services.coupon_service import CouponService
from app.services.email_service import EmailService
from app.utils.simple_activation_manager import (
    SimpleActivationManager,
    get_activation_with_manager,
)

logger = logging.getLogger(__name__)

# 订单号生成冲突重试上限
_MAX_ORDER_NO_RETRIES = 5

# 支付宝视为支付成功的交易状态
_ALIPAY_PAID_STATUSES = {"TRADE_SUCCESS", "TRADE_FINISHED"}

# 即时查单（sync）冷却：order_no → 上次查渠道的 time.monotonic()，10 秒内不重复查（防刷）
_ORDER_SYNC_COOLDOWN: Dict[str, float] = {}
_SYNC_COOLDOWN_SECONDS = 10.0

# 旧 SKU（已下架，仅历史订单兼容）
_LEGACY_PRODUCT_TYPE = "activation_code"
_LEGACY_PRODUCT_NAME = "全程激活码"

# 商品类型（P-B）
PRODUCT_QUARTERLY = "quarterly_package"
PRODUCT_ANNUAL = "annual_package"
PRODUCT_RENEWAL = "renewal"
PRODUCT_CONSULTATION = "consultation"
_VALID_PRODUCT_TYPES = {
    PRODUCT_QUARTERLY,
    PRODUCT_ANNUAL,
    PRODUCT_RENEWAL,
    PRODUCT_CONSULTATION,
}

# 订单意图（ADR-0014）：试用拦截点直购升级——交付后发码并自动消耗升级试用码
INTENT_UPGRADE_TRIAL = "upgrade_trial"

# 团队分析报告提示（年度套餐 3 码交付后：交付邮件附文案 + 站内信 + 前端弹窗）
# 联系邮箱统一走 settings.TEAM_ANALYSIS_EMAIL（前端经 /payment/products 下发）
NOTIFY_TYPE_TEAM_ANALYSIS = "team_analysis_notice"
NOTIFY_TITLE_TEAM_ANALYSIS = "团队分析报告"


def _team_analysis_notice() -> str:
    """团队分析报告提示文案（邮箱独占一行，避免纯文本邮件客户端把上下文误识别为链接）"""
    return (
        "感谢购买！如您需要团队分析报告，请发送邮件至：\n"
        f"{settings.TEAM_ANALYSIS_EMAIL}\n"
        "邮件内容需包含您需要分析的三个激活码，咨询师会在5个工作日内发送报告至您的邮箱，请注意查收。"
    )

# 套餐时长（天）：package_type → settings 字段
_PACKAGE_DAYS = {
    "quarterly": lambda: settings.QUARTERLY_DAYS,
    "annual": lambda: settings.ANNUAL_DAYS,
}


def _package_days(package_type: str) -> int:
    """package_type（quarterly/annual）→ 时长天数（从 settings 读）"""
    getter = _PACKAGE_DAYS.get((package_type or "").strip().lower())
    if getter is None:
        raise ValueError(f"未知的套餐类型：{package_type}")
    return getter()


def _product_price(product_type: str) -> int:
    """商品目录定价（分）；renewal 不走此函数（按目标码 package_type 定价）"""
    if product_type == PRODUCT_QUARTERLY:
        return settings.QUARTERLY_PRICE
    if product_type == PRODUCT_ANNUAL:
        return settings.ANNUAL_PRICE
    if product_type == PRODUCT_CONSULTATION:
        return settings.CONSULTATION_PRICE
    raise ValueError(f"不支持的商品类型：{product_type}")


def _product_name(product_type: str) -> str:
    """渠道预下单 subject 用的商品名"""
    return {
        PRODUCT_QUARTERLY: "季度套餐",
        PRODUCT_ANNUAL: "年度套餐",
        PRODUCT_RENEWAL: "延期激活",
        PRODUCT_CONSULTATION: "报告解读咨询",
        _LEGACY_PRODUCT_TYPE: _LEGACY_PRODUCT_NAME,
    }.get(product_type, product_type)


class OrderNotFoundError(Exception):
    """订单不存在（路由转 404）"""


def _activation_manager() -> SimpleActivationManager:
    """生产激活码管理器（独立成函数便于测试替换 base_dir）"""
    return SimpleActivationManager()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite 读回的 naive datetime 按 UTC 解释"""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class PaymentService:
    """支付订单服务"""

    # ─── 商品与金额 ─────────────────────────────────────────────

    @staticmethod
    def get_products() -> Dict[str, Any]:
        """商品目录 + 会员折扣信息（P-B：季度套餐/年度套餐 + 咨询；旧 SKU 已下架）

        延期激活不在目录中：从「我的激活码」页带 target_code 进 renewal 下单。
        """
        return {
            "items": [
                {
                    "product_type": PRODUCT_QUARTERLY,
                    "name": "季度套餐",
                    "price": settings.QUARTERLY_PRICE,
                    "duration_days": settings.QUARTERLY_DAYS,
                    "popular": True,
                    "description": (
                        "1 个激活码（未绑定）：可用于升级你的试用码（探索记录保留）、"
                        "自己激活使用或转送朋友；自购买成功起算，有效期 3 个月"
                    ),
                    "features": [
                        "不限量对话",
                        "开放全部 5 个探索阶段",
                        "1 份完整报告（30+ 页 / 7+ 主题维度）",
                        "报告提交后 24 小时人工审核交付",
                        "有效期 3 个月（购买成功起算）",
                    ],
                },
                {
                    "product_type": PRODUCT_ANNUAL,
                    "name": "年度套餐",
                    "price": settings.ANNUAL_PRICE,
                    "duration_days": settings.ANNUAL_DAYS,
                    "description": (
                        "3 个激活码（均未绑定）：可自用、转送朋友，或用 1 个升级你的试用码；"
                        "可用于 3 个不同账号，或同一账号分阶段对比；每码有效期 1 年"
                    ),
                    "features": [
                        "不限量对话",
                        "开放全部 5 个探索阶段",
                        "3 份完整报告（单份 30+ 页 / 7+ 主题）",
                        "团队匹配度分析 + 团队角色投射",
                        "报告提交后 24 小时人工审核交付",
                        "3 个激活码（可自用可转送）",
                        "每码有效期 1 年（购买成功起算）",
                    ],
                },
                {
                    "product_type": PRODUCT_CONSULTATION,
                    "name": "报告解读咨询",
                    "price": settings.CONSULTATION_PRICE,
                    "requires_report": True,
                    "description": "一对一线上沟通 60 分钟，需至少一份已完成报告",
                    "features": [
                        "60 分钟一对一线上沟通",
                        "购买后填写预约问卷（主题/时间段/联系方式）",
                        "未预约前可退款",
                    ],
                },
            ],
            "member_discount_percent": settings.MEMBER_DISCOUNT_PERCENT,
            "membership_enabled": settings.MEMBERSHIP_ENABLED,
            "team_analysis_email": settings.TEAM_ANALYSIS_EMAIL,
        }

    @staticmethod
    def is_member(user: User) -> bool:
        """是否生效会员（monthly/lifetime 且未过期）"""
        plan = (getattr(user, "membership_plan", None) or "none").strip().lower()
        if plan not in ("monthly", "lifetime"):
            return False
        expires_at = _as_utc(getattr(user, "membership_expires_at", None))
        return expires_at is not None and expires_at > _utcnow()

    @classmethod
    def compute_amounts(
        cls,
        user: User,
        product_type: str = PRODUCT_ANNUAL,
        coupon_amount: int = 0,
        original_price: Optional[int] = None,
    ) -> Tuple[int, int, int]:
        """金额计算：会员价（先折）→ 减券（后券）→ 下限 0

        Args:
            user: 用户行（取 membership_plan / membership_expires_at）
            product_type: 商品类型（决定原价；renewal 请显式传 original_price）
            coupon_amount: 券面额（分，无券传 0）
            original_price: 显式原价（分，renewal 按目标码 package_type 定价时用）

        Returns:
            (amount_original, amount_discount, amount_paid)
        """
        original = original_price if original_price is not None else _product_price(product_type)
        base = original
        if cls.is_member(user):
            base = round(original * settings.MEMBER_DISCOUNT_PERCENT / 100)
        paid = max(0, base - max(0, coupon_amount))
        discount = original - paid
        return original, discount, paid

    # ─── 下单 ───────────────────────────────────────────────────

    @staticmethod
    def _generate_order_no() -> str:
        """ "X" + UTC 14 位时间戳 + 6 位随机大写 hex（21 字符）"""
        return "X" + _utcnow().strftime("%Y%m%d%H%M%S") + secrets.token_hex(3).upper()

    @staticmethod
    def _validate_renewal_target(user_id: str, target_code: str) -> Tuple[Any, str]:
        """延期激活目标码校验（P-B）

        规则：码须 code_type=full 且 package_type∈{quarterly,annual}（存量无类型码拒延，
        引导买套餐）；操作者须为激活人（owner_user_id）或所属人（purchaser_user_id）。

        Returns:
            (record, package_type)

        Raises:
            ValueError: 各类校验失败（路由转 400）
        """
        code = (target_code or "").strip().upper()
        if not code:
            raise ValueError("延期激活必须传入 target_code（目标激活码）")
        _, rec = get_activation_with_manager(code)
        if rec is None:
            raise ValueError("目标激活码不存在")
        if rec.status not in ("active", "expired"):
            raise ValueError("目标激活码不可用（已作废或已删除）")
        if (getattr(rec, "code_type", "full") or "full") != "full":
            raise ValueError("仅完整码可延期（试用码请先购买激活码升级）")
        package_type = (getattr(rec, "package_type", None) or "").strip().lower()
        if package_type not in ("quarterly", "annual"):
            raise ValueError("该激活码无套餐类型，无法延期，请购买激活码")
        if user_id not in {rec.owner_user_id, getattr(rec, "purchaser_user_id", None)}:
            raise ValueError("仅该激活码的激活人或所属人可为其延期")
        return rec, package_type

    @classmethod
    async def create_order(
        cls,
        user_id: str,
        product_type: str,
        channel: str,
        coupon_code: Optional[str] = None,
        target_code: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> Tuple[PaymentOrder, Optional[Dict[str, str]]]:
        """创建支付订单

        Returns:
            (order, payment)：payment = {"channel", "pay_url"}；0 元单为 None

        Raises:
            ValueError: 商品/渠道不支持、券无效、renewal 目标码校验失败
            RuntimeError: 渠道未配置（路由转 503）
            PaymentChannelError: 渠道下单失败（订单保留 pending 可取消/超时关单）
        """
        if product_type == _LEGACY_PRODUCT_TYPE:
            raise ValueError("该商品已下架，请选择激活码")
        if product_type not in _VALID_PRODUCT_TYPES:
            raise ValueError(f"不支持的商品类型：{product_type}")
        if channel == "wechat":
            raise ValueError("微信支付即将上线")
        if channel != "alipay":
            raise ValueError(f"不支持的支付渠道：{channel}")

        # 订单意图（ADR-0014）：仅套餐支持 upgrade_trial（试用拦截点直购升级）
        intent = (intent or "").strip()
        if intent:
            if intent != INTENT_UPGRADE_TRIAL:
                raise ValueError(f"不支持的订单意图：{intent}")
            if product_type not in (PRODUCT_QUARTERLY, PRODUCT_ANNUAL):
                raise ValueError("仅套餐订单支持升级试用码意图")

        # renewal：目标码归属/类型校验 + 统一定价（不分套餐，2026-07-28 起）
        original_price: Optional[int] = None
        order_meta: Optional[Dict[str, Any]] = None
        if product_type == PRODUCT_RENEWAL:
            cls._validate_renewal_target(user_id, target_code or "")
            original_price = settings.RENEWAL_PRICE
            order_meta = {"target_code": (target_code or "").strip().upper()}

        # consultation：前置校验——至少持有一份已完成且审核通过的报告（ADR-0008）
        if product_type == PRODUCT_CONSULTATION:
            from app.services.consultation_service import ConsultationService

            if not ConsultationService.user_has_completed_report(user_id):
                raise ValueError("报告解读咨询需至少持有一份已完成的报告，请先完成探索流程")

        if intent:
            order_meta = dict(order_meta or {})
            order_meta["intent"] = intent

        async with AsyncSessionLocal() as db:
            user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if not user:
                raise ValueError("用户不存在")

            # 券校验（lock 在订单落库后）
            coupon: Optional[Coupon] = None
            if coupon_code:
                coupon = await CouponService.validate_coupon(coupon_code)

            original, discount, paid = cls.compute_amounts(
                user,
                product_type=product_type,
                coupon_amount=coupon.amount if coupon else 0,
                original_price=original_price,
            )

            # 非 0 元单：先解析渠道（未配置抛 RuntimeError，不产生任何 DB 写入）
            pay_channel = None
            if paid > 0:
                pay_channel = get_channel(channel)

            # 订单落库（order_no 唯一冲突重试）
            order = await cls._insert_order(
                db,
                user_id=user_id,
                product_type=product_type,
                channel=channel,
                coupon_id=coupon.id if coupon else None,
                amount_original=original,
                amount_discount=discount,
                amount_paid=paid,
                meta=json.dumps(order_meta, ensure_ascii=False) if order_meta else None,
            )

        # 锁券（下单即锁定）；失败则删除刚创建的 pending 订单
        if coupon is not None:
            try:
                await CouponService.lock_coupon(coupon.code, order.id)
            except ValueError:
                await cls._delete_order(order.id)
                raise

        # 0 元单：不调渠道，直接交付
        if paid == 0:
            order = await cls._deliver_order(order.id)
            return order, None

        # 调渠道下单（page.pay），跳转 URL 存 qr_code 列
        pay_url = await pay_channel.create_order(
            order_no=order.order_no,
            amount_fen=paid,
            subject=_product_name(product_type),
        )
        async with AsyncSessionLocal() as db:
            row = await cls._get_order_or_raise(db, order.id)
            row.qr_code = pay_url
            await db.commit()
            await db.refresh(row)
            return row, {"channel": channel, "pay_url": pay_url}

    @classmethod
    async def _insert_order(cls, db, **fields) -> PaymentOrder:
        """插入订单，order_no 唯一冲突重试"""
        last_error: Optional[Exception] = None
        for _ in range(_MAX_ORDER_NO_RETRIES):
            order = PaymentOrder(order_no=cls._generate_order_no(), **fields)
            db.add(order)
            try:
                await db.commit()
                await db.refresh(order)
                return order
            except Exception as e:  # 唯一索引冲突等
                await db.rollback()
                last_error = e
                logger.warning("insert payment order failed, retrying: %s", e)
        raise ValueError(f"订单号生成冲突次数过多，请重试（{last_error}）")

    @staticmethod
    async def _delete_order(order_id: str) -> None:
        """删除订单行（仅用于下单锁券失败的回滚）"""
        async with AsyncSessionLocal() as db:
            order = (
                await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
            ).scalar_one_or_none()
            if order:
                await db.delete(order)
                await db.commit()

    # ─── 支付成功交付（幂等）─────────────────────────────────────

    @classmethod
    async def _deliver_order(
        cls,
        order_id: str,
        paid_at: Optional[datetime] = None,
        channel_transaction_id: Optional[str] = None,
    ) -> PaymentOrder:
        """支付成功交付：发码 → 写订单 → 核销券 → 邮件备份

        幂等：已 granted 直接返回（重复回调不重复发码）。
        notify 与 0 元单复用本函数。

        Raises:
            OrderNotFoundError: 订单不存在
            ValueError: 订单状态不允许交付（如已关单/取消/退款）
        """
        async with AsyncSessionLocal() as db:
            order = await cls._get_order_or_raise(db, order_id)
            if order.status == "granted":
                return order
            if order.status not in ("pending", "paid"):
                logger.critical(
                    "支付交付被拒绝：订单状态不允许（order_no=%s status=%s），需人工核查",
                    order.order_no,
                    order.status,
                )
                raise ValueError(f"订单状态不允许交付（当前状态：{order.status}）")

            product_type = order.product_type
            meta = cls._parse_meta(order.meta)
            user_id = order.user_id
            user_email = (
                await db.execute(select(User.email).where(User.id == user_id))
            ).scalar_one_or_none()

            # 按商品类型分派交付（ADR-0008）
            if product_type in (PRODUCT_QUARTERLY, PRODUCT_ANNUAL):
                delivered_code, meta = cls._deliver_package(order, meta, user_email)
            elif product_type == PRODUCT_RENEWAL:
                delivered_code, meta = cls._deliver_renewal(order, meta)
            elif product_type == PRODUCT_CONSULTATION:
                delivered_code, meta = await cls._deliver_consultation(db, order, meta)
            else:  # 旧 SKU 历史订单兼容（已下架）
                record = _activation_manager().create_activation(
                    mode="combined",
                    ttl_minutes=settings.ACTIVATION_CODE_TTL_DAYS * 24 * 60,
                )
                delivered_code = record.code

            order.delivered_code = delivered_code
            if meta:
                order.meta = json.dumps(meta, ensure_ascii=False)
            # 年度套餐（3 码）：站内信提示团队分析报告申请方式（随订单提交，交付幂等故仅一次）
            if product_type == PRODUCT_ANNUAL:
                db.add(
                    Notification(
                        user_id=user_id,
                        type=NOTIFY_TYPE_TEAM_ANALYSIS,
                        title=NOTIFY_TITLE_TEAM_ANALYSIS,
                        content=_team_analysis_notice(),
                        read_at=None,
                        related_feedback_id=None,
                    )
                )
            order.status = "granted"
            order.paid_at = paid_at or _utcnow()
            if channel_transaction_id and not order.channel_transaction_id:
                order.channel_transaction_id = channel_transaction_id
            await db.commit()
            await db.refresh(order)
            coupon_id = order.coupon_id
            order_id_ = order.id

        # 核销券（失败不阻断交付，告警人工核查）
        if coupon_id:
            try:
                await CouponService.redeem_coupon(coupon_id, user_id, order_id_)
            except ValueError as e:
                logger.error(
                    "券核销失败（订单已发码，需人工核查）：order=%s coupon=%s err=%s",
                    order_id_,
                    coupon_id,
                    e,
                )

        # 邮件备份（失败仅记日志）
        await cls._send_delivery_email(user_id, product_type, delivered_code, meta, user_email)
        return order

    # ─── 交付分支（P-B）─────────────────────────────────────────

    @staticmethod
    def _parse_meta(raw: Optional[str]) -> Dict[str, Any]:
        """订单 meta JSON → dict（容错）"""
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    @classmethod
    def _deliver_package(
        cls, order: PaymentOrder, meta: Dict[str, Any], user_email: Optional[str]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """季度/年度套餐交付（ADR-0014）：一律发未绑定完整码（季度 1 个 / 年度 3 个）

        - 不再自动升级试用码、不再自动绑定购买者；码全部未绑定，用户自行
          激活自用 / 转赠 / 消耗升级试用码（POST /simple-auth/codes/apply-to-trial）
        - intent=upgrade_trial（试用拦截点直购，用户主动发起）且用户有 active
          试用码：发码后立即消耗 1 个码原地升级试用码（同一代码路径，审计完整）
        - 有效期自支付成功（交付）时刻起算（ADR-0018）：交付时所有码
          expires_at = now + 套餐天数，未绑定/转赠码同样倒计时；
          存量未激活码（expires_at=None）仍由 maybe_start_validity 首次对话时落地
        """
        package_type = "quarterly" if order.product_type == PRODUCT_QUARTERLY else "annual"
        days = _package_days(package_type)
        mgr = _activation_manager()
        user_id = order.user_id
        meta = dict(meta or {})

        count = 1 if order.product_type == PRODUCT_QUARTERLY else 3
        codes: List[str] = []
        for _ in range(count):
            rec = mgr.create_activation(
                mode="combined",
                ttl_minutes=days * 24 * 60,  # 支付成功（交付）即起算有效期
                code_type="full",
                vip_level=2,
                package_type=package_type,
            )
            mgr.set_purchase_source(
                rec.code, source_order_id=order.id, purchaser_user_id=user_id
            )
            codes.append(rec.code)
        meta["codes"] = codes
        logger.info("套餐未绑定码已生成：order=%s codes=%s", order.order_no, codes)

        # 直购升级（试用拦截点用户主动发起）：发码后立即消耗 1 个码升级试用码
        if (meta.get("intent") or "").strip() == INTENT_UPGRADE_TRIAL:
            from app.utils.trial_codes import get_active_trial_code_for_user

            trial = get_active_trial_code_for_user(user_id)
            if trial is not None:
                consumed_code = codes[0]
                consumed_rec = mgr.consume_for_trial_upgrade(
                    consumed_code, trial.code, actor={"user_id": user_id}
                )
                mgr.upgrade_to_full(
                    trial.code,
                    package_type,
                    days,
                    expires_at=getattr(consumed_rec, "expires_at", None),
                    source_order_id=order.id,
                    purchaser_user_id=user_id,
                    actor={"user_id": user_id},
                )
                meta["auto_upgraded"] = True
                logger.info(
                    "直购升级完成：order=%s consumed=%s trial=%s",
                    order.order_no,
                    consumed_code,
                    trial.code,
                )

        return codes[0], meta

    @classmethod
    def _deliver_renewal(
        cls, order: PaymentOrder, meta: Dict[str, Any]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """延期激活交付：目标码有效期从 max(当前到期, now) 追加统一延期时长（不分套餐）"""
        meta = dict(meta or {})
        target_code = (meta.get("target_code") or "").strip().upper()
        if not target_code:
            raise ValueError("延期订单缺少 target_code，需人工核查")
        mgr, rec = get_activation_with_manager(target_code)
        if rec is None:
            raise ValueError("延期目标码不存在，需人工核查")
        days = settings.RENEWAL_DAYS
        mgr.extend_validity(target_code, days, actor={"user_id": order.user_id})
        meta["added_days"] = days
        return target_code, meta

    @classmethod
    async def _deliver_consultation(
        cls, db, order: PaymentOrder, meta: Dict[str, Any]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """咨询交付：生成预约单（pending_survey），meta 记录 booking_id"""
        meta = dict(meta or {})
        booking = ConsultationBooking(
            order_id=order.id, user_id=order.user_id, status="pending_survey"
        )
        db.add(booking)
        await db.flush()
        meta["booking_id"] = booking.id
        logger.info("咨询预约单已生成：order=%s booking=%s", order.order_no, booking.id)
        return None, meta

    @staticmethod
    async def _send_delivery_email(
        user_id: str,
        product_type: str,
        delivered_code: Optional[str],
        meta: Dict[str, Any],
        user_email: Optional[str],
    ) -> None:
        """支付成功交付邮件（按商品类型；纯文本，失败仅记日志）"""
        try:
            email = user_email
            if not email:
                async with AsyncSessionLocal() as db:
                    email = (
                        await db.execute(select(User.email).where(User.id == user_id))
                    ).scalar_one_or_none()
            if not email:
                logger.warning("交付邮件跳过：用户 %s 无邮箱", user_id)
                return

            frontend = settings.FRONTEND_URL
            if product_type in (PRODUCT_QUARTERLY, PRODUCT_ANNUAL):
                days = _package_days(
                    "quarterly" if product_type == PRODUCT_QUARTERLY else "annual"
                )
                codes = list((meta or {}).get("codes") or [])
                if not codes and delivered_code:
                    codes = [delivered_code] + list((meta or {}).get("gift_codes") or [])
                auto_upgraded = bool((meta or {}).get("auto_upgraded"))
                lines = [
                    "您好，",
                    "",
                    "感谢您的购买，您的激活码已就绪：",
                    "",
                ]
                if auto_upgraded:
                    lines += [
                        "您的试用码已升级为完整版（对话记录完整保留，继续使用原激活码即可）。",
                    ]
                    remaining = codes[1:]
                    if remaining:
                        lines += ["", "其余激活码（未绑定，可自行激活或转送朋友）："]
                        lines += [f"  - {c}" for c in remaining]
                    lines += [
                        "",
                        f"每码有效期：{days} 天（自购买成功起算）",
                    ]
                else:
                    lines += ["激活码（未绑定，可自行激活、转送朋友，或用于升级您的试用码）："]
                    lines += [f"  - {c}" for c in codes]
                    lines += [
                        "",
                        f"每码有效期：{days} 天（自购买成功起算）",
                        f"激活入口：{frontend}/explore/activate",
                    ]
                lines += [
                    "",
                    "请妥善保管本邮件；也可在「个人空间 - 我的激活码」中随时查看。",
                ]
                if product_type == PRODUCT_ANNUAL:
                    lines += ["", _team_analysis_notice()]
                lines += [
                    "",
                    "—— 寻路·OpenLife",
                ]
                subject = "【寻路·OpenLife】您的激活码"
                body = "\n".join(lines)
            elif product_type == PRODUCT_RENEWAL:
                subject = "【寻路·OpenLife】延期激活成功"
                body = (
                    "您好，\n\n"
                    f"您的激活码 {delivered_code} 已成功延期 "
                    f"{(meta or {}).get('added_days', '')} 天。\n"
                    "可在「个人空间 - 我的激活码」中查看新的有效期。\n\n"
                    "—— 寻路·OpenLife"
                )
            elif product_type == PRODUCT_CONSULTATION:
                subject = "【寻路·OpenLife】报告解读咨询购买成功"
                body = (
                    "您好，\n\n"
                    "感谢您的购买。请前往填写预约问卷（想探讨的主题、方便的时间段、联系方式），"
                    "我们会尽快与您确认咨询时间：\n\n"
                    f"{frontend}/dashboard/consultation\n\n"
                    "—— 寻路·OpenLife"
                )
            else:  # 旧 SKU 历史订单
                ttl_days = settings.ACTIVATION_CODE_TTL_DAYS
                activate_url = f"{frontend}/explore/activate?code={delivered_code}"
                subject = "【寻路·OpenLife】您的全程激活码"
                body = (
                    "您好，\n\n"
                    "感谢您的购买，您的全程激活码如下：\n\n"
                    f"激活码：{delivered_code}\n"
                    f"有效期：{ttl_days} 天（自发放之日起）\n"
                    f"激活入口：{activate_url}\n\n"
                    "请妥善保管本邮件；也可在「个人空间 - 我的激活码」中随时查看。\n\n"
                    "—— 寻路·OpenLife"
                )

            await EmailService.send_email(to_email=email, subject=subject, body_text=body)
        except Exception as e:
            logger.error("交付邮件发送失败（不影响交付）：user=%s err=%s", user_id, e)

    # ─── 支付宝回调处理 ─────────────────────────────────────────

    @classmethod
    async def handle_alipay_notify(cls, form: Dict[str, str]) -> None:
        """处理支付宝异步通知：验签 → 查单 → 校验金额 → 幂等交付

        仅 TRADE_SUCCESS / TRADE_FINISHED 触发交付；其余状态确认收到不处理。

        Raises:
            RuntimeError: 渠道未配置
            NotifyVerifyError: 验签失败
            ValueError: 订单不存在 / 金额不符 / 状态不允许交付
        """
        channel = get_channel("alipay")
        notify = await channel.verify_notify(form)

        if notify.trade_status not in _ALIPAY_PAID_STATUSES:
            logger.info(
                "alipay notify ignored (trade_status=%s, order_no=%s)",
                notify.trade_status,
                notify.order_no,
            )
            return

        async with AsyncSessionLocal() as db:
            order = (
                await db.execute(
                    select(PaymentOrder).where(PaymentOrder.order_no == notify.order_no)
                )
            ).scalar_one_or_none()
        if not order:
            raise ValueError(f"回调订单不存在：{notify.order_no}")

        if notify.total_amount_fen != order.amount_paid:
            logger.critical(
                "支付回调金额不符，拒绝交付并告警：order_no=%s notify=%d order=%d",
                notify.order_no,
                notify.total_amount_fen,
                order.amount_paid,
            )
            raise ValueError("回调金额与订单实付不符")

        await cls._deliver_order(
            order.id,
            paid_at=notify.paid_at,
            channel_transaction_id=notify.channel_transaction_id,
        )

    # ─── 主动查单对账（notify 兜底）─────────────────────────────

    @classmethod
    async def reconcile_pending_orders(cls) -> int:
        """主动查单补交付（APScheduler 每 2 分钟调用）

        异步回调 notify 偶发不到达时，对「已向渠道下单」的 pending 订单
        （创建满 3 分钟，避开正常支付窗口）主动调渠道查单；渠道侧已支付
        且金额一致 → 幂等交付。单笔异常仅记日志，不影响其余订单，整体不抛。

        Returns:
            本轮补交付的订单数
        """
        threshold = (_utcnow() - timedelta(minutes=3)).replace(tzinfo=None)
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(PaymentOrder).where(
                            PaymentOrder.status == "pending",
                            PaymentOrder.channel == "alipay",
                            PaymentOrder.amount_paid > 0,
                            PaymentOrder.qr_code.isnot(None),
                            PaymentOrder.created_at < threshold,
                        )
                    )
                )
                .scalars()
                .all()
            )
            # 提取所需字段，避免会话关闭后访问延迟属性
            candidates = [(o.id, o.order_no, o.amount_paid, o.channel) for o in rows]

        delivered = 0
        for order_id, order_no, amount_paid, channel_name in candidates:
            try:
                channel = get_channel(channel_name)
                result = await channel.query_order(order_no)
                if result is None:
                    continue  # 渠道无此单，跳过
                if result.trade_status not in _ALIPAY_PAID_STATUSES:
                    continue  # WAIT_BUYER_PAY 等未支付状态，跳过
                if result.total_amount_fen != amount_paid:
                    logger.critical(
                        "对账查单金额不符，跳过交付并告警：order_no=%s query=%d order=%d",
                        order_no,
                        result.total_amount_fen,
                        amount_paid,
                    )
                    continue
                await cls._deliver_order(
                    order_id,
                    paid_at=result.paid_at,
                    channel_transaction_id=result.channel_transaction_id,
                )
                delivered += 1
                logger.info("对账补交付成功：order_no=%s", order_no)
            except Exception as e:
                logger.error("对账查单失败（跳过本笔）：order_no=%s err=%s", order_no, e)
        if delivered:
            logger.info("对账补交付 %d 笔", delivered)
        return delivered

    # ─── 用户侧查询 ─────────────────────────────────────────────

    @classmethod
    async def _sync_order_from_channel(cls, order: PaymentOrder) -> None:
        """即时主动查单（sync 查询用）：pending 订单向渠道查单，已支付则幂等交付

        仅处理 pending 且已向渠道下单（qr_code 非空）的订单；同一订单 10 秒
        冷却期内不重复查渠道（无论成败都更新冷却时间，防刷）。
        金额不符记 critical；渠道无单/未支付/异常均忽略（仅记日志，不抛）。
        """
        if order.status != "pending" or not order.qr_code:
            return
        now = time.monotonic()
        if now - _ORDER_SYNC_COOLDOWN.get(order.order_no, 0.0) < _SYNC_COOLDOWN_SECONDS:
            return
        _ORDER_SYNC_COOLDOWN[order.order_no] = now
        if len(_ORDER_SYNC_COOLDOWN) > 10000:  # 防御：避免冷却字典无限增长
            _ORDER_SYNC_COOLDOWN.clear()
        try:
            channel = get_channel(order.channel)
            result = await channel.query_order(order.order_no)
        except Exception as e:
            logger.warning("即时查单失败（忽略）：order_no=%s err=%s", order.order_no, e)
            return
        if result is None or result.trade_status not in _ALIPAY_PAID_STATUSES:
            return
        if result.total_amount_fen != order.amount_paid:
            logger.critical(
                "即时查单金额不符，跳过交付并告警：order_no=%s query=%d order=%d",
                order.order_no,
                result.total_amount_fen,
                order.amount_paid,
            )
            return
        await cls._deliver_order(
            order.id,
            paid_at=result.paid_at,
            channel_transaction_id=result.channel_transaction_id,
        )
        logger.info("即时查单补交付成功：order_no=%s", order.order_no)

    @staticmethod
    async def _get_order_or_raise(db, order_id: str) -> PaymentOrder:
        order = (
            await db.execute(select(PaymentOrder).where(PaymentOrder.id == order_id))
        ).scalar_one_or_none()
        if not order:
            raise OrderNotFoundError("订单不存在")
        return order

    @classmethod
    async def list_user_orders(
        cls, user_id: str, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """我的订单列表（仅当前用户，按创建时间倒序）"""
        async with AsyncSessionLocal() as db:
            base = select(PaymentOrder, Coupon.code).outerjoin(
                Coupon, PaymentOrder.coupon_id == Coupon.id
            )
            count_q = select(func.count()).select_from(PaymentOrder)
            base = base.where(PaymentOrder.user_id == user_id)
            count_q = count_q.where(PaymentOrder.user_id == user_id)

            total = (await db.execute(count_q)).scalar() or 0
            rows = (
                await db.execute(
                    base.order_by(PaymentOrder.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return [cls._order_to_dict(order, coupon_code) for order, coupon_code in rows], total

    @classmethod
    async def get_user_order(
        cls, user_id: str, order_id: str, sync: bool = False
    ) -> Dict[str, Any]:
        """订单详情（仅本人）；pending 时返回存储的支付跳转 URL 供继续支付

        Args:
            sync: True 时先向渠道即时查单补交付（10 秒冷却防刷），再返回最新状态

        Returns:
            {"order": OrderItem, "pay_url": str | None}

        Raises:
            OrderNotFoundError: 订单不存在或非本人
        """
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(PaymentOrder, Coupon.code)
                    .outerjoin(Coupon, PaymentOrder.coupon_id == Coupon.id)
                    .where(PaymentOrder.id == order_id)
                )
            ).first()
            if not row or row[0].user_id != user_id:
                raise OrderNotFoundError("订单不存在")
            order, coupon_code = row
            if sync:
                await cls._sync_order_from_channel(order)
                await db.refresh(order)  # sync 可能已触发交付，重取最新数据
            return {
                "order": cls._order_to_dict(order, coupon_code),
                "pay_url": order.qr_code if order.status == "pending" else None,
            }

    @classmethod
    async def get_order_by_no(
        cls, user_id: str, order_no: str, sync: bool = False
    ) -> Dict[str, Any]:
        """按商户订单号查订单详情（仅本人）；结构与 get_user_order 相同

        Args:
            sync: True 时先向渠道即时查单补交付（10 秒冷却防刷），再返回最新状态

        Returns:
            {"order": OrderItem, "pay_url": str | None}

        Raises:
            OrderNotFoundError: 订单不存在或非本人
        """
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(PaymentOrder, Coupon.code)
                    .outerjoin(Coupon, PaymentOrder.coupon_id == Coupon.id)
                    .where(PaymentOrder.order_no == order_no)
                )
            ).first()
            if not row or row[0].user_id != user_id:
                raise OrderNotFoundError("订单不存在")
            order, coupon_code = row
            if sync:
                await cls._sync_order_from_channel(order)
                await db.refresh(order)  # sync 可能已触发交付，重取最新数据
            return {
                "order": cls._order_to_dict(order, coupon_code),
                "pay_url": order.qr_code if order.status == "pending" else None,
            }

    # ─── 取消与超时关单 ─────────────────────────────────────────

    @classmethod
    async def cancel_order(cls, user_id: str, order_id: str) -> PaymentOrder:
        """主动取消（仅本人 pending）：尝试渠道关单（失败不阻断）→ 释放券 → cancelled

        Raises:
            OrderNotFoundError: 订单不存在或非本人
            ValueError: 非 pending 不可取消
        """
        async with AsyncSessionLocal() as db:
            order = await cls._get_order_or_raise(db, order_id)
            if order.user_id != user_id:
                raise OrderNotFoundError("订单不存在")
            if order.status != "pending":
                raise ValueError(f"仅待支付订单可取消（当前状态：{order.status}）")
            coupon_id = order.coupon_id
            await cls._close_channel_order(order)
            order.status = "cancelled"
            await db.commit()
            await db.refresh(order)

        await cls._release_coupon_safe(coupon_id)
        return order

    @classmethod
    async def close_timeout_orders(cls) -> int:
        """关闭超时 pending 订单（APScheduler 每 5 分钟调用）

        pending 且 created_at 早于 ORDER_TIMEOUT_MINUTES 前 → 尝试渠道关单
        （失败仅记日志）→ 释放券 → status closed。单订单异常不影响其余订单。

        Returns:
            关闭的订单数
        """
        threshold = (_utcnow() - timedelta(minutes=settings.ORDER_TIMEOUT_MINUTES)).replace(
            tzinfo=None
        )
        closed = 0
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(PaymentOrder).where(
                            PaymentOrder.status == "pending",
                            PaymentOrder.created_at < threshold,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for order in rows:
                try:
                    await cls._close_channel_order(order)
                    coupon_id = order.coupon_id
                    order.status = "closed"
                    order.closed_at = _utcnow()
                    await db.commit()
                    closed += 1
                    await cls._release_coupon_safe(coupon_id)
                except Exception as e:
                    await db.rollback()
                    logger.error("关闭超时订单失败：order_no=%s err=%s", order.order_no, e)
        if closed:
            logger.info("关闭超时订单 %d 笔", closed)
        return closed

    @classmethod
    async def close_pending_orders_for_user(cls, user_id: str) -> int:
        """关闭某用户全部 pending 订单（账户注销时调用）

        复用超时关单逻辑：尝试渠道关单（失败仅记日志）→ 释放券 → status closed。
        单订单异常不影响其余订单。

        Returns:
            关闭的订单数
        """
        closed = 0
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(PaymentOrder).where(
                            PaymentOrder.user_id == user_id,
                            PaymentOrder.status == "pending",
                        )
                    )
                )
                .scalars()
                .all()
            )
            for order in rows:
                try:
                    await cls._close_channel_order(order)
                    coupon_id = order.coupon_id
                    order.status = "closed"
                    order.closed_at = _utcnow()
                    await db.commit()
                    closed += 1
                    await cls._release_coupon_safe(coupon_id)
                except Exception as e:
                    await db.rollback()
                    logger.error(
                        "注销关单失败：order_no=%s err=%s", order.order_no, e
                    )
        if closed:
            logger.info("账户注销关闭 pending 订单 %d 笔：user_id=%s", closed, user_id)
        return closed

    @staticmethod
    async def _close_channel_order(order: PaymentOrder) -> None:
        """尝试渠道关单（仅对已向渠道预下单的订单；失败仅记日志不阻断）"""
        if not order.qr_code or not order.channel:
            return
        try:
            channel = get_channel(order.channel)
            await channel.close_order(order.order_no)
        except Exception as e:
            logger.warning("渠道关单失败（不阻断本地关单）：order_no=%s err=%s", order.order_no, e)

    @staticmethod
    async def _release_coupon_safe(coupon_id: Optional[str]) -> None:
        """释放券（防御性：失败仅记日志）"""
        if not coupon_id:
            return
        try:
            await CouponService.release_coupon(coupon_id)
        except ValueError as e:
            logger.warning("释放券失败：coupon=%s err=%s", coupon_id, e)

    # ─── Admin：订单列表 / 详情 / 退款 ──────────────────────────

    @classmethod
    async def admin_list_orders(
        cls,
        status: Optional[str] = None,
        channel: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Admin 订单列表（状态/渠道筛选 + 分页，item 含 user_email + code_refundable）"""
        async with AsyncSessionLocal() as db:
            base = (
                select(PaymentOrder, Coupon.code, User.email)
                .outerjoin(Coupon, PaymentOrder.coupon_id == Coupon.id)
                .join(User, PaymentOrder.user_id == User.id)
            )
            count_q = select(func.count()).select_from(PaymentOrder)
            if status:
                base = base.where(PaymentOrder.status == status)
                count_q = count_q.where(PaymentOrder.status == status)
            if channel:
                base = base.where(PaymentOrder.channel == channel)
                count_q = count_q.where(PaymentOrder.channel == channel)

            total = (await db.execute(count_q)).scalar() or 0
            rows = (
                await db.execute(
                    base.order_by(PaymentOrder.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()

            items = []
            for order, coupon_code, user_email in rows:
                item = cls._order_to_dict(order, coupon_code)
                item["user_email"] = user_email
                item["code_refundable"] = cls._order_refundable(order)
                items.append(item)
            return items, total

    @classmethod
    async def admin_get_order(cls, order_id: str) -> Dict[str, Any]:
        """Admin 订单详情（完整字段 + user_email + code_refundable）

        Raises:
            OrderNotFoundError: 订单不存在
        """
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(PaymentOrder, Coupon.code, User.email)
                    .outerjoin(Coupon, PaymentOrder.coupon_id == Coupon.id)
                    .join(User, PaymentOrder.user_id == User.id)
                    .where(PaymentOrder.id == order_id)
                )
            ).first()
            if not row:
                raise OrderNotFoundError("订单不存在")
            order, coupon_code, user_email = row
            item = cls._order_to_dict(order, coupon_code)
            item["user_email"] = user_email
            item["code_refundable"] = cls._order_refundable(order)
            # 交付码去向（ADR-0014 消耗去向展示；码值/邮箱不脱敏，仅供 admin 排查）
            item["delivered_codes"] = cls._delivered_codes_with_destination(order)
            return {"order": item}

    @staticmethod
    def _package_order_codes(order: PaymentOrder) -> List[str]:
        """收集套餐订单交付的全部码（新 meta.codes + 兼容旧 gift_codes/delivered_code，去重）"""
        meta = PaymentService._parse_meta(order.meta)
        codes: List[str] = []
        for raw in list(meta.get("codes") or []) + list(meta.get("gift_codes") or []):
            code = (raw or "").strip().upper()
            if code and code not in codes:
                codes.append(code)
        delivered = (order.delivered_code or "").strip().upper()
        if delivered and delivered not in codes:
            codes.append(delivered)
        return codes

    @classmethod
    def _delivered_codes_with_destination(cls, order: PaymentOrder) -> List[Dict[str, Any]]:
        """订单交付码列表 + 去向（admin 订单详情用；码值与邮箱不脱敏）

        destination_type 取值：
        - unknown              激活码记录不存在（含查询异常兜底）
        - revoked / deleted    已作废（退款）/ 已删除，detail 为 None
        - consumed_for_upgrade 已消耗升级试用码，detail=受益试用码完整码值
        - bound_self / bound_other 已绑定（owner==订单购买人 / 他人），detail=激活人邮箱
        - expired              未绑定但已过期
        - unbound              未绑定可用
        """
        result: List[Dict[str, Any]] = []
        for code in cls._package_order_codes(order):
            rec = None
            try:
                _, rec = get_activation_with_manager(code)
            except Exception as e:
                logger.warning("查询交付码去向失败：code=%s err=%s", code, e)
            destination_type = "unknown"
            destination_detail: Optional[str] = None
            rec_status: Optional[str] = None
            upgraded_from_code: Optional[str] = None
            if rec is not None:
                rec_status = rec.status
                upgraded_from_code = getattr(rec, "upgraded_from_code", None)
                owner_uid = getattr(rec, "owner_user_id", None)
                if rec_status == "revoked":
                    destination_type = "revoked"
                elif rec_status == "deleted":
                    destination_type = "deleted"
                elif rec_status == "consumed":
                    destination_type = "consumed_for_upgrade"
                    destination_detail = getattr(rec, "consumed_into", None)
                elif owner_uid:
                    destination_type = (
                        "bound_self" if owner_uid == order.user_id else "bound_other"
                    )
                    destination_detail = getattr(rec, "owner_email", None)
                elif rec_status == "expired":
                    destination_type = "expired"
                else:
                    destination_type = "unbound"
            result.append(
                {
                    "code": code,
                    "status": rec_status,
                    "destination_type": destination_type,
                    "destination_detail": destination_detail,
                    "upgraded_from_code": upgraded_from_code,
                }
            )
        return result

    @classmethod
    def _package_codes_untouched(cls, order: PaymentOrder) -> bool:
        """套餐订单全部交付码是否未被使用（ADR-0014：未被 claim 且未被消耗升级）"""
        meta = cls._parse_meta(order.meta)
        # 旧订单：已自动升级试用码，不可逆，视为已使用
        if meta.get("upgraded") or meta.get("auto_upgraded"):
            return False
        codes = cls._package_order_codes(order)
        if not codes:
            return False
        for code in codes:
            try:
                _, rec = get_activation_with_manager(code)
            except Exception as e:
                logger.warning("查询交付码状态失败：code=%s err=%s", code, e)
                return False
            if rec is None:
                return False
            if rec.owner_user_id or rec.status != "active":
                return False
        return True

    @classmethod
    def _order_refundable(cls, order: PaymentOrder) -> bool:
        """订单交付码是否可退（admin 列表/详情展示用）"""
        if order.product_type in (PRODUCT_QUARTERLY, PRODUCT_ANNUAL):
            return cls._package_codes_untouched(order)
        return cls._code_refundable(order.delivered_code)

    @staticmethod
    def _code_refundable(delivered_code: Optional[str]) -> bool:
        """交付码是否可退：存在、未被任何用户 claim 且状态 active"""
        if not delivered_code:
            return False
        try:
            _, rec = get_activation_with_manager(delivered_code)
        except Exception as e:
            logger.warning("查询交付码状态失败：code=%s err=%s", delivered_code, e)
            return False
        if rec is None:
            return False
        return not rec.owner_user_id and rec.status == "active"

    @classmethod
    async def admin_refund(cls, order_id: str, actor: Optional[dict] = None) -> PaymentOrder:
        """Admin 发起退款（按商品类型守卫）

        - 套餐（quarterly/annual，ADR-0014）：任一交付码被激活（claim）或消耗升级 → 整单不可退；
          全部码未动 → 可退，退款成功作废全部码
        - 延期（renewal）：交付即已用，一律拒绝
        - 咨询（consultation）：仅未预约（pending_survey/submitted）可退，退款后预约单取消
        - 旧 SKU（activation_code）：仅交付码未被 claim 可退，退款成功作废码

        Raises:
            OrderNotFoundError: 订单不存在
            ValueError: 状态不允许 / 不可退款
            RuntimeError: 渠道未配置
            PaymentChannelError: 渠道退款失败
        """
        booking = None
        legacy_code: Optional[str] = None
        legacy_mgr = None
        package_codes: List[str] = []

        async with AsyncSessionLocal() as db:
            order = await cls._get_order_or_raise(db, order_id)
            if order.status != "granted":
                raise ValueError("仅已交付（granted）订单可退款")
            product_type = order.product_type

            if product_type == PRODUCT_RENEWAL:
                raise ValueError("延期订单交付后即已使用，不可退款（请走线下协商）")

            if product_type in (PRODUCT_QUARTERLY, PRODUCT_ANNUAL):
                # ADR-0014：一单多码时任一码被激活/消耗 → 整单不可退
                if not cls._package_codes_untouched(order):
                    raise ValueError(
                        "订单内激活码已被使用或消耗，不可退款（请走线下协商）"
                    )
                package_codes = cls._package_order_codes(order)
            elif product_type == PRODUCT_CONSULTATION:
                booking = (
                    await db.execute(
                        select(ConsultationBooking).where(
                            ConsultationBooking.order_id == order.id
                        )
                    )
                ).scalar_one_or_none()
                if booking is None:
                    raise ValueError("咨询预约单不存在，需人工核查")
                if booking.status not in ("pending_survey", "submitted"):
                    raise ValueError("咨询已预约或已完成，不可退款（请走线下协商）")
            else:
                # 旧 SKU：码未被 claim 才可退
                if not order.delivered_code:
                    raise ValueError("订单无交付激活码，需人工核查")
                legacy_code = order.delivered_code
                legacy_mgr, rec = get_activation_with_manager(legacy_code)
                if rec is None:
                    raise ValueError("交付的激活码不存在，需人工核查")
                if rec.owner_user_id or rec.status != "active":
                    raise ValueError("激活码已被使用，不可退款（请走线下协商）")

            # 调渠道退款（0 元单无真实支付，跳过渠道）
            if order.amount_paid > 0:
                channel = get_channel(order.channel)
                await channel.refund(
                    order_no=order.order_no,
                    amount_fen=order.amount_paid,
                    refund_no=order.order_no + "R",
                )

            order.status = "refunded"
            order.refunded_at = _utcnow()
            if booking is not None:
                booking.status = "cancelled"
            await db.commit()
            await db.refresh(order)

        # 旧 SKU：作废码（update_status 内部写审计 EVENT_STATUS_CHANGED）
        if legacy_code and legacy_mgr:
            changed = legacy_mgr.update_status([legacy_code], "revoked", actor=actor)
            if changed:
                logger.info("退款完成，激活码已作废：order_id=%s code=%s", order_id, legacy_code)
        # 套餐：全部未动码作废
        for code in package_codes:
            try:
                mgr, _rec = get_activation_with_manager(code)
                if mgr:
                    mgr.update_status([code], "revoked", actor=actor)
            except Exception as e:
                logger.error("退款作废套餐码失败（需人工核查）：code=%s err=%s", code, e)
        if package_codes:
            logger.info("退款完成，套餐码已全部作废：order_id=%s codes=%s", order_id, package_codes)
        return order

    # ─── 序列化 ─────────────────────────────────────────────────

    @staticmethod
    def _order_to_dict(order: PaymentOrder, coupon_code: Optional[str] = None) -> Dict[str, Any]:
        """ORM → OrderItem（契约字段）"""

        def iso(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        return {
            "id": order.id,
            "order_no": order.order_no,
            "product_type": order.product_type,
            "quantity": order.quantity,
            "amount_original": order.amount_original,
            "amount_discount": order.amount_discount,
            "amount_paid": order.amount_paid,
            "coupon_code": coupon_code,
            "channel": order.channel,
            "status": order.status,
            "delivered_code": order.delivered_code,
            "channel_transaction_id": order.channel_transaction_id,
            "meta": PaymentService._parse_meta(order.meta) or None,
            "created_at": iso(order.created_at),
            "paid_at": iso(order.paid_at),
            "closed_at": iso(order.closed_at),
            "refunded_at": iso(order.refunded_at),
        }
