/**
 * 支付模块 API 封装（P1：折扣券 admin 管理；P2a：支付宝支付闭环）
 *
 * 金额单位约定：后端一律使用「分」（整数）；
 * 前端展示元（/100，保留两位），用户输入元（×100 取整提交）。
 */
import { apiClient } from '@/lib/api/client';

// ─── 类型定义 ─────────────────────────────────────────────

export type CouponStatus = 'unused' | 'locked' | 'used';

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

/** 批量创建折扣券（定金额，count 1-500），amount 单位：分 */
export async function createCoupons(payload: {
  amount: number;
  count: number;
}): Promise<{ created: CreatedCoupon[] }> {
  const res = await apiClient.post('/admin/coupons', payload);
  return (res.data ?? { created: [] }) as { created: CreatedCoupon[] };
}

/** 调整面额（仅 unused 状态可改），amount 单位：分 */
export async function updateCouponAmount(id: string, amount: number): Promise<CouponItem> {
  const res = await apiClient.patch(`/admin/coupons/${encodeURIComponent(id)}`, { amount });
  return (res.data ?? {}) as CouponItem;
}

/** 作废折扣券（仅 unused 状态可删） */
export async function deleteCoupon(id: string): Promise<void> {
  await apiClient.delete(`/admin/coupons/${encodeURIComponent(id)}`);
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

export type OrderStatus =
  | 'pending'
  | 'paid'
  | 'granted'
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
  /** 「最受欢迎」标记（三人包） */
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
  /** 年度单交付的赠品码（可转送朋友） */
  gift_codes?: string[];
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
  /** 0 元单为 null（订单直接 granted）；否则含支付宝收银台跳转 URL（page.pay） */
  payment: { channel: PayChannel; pay_url: string } | null;
}

export interface OrderDetailResult {
  order: OrderItem;
  /** 支付宝收银台跳转 URL（仅 pending 订单返回） */
  pay_url: string | null;
}

/** 商品与价格列表 */
export async function getProducts(): Promise<ProductsResult> {
  const res = await apiClient.get('/payment/products');
  return (res.data ?? { items: [], member_discount_percent: 100, membership_enabled: false }) as ProductsResult;
}

/** 校验折扣券（下单前实时校验抵扣金额）；无效券后端返回 400 */
export async function validateCoupon(code: string): Promise<{ code: string; amount: number }> {
  const res = await apiClient.post('/payment/coupons/validate', { code });
  return (res.data ?? { code, amount: 0 }) as { code: string; amount: number };
}

/** 创建订单（券码在此锁定）；amount 单位：分 */
export async function createOrder(payload: {
  product_type: ProductType;
  channel: PayChannel;
  coupon_code?: string;
  /** renewal 必传：延期目标激活码 */
  target_code?: string;
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

export interface AdminOrderItem extends OrderItem {
  user_email?: string | null;
  /** 交付的激活码是否可退（未使用才可退） */
  code_refundable?: boolean;
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

/** 发起退款（仅未使用激活码可退；官方退款 API，回调后置 refunded + 作废码） */
export async function adminRefundOrder(id: string): Promise<{ order: AdminOrderItem }> {
  const res = await apiClient.post(`/admin/payment/orders/${encodeURIComponent(id)}/refund`);
  return res.data as { order: AdminOrderItem };
}
