'use client';

import { Fragment, useCallback, useEffect, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  adminGetOrder,
  adminListOrders,
  adminRefundOrder,
  fenToYuan,
  type AdminOrderItem,
  type OrderStatus,
  type PayChannel,
} from '@/lib/api/payment';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

type StatusFilter = 'all' | OrderStatus;
type ChannelFilter = 'all' | PayChannel;

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<OrderStatus, string> = {
  pending: '待支付',
  paid: '已支付',
  granted: '已发放',
  closed: '已关闭',
  cancelled: '已取消',
  refunding: '退款中',
  refunded: '已退款',
};

/** pending 黄 / paid 青 / granted 绿 / closed cancelled 灰 / refunding 橙 / refunded 紫 */
const STATUS_COLOR: Record<OrderStatus, string> = {
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
  paid: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  granted: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  closed: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  cancelled: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  refunding: 'bg-orange-100 text-orange-700 border-orange-200',
  refunded: 'bg-purple-100 text-purple-700 border-purple-200',
};

const CHANNEL_LABEL: Record<string, string> = {
  alipay: '支付宝',
  wechat: '微信',
};

const PRODUCT_LABEL: Record<string, string> = {
  activation_code: '全程激活码',
  membership_monthly: '会员（包月）',
  membership_lifetime: '会员（永久）',
};

/** 交付码去向文案（ADR-0014；admin 直接中文，与同组件其余文案一致） */
const DEST_LABEL: Record<string, string> = {
  unbound: '未绑定',
  bound_self: '已绑定（本人）',
  bound_other: '已绑定（他人）',
  consumed_for_upgrade: '已用于升级试用码',
  revoked: '已作废（退款）',
  deleted: '已删除',
  expired: '已过期',
  unknown: '记录不存在',
};

/** 去向 badge 配色：unbound 绿 / bound_* 青 / consumed 金 / revoked 红 / 其余灰 */
const DEST_COLOR: Record<string, string> = {
  unbound: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  bound_self: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  bound_other: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  consumed_for_upgrade: 'bg-amber-100 text-amber-700 border-amber-200',
  revoked: 'bg-red-100 text-red-700 border-red-200',
  deleted: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  expired: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  unknown: 'bg-neutral-200 text-neutral-600 border-neutral-300',
};

/**
 * 支付管理 · 订单管理 tab（P2a）
 * 风格与折扣券 tab 一致：原生 table、本地 toast、二次确认、点击订单号展开详情行。
 */
export default function PaymentOrdersTab() {
  const [orders, setOrders] = useState<AdminOrderItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [channelFilter, setChannelFilter] = useState<ChannelFilter>('all');
  const [loading, setLoading] = useState(false);

  // 展开详情 / 退款确认
  const [expandedId, setExpandedId] = useState<string | null>(null);
  /** 展开行缓存的订单详情（含 delivered_codes 去向） */
  const [detailById, setDetailById] = useState<Record<string, AdminOrderItem>>({});
  const [refundTarget, setRefundTarget] = useState<AdminOrderItem | null>(null);
  const [refundWorking, setRefundWorking] = useState(false);

  // 复制反馈 + 本地 toast（与券 tab 同款）
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  const loadOrders = useCallback(
    async (p: number, sf: StatusFilter, cf: ChannelFilter) => {
      setLoading(true);
      try {
        const res = await adminListOrders({
          page: p,
          page_size: PAGE_SIZE,
          status: sf === 'all' ? undefined : sf,
          channel: cf === 'all' ? undefined : cf,
        });
        setOrders(res.items);
        setTotal(res.total);
        setPage(res.page || p);
      } catch (e: unknown) {
        setToast({ type: 'error', msg: getApiErrorMessage(e, '加载订单列表失败') });
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadOrders(1, 'all', 'all');
  }, [loadOrders]);

  const reload = () => loadOrders(page, statusFilter, channelFilter);

  const formatTime = (iso?: string | null) => {
    if (!iso) return '—';
    const formatted = formatLocalDateTime(iso);
    return formatted === '-' ? iso : formatted;
  };

  const copyText = async (text: string, tip: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedCode(text);
      setToast({ type: 'success', msg: tip });
      setTimeout(() => setCopiedCode(null), 1500);
    } catch {
      setToast({ type: 'error', msg: '复制失败，请手动复制' });
    }
  };

  /** 展开/收起详情行：展开时拉取详情（含交付码去向）并缓存 */
  const toggleExpand = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (detailById[id]) return;
    try {
      const res = await adminGetOrder(id);
      setDetailById((m) => ({ ...m, [id]: res.order }));
    } catch {
      /* 详情拉取失败时沿用列表数据 */
    }
  };

  /** 打开退款确认弹窗：拉取最新详情（含 code_refundable） */
  const openRefund = async (item: AdminOrderItem) => {
    setRefundTarget(item);
    try {
      const res = await adminGetOrder(item.id);
      setRefundTarget({ ...item, ...res.order });
    } catch {
      /* 详情拉取失败时沿用列表数据 */
    }
  };

  const handleRefund = async () => {
    if (!refundTarget || refundWorking) return;
    setRefundWorking(true);
    try {
      await adminRefundOrder(refundTarget.id);
      setToast({ type: 'success', msg: `订单 ${refundTarget.order_no} 已发起退款` });
      setRefundTarget(null);
      await reload();
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '退款失败') });
    } finally {
      setRefundWorking(false);
    }
  };

  return (
    <>
      {/* 筛选 */}
      <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-4 text-xs">
        <label className="inline-flex items-center gap-2">
          <span className="text-bd-subtle">状态</span>
          <select
            value={statusFilter}
            onChange={(e) => {
              const v = e.target.value as StatusFilter;
              setStatusFilter(v);
              loadOrders(1, v, channelFilter);
            }}
            className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
          >
            <option value="all">全部</option>
            <option value="pending">待支付</option>
            <option value="paid">已支付</option>
            <option value="granted">已发放</option>
            <option value="closed">已关闭</option>
            <option value="cancelled">已取消</option>
            <option value="refunding">退款中</option>
            <option value="refunded">已退款</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-2">
          <span className="text-bd-subtle">渠道</span>
          <select
            value={channelFilter}
            onChange={(e) => {
              const v = e.target.value as ChannelFilter;
              setChannelFilter(v);
              loadOrders(1, statusFilter, v);
            }}
            className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
          >
            <option value="all">全部</option>
            <option value="alipay">支付宝</option>
            <option value="wechat">微信</option>
          </select>
        </label>
        <span className="text-[11px] text-bd-subtle ml-auto">共 {total} 单</span>
      </section>

      {/* 订单列表 */}
      <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-5 shadow-sm">
        {loading ? (
          <p className="text-xs text-bd-subtle">加载中…</p>
        ) : orders.length === 0 ? (
          <p className="text-xs text-bd-subtle">暂无订单记录。</p>
        ) : (
          <div className="overflow-x-auto -mx-2">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                  <th className="px-2 py-2 text-left font-medium">订单号</th>
                  <th className="px-2 py-2 text-left font-medium">用户邮箱</th>
                  <th className="px-2 py-2 text-left font-medium">商品</th>
                  <th className="px-2 py-2 text-left font-medium">原价/抵扣/实付</th>
                  <th className="px-2 py-2 text-left font-medium">渠道</th>
                  <th className="px-2 py-2 text-left font-medium">状态</th>
                  <th className="px-2 py-2 text-left font-medium">激活码</th>
                  <th className="px-2 py-2 text-left font-medium">创建/支付时间</th>
                  <th className="px-2 py-2 text-left font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((item) => (
                  <Fragment key={item.id}>
                    <tr className="border-b border-bd-border/60 last:border-0">
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          onClick={() => void toggleExpand(item.id)}
                          title="点击展开详情"
                          className="font-mono text-[11px] hover:underline"
                          style={{ color: 'var(--bd-fg)' }}
                        >
                          {item.order_no}
                        </button>
                      </td>
                      <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                        {item.user_email || '—'}
                      </td>
                      <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                        {PRODUCT_LABEL[item.product_type] || item.product_type}
                      </td>
                      <td className="px-2 py-2 whitespace-nowrap text-[11px] text-bd-muted">
                        ¥{fenToYuan(item.amount_original)} / -¥{fenToYuan(item.amount_discount)} /{' '}
                        <span className="font-semibold" style={{ color: 'var(--bd-fg)' }}>
                          ¥{fenToYuan(item.amount_paid)}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                        {CHANNEL_LABEL[item.channel] || item.channel}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-medium ${
                            STATUS_COLOR[item.status] ||
                            'bg-bd-overlay-md text-bd-subtle border-bd-border'
                          }`}
                        >
                          {STATUS_LABEL[item.status] || item.status}
                        </span>
                      </td>
                      <td className="px-2 py-2">
                        {item.delivered_code ? (
                          <button
                            type="button"
                            onClick={() => copyText(item.delivered_code!, `已复制：${item.delivered_code}`)}
                            title="点击复制"
                            className="inline-flex items-center gap-1 font-mono text-[11px] hover:text-bd-fg"
                            style={{ color: 'var(--bd-fg)' }}
                          >
                            {item.delivered_code}
                            {copiedCode === item.delivered_code ? (
                              <Check className="w-3 h-3 text-emerald-500" />
                            ) : (
                              <Copy className="w-3 h-3 opacity-50" />
                            )}
                          </button>
                        ) : (
                          <span className="text-bd-subtle">—</span>
                        )}
                      </td>
                      <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                        {formatTime(item.created_at)}
                        <br />
                        {formatTime(item.paid_at)}
                      </td>
                      <td className="px-2 py-2 whitespace-nowrap">
                        {item.status === 'granted' ? (
                          <button
                            type="button"
                            onClick={() => void openRefund(item)}
                            className="px-2 py-1 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-[11px]"
                          >
                            退款
                          </button>
                        ) : (
                          <span className="text-bd-subtle">—</span>
                        )}
                      </td>
                    </tr>
                    {expandedId === item.id && (
                      <tr className="border-b border-bd-border/60 last:border-0">
                        <td colSpan={9} className="px-2 py-3 bg-bd-overlay/40">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 text-[11px] text-bd-muted px-2">
                            <p>
                              渠道交易号：
                              <span className="font-mono">{item.channel_transaction_id || '—'}</span>
                            </p>
                            <p>
                              使用券码：
                              <span className="font-mono">{item.coupon_code || '—'}</span>
                            </p>
                            <p>创建时间：{formatTime(item.created_at)}</p>
                            <p>支付时间：{formatTime(item.paid_at)}</p>
                            <p>关闭时间：{formatTime(item.closed_at)}</p>
                            <p>退款时间：{formatTime(item.refunded_at)}</p>
                          </div>
                          {/* 交付码去向（ADR-0014；码值/邮箱不脱敏） */}
                          {(detailById[item.id]?.delivered_codes?.length ?? 0) > 0 && (
                            <div className="mt-2 px-2">
                              <p className="text-[11px] text-bd-subtle mb-1">交付码去向：</p>
                              <div className="space-y-1">
                                {detailById[item.id].delivered_codes!.map((dc) => (
                                  <p
                                    key={dc.code}
                                    className="flex flex-wrap items-center gap-2 text-[11px] text-bd-muted"
                                  >
                                    <span className="font-mono" style={{ color: 'var(--bd-fg)' }}>
                                      {dc.code}
                                    </span>
                                    <span
                                      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-medium ${
                                        DEST_COLOR[dc.destination_type] || DEST_COLOR.unknown
                                      }`}
                                    >
                                      {DEST_LABEL[dc.destination_type] || dc.destination_type}
                                    </span>
                                    {dc.destination_detail && (
                                      <span className="font-mono">{dc.destination_detail}</span>
                                    )}
                                    {dc.upgraded_from_code && (
                                      <span className="text-bd-subtle">
                                        来源码：
                                        <span className="font-mono">{dc.upgraded_from_code}</span>
                                      </span>
                                    )}
                                  </p>
                                ))}
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 分页 */}
        {total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-center gap-4 text-xs text-bd-muted">
            <button
              type="button"
              onClick={() => loadOrders(page - 1, statusFilter, channelFilter)}
              disabled={page <= 1}
              className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
            >
              上一页
            </button>
            <span>
              第 {page} 页 / 共 {Math.ceil(total / PAGE_SIZE)} 页（总 {total} 条）
            </span>
            <button
              type="button"
              onClick={() => loadOrders(page + 1, statusFilter, channelFilter)}
              disabled={page * PAGE_SIZE >= total}
              className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
            >
              下一页
            </button>
          </div>
        )}
      </section>

      {/* 退款二次确认弹窗 */}
      {refundTarget && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center px-5">
          <button
            type="button"
            className="absolute inset-0 bg-stone-900/25 backdrop-blur-[2px]"
            aria-label="关闭"
            onClick={() => !refundWorking && setRefundTarget(null)}
          />
          <div
            role="dialog"
            aria-modal
            className="relative w-full max-w-sm rounded-2xl border border-bd-border bg-bd-card px-6 py-5 shadow-xl space-y-4"
          >
            <h3 className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
              确认退款
            </h3>
            <div className="space-y-1.5 text-xs text-bd-muted">
              <p>
                订单号：<span className="font-mono">{refundTarget.order_no}</span>
              </p>
              <p>实付金额：¥{fenToYuan(refundTarget.amount_paid)}</p>
              <p>
                交付激活码：
                <span className="font-mono">{refundTarget.delivered_code || '—'}</span>
              </p>
            </div>
            {refundTarget.code_refundable === false ? (
              <p className="text-xs text-rose-600">激活码已被使用，不可退款</p>
            ) : (
              <p className="text-xs text-bd-subtle">
                退款成功后该激活码将作废，确认继续？
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRefundTarget(null)}
                disabled={refundWorking}
                className="px-3 py-1.5 rounded-lg border border-bd-border text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md text-xs"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleRefund()}
                disabled={refundWorking || refundTarget.code_refundable === false}
                className="px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-medium disabled:opacity-50"
              >
                {refundWorking ? '退款中…' : '确认退款'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast（与券 tab 同款） */}
      {toast && (
        <div
          role="alert"
          className={`fixed bottom-8 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium shadow-lg z-[120] ${
            toast.type === 'success'
              ? 'bg-emerald-600/95 text-white'
              : 'bg-red-600/95 text-white'
          }`}
          style={{ animation: 'toast-in 0.25s ease-out' }}
        >
          {toast.msg}
        </div>
      )}
    </>
  );
}
