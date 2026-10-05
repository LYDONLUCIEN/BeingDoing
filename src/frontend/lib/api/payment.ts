/**
 * 支付模块 API 封装（P1：折扣券 admin 管理；P2a：支付宝支付闭环）
 *
 * 金额单位约定：后端一律使用「分」（整数）；
 * 前端展示元（/100，保留两位），用户输入元（×100 取整提交）。
 */
import { apiClient } from '@/lib/api/client';

// ─── 类型定义 ─────────────────────────────────────────────

export type CouponStatus = 'unused' | 'locked' | 'used' | 'expired' | 'void';

export type CouponSource = 'admin' | 'email_auto';

export interface CouponItem {
  id: string;
  code: string;
  /** 面额（分） */
  amount: number;
  status: CouponStatus;
  source: CouponSource;
  created_at: string;
  used_at?: string | null;
  used_by_email?: string | null;
  used_order_no?: string | null;
  locked_order_no?: string | null;
  /** 有效期（ISO8601，null=不限） */
  expires_at: string | null;
  /** 绑定用户邮箱（null=未绑定） */
  owner_email: string | null;
  /** 作废时间（软删除，null=未作废） */
  voided_at: string | null;
}

export interface CouponListResult {
  items: CouponItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreatedCoupon {
  id: string;
  code: string;
  /** 面额（分） */
  amount: number;
  /** 有效期（ISO8601，null=不限） */
  expires_at?: string | null;
}

/** 用户侧「我的折扣券」单券（GET /payment/my-coupons） */
export interface MyCouponItem {
  code: string;
  /** 面额（分） */
  amount: number;
  /** 有效期（ISO8601，null=不限） */
  expires_at: string | null;
  used_at: string | null;
  used_order_no: string | null;
  source: CouponSource;
}

/** 用户侧「我的折扣券」分组响应（不含已作废和锁定中的券） */
export interface MyCouponsResult {
  available: MyCouponItem[];
  used: MyCouponItem[];
  expired: MyCouponItem[];
}

/** Admin 折扣券全局配置（GET/POST /admin/coupon-config） */
export interface CouponConfig {
  default_ttl_days: number;
  fallback: number;
  min: number;
  max: number;
}

// ─── 金额换算工具 ─────────────────────────────────────────

/** 分 → 元字符串（保留两位小数） */
export function fenToYuan(fen: number): string {
  return (fen / 100).toFixed(2);
}

/** 元（可带小数）→ 分（四舍五入取整） */
export function yuanToFen(yuan: number): number {
  return Math.round(yuan * 100);
}

// ─── Admin 折扣券管理 ─────────────────────────────────────

/** 分页查询折扣券（可按状态/来源筛选） */
export async function listCoupons(params?: {
  status?: CouponStatus;
  source?: CouponSource;
  page?: number;
  page_size?: number;
}): Promise<CouponListResult> {
  const res = await apiClient.get('/admin/coupons', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 20 }) as CouponListResult;
}

/** 批量创建折扣券（定金额，count 1-500），amount 单位：分；ttl_days 不传用全局默认 */
export async function createCoupons(payload: {
  amount: number;
  count: number;
  ttl_days?: number;
}): Promise<{ created: CreatedCoupon[] }> {
  const res = await apiClient.post('/admin/coupons', payload);
  return (res.data ?? { created: [] }) as { created: CreatedCoupon[] };
}

/** 调整面额（仅 unused/expired 状态可改），amount 单位：分 */
export async function updateCouponAmount(id: string, amount: number): Promise<CouponItem> {
  const res = await apiClient.patch(`/admin/coupons/${encodeURIComponent(id)}`, { amount });
  return (res.data ?? {}) as CouponItem;
}

/** 修改有效期（仅 unused/expired 状态可改，改期即复活），expiresAt 为 ISO8601 */
export async function updateCouponExpiry(id: string, expiresAt: string): Promise<CouponItem> {
  const res = await apiClient.patch(`/admin/coupons/${encodeURIComponent(id)}`, {
    expires_at: expiresAt,
  });
  return (res.data ?? {}) as CouponItem;
}

/** 作废折扣券（软删除：unused/expired → void） */
export async function deleteCoupon(id: string): Promise<void> {
  await apiClient.delete(`/admin/coupons/${encodeURIComponent(id)}`);
}

/** 恢复已作废折扣券（void → unused） */
export async function restoreCoupon(id: string): Promise<{ id: string; code: string; status: CouponStatus }> {
  const res = await apiClient.post(`/admin/coupons/${encodeURIComponent(id)}/restore`);
  return (res.data ?? {}) as { id: string; code: string; status: CouponStatus };
}

/** 读取折扣券全局配置（默认有效期天数） */
export async function fetchCouponConfig(): Promise<CouponConfig> {
  const res = await apiClient.get('/admin/coupon-config');
  return (res.data ?? { default_ttl_days: 90, fallback: 90, min: 1, max: 3650 }) as CouponConfig;
}

/** 更新折扣券默认有效期（1-3650 天，即时生效，只影响之后新创建的券） */
export async function updateCouponConfig(defaultTtlDays: number): Promise<CouponConfig> {
  const res = await apiClient.post('/admin/coupon-config', { default_ttl_days: defaultTtlDays });
  return (res.data ?? { default_ttl_days: defaultTtlDays, fallback: 90, min: 1, max: 3650 }) as CouponConfig;
}

// ─── P2a 支付闭环（用户侧） ──────────────────────────────

export type ProductType =
  | 'activation_code' // 旧 SKU（P-B 起下架，历史订单仍可能展示）
  | 'membership_monthly'
  | 'membership_lifetime'
  | 'quarterly_package'
  | 'annual_package'
  | 'renewal'
  | 'consultation';

export type PayChannel = 'alipay' | 'wechat';

/** 支付串展示方式：qr=页面内 iframe 嵌入二维码（支付宝前置模式/微信 Native）；redirect=新窗口跳收银台 */
export type PayType = 'qr' | 'redirect';

export type OrderStatus =
  | 'pending'
  | 'paid'
  | 'granted'
  | 'partially_refunded'
  | 'closed'
  | 'cancelled'
  | 'refunding'
  | 'refunded';

export interface ProductItem {
  product_type: ProductType;
  name: string;
  description: string;
  /** 价格（分） */
  price: number;
  /** 套餐时长（天）；旧 SKU 字段为 ttl_days */
  duration_days?: number;
  /** 旧 SKU 的激活码有效期（天） */
  ttl_days?: number;
  /** 「最受欢迎」标记（季度套餐） */
  popular?: boolean;
  /** 购买前置条件：需有已完成报告（咨询） */
  requires_report?: boolean;
  /** 卖点列表（后端下发；前端展示优先用 i18n） */
  features?: string[];
}

export interface ProductsResult {
  items: ProductItem[];
  /** 会员折扣（百分比，如 85 表示 8.5 折） */
  member_discount_percent: number;
  membership_enabled: boolean;
  /** 团队分析报告联系邮箱（后端 TEAM_ANALYSIS_EMAIL 统一下发） */
  team_analysis_email?: string;
}

export interface OrderItem {
  id: string;
  order_no: string;
  product_type: ProductType;
  quantity: number;
  /** 原价（分） */
  amount_original: number;
  /** 券抵扣（分） */
  amount_discount: number;
  /** 实付（分） */
  amount_paid: number;
  /** 累计成功退款（分） */
  amount_refunded?: number;
  coupon_code?: string | null;
  channel: PayChannel;
  status: OrderStatus;
  delivered_code?: string | null;
  /** 商品特定载荷：renewal {target_code, added_days}；annual {gift_codes}；consultation {booking_id} */
  meta?: OrderMeta | null;
  channel_transaction_id?: string | null;
  created_at: string;
  paid_at?: string | null;
  closed_at?: string | null;
  refunded_at?: string | null;
}

export interface OrderMeta {
  /** 套餐订单交付的全部激活码（ADR-0014，未绑定） */
  codes?: string[];
  /** 年度单交付的赠品码（旧订单兼容字段） */
  gift_codes?: string[];
  /** 直购升级订单：交付时已自动消耗 1 码升级试用码 */
  auto_upgraded?: boolean;
  /** 订单意图（upgrade_trial=试用拦截点直购升级） */
  intent?: string;
  /** 延期目标码 */
  target_code?: string;
  /** 延期追加天数 */
  added_days?: number;
  /** 咨询预约单 ID */
  booking_id?: string;
}

export interface OrderListResult {
  items: OrderItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateOrderResult {
  order: OrderItem;
  /** 0 元单为 null（订单直接 granted）；否则含支付串（qr=iframe 嵌入二维码，redirect=收银台跳转） */
  payment: { channel: PayChannel; pay_type?: PayType; pay_url: string } | null;
}

export interface OrderDetailResult {
  order: OrderItem;
  /** 支付串（仅 pending 订单返回；qr=iframe 嵌入二维码，redirect=收银台跳转） */
  pay_url: string | null;
  pay_type?: PayType | null;
}

/** 商品与价格列表 */
export async function getProducts(): Promise<ProductsResult> {
  const res = await apiClient.get('/payment/products');
  return (res.data ?? { items: [], member_discount_percent: 100, membership_enabled: false }) as ProductsResult;
}

/** 团队分析报告联系邮箱兜底（与后端 settings.TEAM_ANALYSIS_EMAIL 默认值一致） */
export const TEAM_ANALYSIS_EMAIL_FALLBACK = 'soulhappylab@163.com';

let cachedTeamAnalysisEmail: string | null = null;

/**
 * 团队分析报告联系邮箱（模块级缓存；接口失败/未返回时用兜底值）。
 * 后端唯一来源：TEAM_ANALYSIS_EMAIL 环境变量 → GET /payment/products。
 */
export async function getTeamAnalysisEmail(): Promise<string> {
  if (cachedTeamAnalysisEmail) return cachedTeamAnalysisEmail;
  try {
    const res = await getProducts();
    const v = (res.team_analysis_email || '').trim();
    if (v) cachedTeamAnalysisEmail = v;
  } catch {
    /* 接口失败用兜底值 */
  }
  return cachedTeamAnalysisEmail ?? TEAM_ANALYSIS_EMAIL_FALLBACK;
}

/** 校验折扣券（下单前实时校验抵扣金额）；无效/过期/属于他人后端返回 400 */
export async function validateCoupon(
  code: string,
): Promise<{ code: string; amount: number; expires_at: string | null }> {
  const res = await apiClient.post('/payment/coupons/validate', { code });
  return (res.data ?? { code, amount: 0, expires_at: null }) as {
    code: string;
    amount: number;
    expires_at: string | null;
  };
}

/** 我的折扣券（分组：可用 / 已使用 / 已过期；不含已作废和锁定中的券） */
export async function listMyCoupons(): Promise<MyCouponsResult> {
  const res = await apiClient.get('/payment/my-coupons');
  return (res.data ?? { available: [], used: [], expired: [] }) as MyCouponsResult;
}

/** 创建订单（券码在此锁定）；amount 单位：分 */
export async function createOrder(payload: {
  product_type: ProductType;
  channel: PayChannel;
  coupon_code?: string;
  /** renewal 必传：延期目标激活码 */
  target_code?: string;
  /** 订单意图（ADR-0014）：upgrade_trial=试用拦截点直购升级（仅套餐） */
  intent?: 'upgrade_trial';
}): Promise<CreateOrderResult> {
  const res = await apiClient.post('/payment/orders', payload);
  return res.data as CreateOrderResult;
}

/** 我的订单列表（分页） */
export async function listMyOrders(params?: {
  page?: number;
  page_size?: number;
}): Promise<OrderListResult> {
  const res = await apiClient.get('/payment/orders', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 20 }) as OrderListResult;
}

/**
 * 订单详情（pending 订单含收银台跳转 URL）
 * sync=true 时后端先实时调用支付宝查单核实（已付则立即发码），每单 10 秒冷却
 */
export async function getOrder(id: string, sync?: boolean): Promise<OrderDetailResult> {
  const res = await apiClient.get(
    `/payment/orders/${encodeURIComponent(id)}${sync ? '?sync=1' : ''}`,
  );
  return res.data as OrderDetailResult;
}

/**
 * 按订单号查询订单（支付结果页用：支付宝同步回跳带 out_trade_no）
 * sync=true 时后端先实时调用支付宝查单核实（已付则立即发码），每单 10 秒冷却
 */
export async function getOrderByNo(orderNo: string, sync?: boolean): Promise<OrderDetailResult> {
  const res = await apiClient.get(
    `/payment/orders/by-no/${encodeURIComponent(orderNo)}${sync ? '?sync=1' : ''}`,
  );
  return res.data as OrderDetailResult;
}

/** 主动取消订单（释放券） */
export async function cancelOrder(id: string): Promise<{ order: OrderItem }> {
  const res = await apiClient.post(`/payment/orders/${encodeURIComponent(id)}/cancel`);
  return res.data as { order: OrderItem };
}

// ─── P2a Admin 订单管理 ─────────────────────────────────

/** Admin 订单详情的交付码去向（ADR-0014；码值/邮箱不脱敏，仅超管可见） */
export interface AdminDeliveredCode {
  code: string;
  /** 激活码记录当前状态；记录不存在为 null */
  status?: string | null;
  destination_type:
    | 'unbound'
    | 'bound_self'
    | 'bound_other'
    | 'consumed_for_upgrade'
    | 'revoked'
    | 'deleted'
    | 'expired'
    | 'unknown';
  /** bound_* 为激活人邮箱；consumed_for_upgrade 为受益试用码完整码值；其余为 null */
  destination_detail?: string | null;
  /** 消耗升级反向溯源（一般为 null） */
  upgraded_from_code?: string | null;
}

export interface AdminOrderItem extends OrderItem {
  user_email?: string | null;
  /** 交付的激活码是否可退（未使用才可退） */
  code_refundable?: boolean;
  /** 订单交付码列表 + 去向（仅详情接口返回） */
  delivered_codes?: AdminDeliveredCode[];
}

export interface AdminOrderListResult {
  items: AdminOrderItem[];
  total: number;
  page: number;
  page_size: number;
}

/** 订单列表（可按状态/渠道筛选，分页） */
export async function adminListOrders(params?: {
  status?: OrderStatus;
  channel?: PayChannel;
  page?: number;
  page_size?: number;
}): Promise<AdminOrderListResult> {
  const res = await apiClient.get('/admin/payment/orders', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 20 }) as AdminOrderListResult;
}

/** 订单详情 */
export async function adminGetOrder(id: string): Promise<{ order: AdminOrderItem }> {
  const res = await apiClient.get(`/admin/payment/orders/${encodeURIComponent(id)}`);
  return res.data as { order: AdminOrderItem };
}

// ===================== 退款（2026-10-05 统一申请单）=====================

export type RefundType = 'full' | 'partial';

export type RefundStatus =
  | 'pending_review'
  | 'refunding'
  | 'succeeded'
  | 'failed'
  | 'rejected'
  | 'withdrawn';

/** 订单明细行（优惠分摊口径；item_type=code 时 item_ref 为激活码） */
export interface RefundLineItem {
  id: string;
  line_no: number;
  item_type: 'code' | 'consultation_service' | 'renewal_service';
  item_ref: string | null;
  /** 该行分摊实付（分，退款上限） */
  amount_paid_alloc: number;
  /** 实时有效状态：available 可退 / used 已被用 / refunded 已退 */
  effective_status: 'available' | 'used' | 'refunded';
}

/** 退款能力视图 */
export interface RefundOptions {
  order: {
    id: string;
    order_no: string;
    product_type: ProductType;
    amount_paid: number;
    amount_refunded: number;
    status: OrderStatus;
  };
  full_allowed: boolean;
  partial_allowed: boolean;
  /** 套餐部分退按所选码折算；咨询部分退走 admin 协商金额 */
  partial_by_lines: boolean;
  remaining_refundable: number;
  lines: RefundLineItem[];
  pending_request: RefundItem | null;
  history: RefundItem[];
}

/** 退款单（审批留痕全量可见） */
export interface RefundItem {
  id: string;
  refund_no: string;
  order_id: string;
  order_no: string;
  user_id: string;
  originated: 'user' | 'admin';
  created_by_admin?: string | null;
  refund_type: RefundType;
  /** 申请金额（分） */
  requested_amount: number;
  /** 批准金额（分，= 执行金额） */
  approved_amount?: number | null;
  reason_user?: string | null;
  reason_admin?: string | null;
  status: RefundStatus;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  executed_at?: string | null;
  succeeded_at?: string | null;
  failed_reason?: string | null;
  line_snapshot?: Array<{
    line_id: string;
    line_no: number;
    item_type: string;
    item_ref: string | null;
    amount_paid_alloc: number;
  }> | null;
  created_at: string;
  updated_at?: string | null;
  /** admin 列表附带 */
  user_email?: string;
}

export interface RefundListResult {
  items: RefundItem[];
  total: number;
  page: number;
  page_size: number;
}

/** 订单退款能力视图（行级分摊 + 可退性） */
export async function fetchRefundOptions(orderId: string): Promise<RefundOptions> {
  const res = await apiClient.get(
    `/payment/orders/${encodeURIComponent(orderId)}/refund-options`
  );
  return res.data as RefundOptions;
}

/** 提交退款申请（全退/部分退；金额按规则计算） */
export async function createRefundRequest(
  orderId: string,
  payload: { refund_type: RefundType; line_ids?: string[]; reason: string }
): Promise<{ refund: RefundItem }> {
  const res = await apiClient.post(
    `/payment/orders/${encodeURIComponent(orderId)}/refund-requests`,
    payload
  );
  return res.data as { refund: RefundItem };
}

/** 我的退款申请列表 */
export async function listMyRefunds(params?: {
  page?: number;
  page_size?: number;
}): Promise<RefundListResult> {
  const res = await apiClient.get('/payment/refund-requests', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 20 }) as RefundListResult;
}

/** 撤回退款申请（仅待审批） */
export async function withdrawRefund(id: string): Promise<{ refund: RefundItem }> {
  const res = await apiClient.post(`/payment/refund-requests/${encodeURIComponent(id)}/withdraw`);
  return res.data as { refund: RefundItem };
}

// ─── Admin：退款审批 ──────────────────────────────────────────

/** admin 退款单列表（状态/订单号筛选） */
export async function adminListRefunds(params?: {
  status?: RefundStatus;
  order_no?: string;
  page?: number;
  page_size?: number;
}): Promise<RefundListResult> {
  const res = await apiClient.get('/admin/payment/refunds', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 20 }) as RefundListResult;
}

/** admin 退款单详情（含订单信息 + 实时行状态） */
export async function adminGetRefund(
  id: string
): Promise<RefundItem & {
  order: {
    id: string;
    order_no: string;
    product_type: ProductType;
    amount_paid: number;
    amount_refunded: number;
    status: OrderStatus;
    coupon_id: string | null;
  };
  order_lines: Array<RefundLineItem & { db_status: string }>;
}> {
  const res = await apiClient.get(`/admin/payment/refunds/${encodeURIComponent(id)}`);
  return res.data as ReturnType<typeof adminGetRefund>;
}

/** admin 代录退款申请（线下协商场景） */
export async function adminCreateRefund(
  payload: {
    order_id: string;
    refund_type: RefundType;
    amount?: number;
    line_ids?: string[];
    reason: string;
    note?: string;
  }
): Promise<{ refund: RefundItem }> {
  const res = await apiClient.post('/admin/payment/refunds', payload);
  return res.data as { refund: RefundItem };
}

/** 批准并执行退款（approved_amount 不传 = 申请额；与申请额不一致必填 note） */
export async function adminApproveRefund(
  id: string,
  payload: { approved_amount?: number; note?: string }
): Promise<{ refund: RefundItem }> {
  const res = await apiClient.post(
    `/admin/payment/refunds/${encodeURIComponent(id)}/approve`,
    payload
  );
  return res.data as { refund: RefundItem };
}

/** 驳回（必填理由，用户可见） */
export async function adminRejectRefund(
  id: string,
  note: string
): Promise<{ refund: RefundItem }> {
  const res = await apiClient.post(
    `/admin/payment/refunds/${encodeURIComponent(id)}/reject`,
    { note }
  );
  return res.data as { refund: RefundItem };
}

/** 失败重试（同 refund_no 渠道幂等） */
export async function adminRetryRefund(id: string): Promise<{ refund: RefundItem }> {
  const res = await apiClient.post(`/admin/payment/refunds/${encodeURIComponent(id)}/retry`);
  return res.data as { refund: RefundItem };
}
