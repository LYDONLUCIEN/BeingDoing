'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Check, Copy, Receipt } from 'lucide-react';
import { getApiErrorMessage, isRequestCanceled } from '@/lib/api/client';
import {
  cancelOrder,
  fenToYuan,
  listMyOrders,
  type OrderItem,
  type OrderStatus,
  type PayChannel,
  type ProductType,
} from '@/lib/api/payment';
import { formatLocalDateTime } from '@/lib/utils/formatTime';
import { useLocale } from '@/hooks/useLocale';
import PurchaseModal from '@/components/payment/PurchaseModal';

const PAGE_SIZE = 10;

/** 状态 badge 配色：pending 黄 / paid 青 / granted 绿 / closed cancelled 灰 / refunding 橙 / refunded 紫 */
const STATUS_COLOR: Record<OrderStatus, string> = {
  pending: 'bg-amber-100 text-amber-700 border-amber-200',
  paid: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  granted: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  closed: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  cancelled: 'bg-neutral-200 text-neutral-600 border-neutral-300',
  refunding: 'bg-orange-100 text-orange-700 border-orange-200',
  refunded: 'bg-purple-100 text-purple-700 border-purple-200',
};

/** 订单列表（原 /dashboard/orders 页主体）：分页、继续支付/取消订单、交付码展示、咨询订单入口 */
export default function OrdersSection() {
  const { t } = useLocale();

  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedText, setCopiedText] = useState<string | null>(null);
  const [workingId, setWorkingId] = useState<string | null>(null);

  // 购买弹窗：resumeOrderId 存在时为「继续支付」模式
  const [modalOpen, setModalOpen] = useState(false);
  const [resumeOrderId, setResumeOrderId] = useState<string | undefined>(undefined);

  const loadOrders = useCallback(
    async (p: number) => {
      setLoading(true);
      try {
        const res = await listMyOrders({ page: p, page_size: PAGE_SIZE });
        setOrders(res.items);
        setTotal(res.total);
        setPage(res.page || p);
        setError(null);
      } catch (e: unknown) {
        // 页面刷新/导航导致的请求取消不是错误，静默忽略
        if (isRequestCanceled(e)) return;
        setError(getApiErrorMessage(e, t('dashboard.ordersPage.loadFailed')));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  useEffect(() => {
    void loadOrders(1);
  }, [loadOrders]);

  const productName = (type: ProductType) =>
    t(`payment.productName.${type}`) === `payment.productName.${type}`
      ? type
      : t(`payment.productName.${type}`);

  const channelLabel = (channel: PayChannel) =>
    channel === 'alipay' ? t('payment.channel.alipay') : t('payment.channel.wechat');

  const formatTime = (iso?: string | null) => {
    if (!iso) return '—';
    const formatted = formatLocalDateTime(iso);
    return formatted === '-' ? iso : formatted;
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedText(text);
      setTimeout(() => setCopiedText(null), 1500);
    } catch {
      /* 复制失败静默 */
    }
  };

  const openResume = (id: string) => {
    setResumeOrderId(id);
    setModalOpen(true);
  };

  const handleCancel = async (order: OrderItem) => {
    if (!window.confirm(t('dashboard.ordersPage.confirmCancel'))) return;
    setWorkingId(order.id);
    try {
      await cancelOrder(order.id);
      await loadOrders(page);
    } catch (e: unknown) {
      setError(getApiErrorMessage(e, t('dashboard.ordersPage.cancelFailed')));
    } finally {
      setWorkingId(null);
    }
  };

  return (
    <div>
      {loading ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-bd-muted">加载中...</p>
        </div>
      ) : error && orders.length === 0 ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-red-600/90 dark:text-red-400/90 mb-4">{error}</p>
          <button
            type="button"
            onClick={() => void loadOrders(page)}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            重试
          </button>
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center space-y-6">
          <Receipt className="w-8 h-8 mx-auto text-bd-subtle" />
          <p className="text-bd-muted">{t('dashboard.ordersPage.empty')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {error && <p className="text-sm text-red-600/90 dark:text-red-400/90">{error}</p>}
          {orders.map((order) => (
            <div
              key={order.id}
              className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-5 space-y-3"
            >
              {/* 头部：商品名 + 状态 badge */}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-medium text-bd-fg text-base">{productName(order.product_type)}</h2>
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full border text-xs font-medium ${
                    STATUS_COLOR[order.status] || 'bg-bd-overlay-md text-bd-subtle border-bd-border'
                  }`}
                >
                  {t(`payment.status.${order.status}`)}
                </span>
              </div>

              {/* 订单号（可复制） */}
              <div className="flex items-center gap-2 text-xs text-bd-muted">
                <span>{t('dashboard.ordersPage.orderNo')}</span>
                <button
                  type="button"
                  onClick={() => void copyText(order.order_no)}
                  title={t('payment.copy')}
                  className="inline-flex items-center gap-1 font-mono hover:text-bd-fg"
                >
                  {order.order_no}
                  {copiedText === order.order_no ? (
                    <Check className="w-3 h-3 text-emerald-500" />
                  ) : (
                    <Copy className="w-3 h-3 opacity-50" />
                  )}
                </button>
              </div>

              {/* 金额行：实付大字 + 原价划线 + 券抵扣注明 */}
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-xl font-bold text-bd-fg">¥{fenToYuan(order.amount_paid)}</span>
                {order.amount_discount > 0 && (
                  <>
                    <span className="text-sm text-bd-subtle line-through">
                      ¥{fenToYuan(order.amount_original)}
                    </span>
                    <span className="text-xs text-emerald-600">
                      {t('dashboard.ordersPage.couponNote', {
                        amount: fenToYuan(order.amount_discount),
                      })}
                    </span>
                  </>
                )}
              </div>

              {/* 渠道 + 创建时间 */}
              <p className="text-xs text-bd-muted">
                {channelLabel(order.channel)} · {formatTime(order.created_at)}
              </p>

              {/* 操作区 */}
              {order.status === 'pending' && (
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => openResume(order.id)}
                    className="px-4 py-2 rounded-lg text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
                  >
                    {t('dashboard.ordersPage.continuePay')}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleCancel(order)}
                    disabled={workingId === order.id}
                    className="px-4 py-2 rounded-lg text-sm border border-bd-border text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md disabled:opacity-50"
                  >
                    {t('dashboard.ordersPage.cancel')}
                  </button>
                </div>
              )}

              {order.status === 'granted' &&
                order.delivered_code &&
                (() => {
                  // 套餐订单可交付多枚码：全部平级展示，不指定「哪枚自用/哪枚转赠」
                  // （码是等价的，用户升级/赠送时不一定会用哪一枚）
                  const metaCodes = Array.isArray(order.meta?.codes)
                    ? (order.meta!.codes as string[])
                    : [];
                  const giftCodes = Array.isArray(order.meta?.gift_codes)
                    ? (order.meta!.gift_codes as string[])
                    : [];
                  const allCodes = [order.delivered_code!, ...metaCodes, ...giftCodes]
                    .filter((c): c is string => !!c)
                    .filter((c, i, arr) => arr.indexOf(c) === i);
                  const renderCopyBtn = (code: string) => (
                    <button
                      key={code}
                      type="button"
                      onClick={() => void copyText(code)}
                      title={t('payment.copy')}
                      className="inline-flex items-center gap-1.5 rounded-md border border-bd-border bg-bd-overlay px-2 py-1 font-mono text-sm text-bd-fg hover:bg-bd-overlay-md"
                    >
                      {code}
                      {copiedText === code ? (
                        <Check className="w-3.5 h-3.5 text-emerald-500" />
                      ) : (
                        <Copy className="w-3.5 h-3.5 opacity-50" />
                      )}
                    </button>
                  );
                  if (allCodes.length <= 1) {
                    return (
                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        <span className="text-xs text-bd-muted">
                          {t('payment.success.codeLabel')}
                        </span>
                        {renderCopyBtn(order.delivered_code!)}
                        <Link
                          href={`/explore/activate?code=${encodeURIComponent(order.delivered_code!)}`}
                          className="px-4 py-2 rounded-lg text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
                        >
                          {t('dashboard.ordersPage.goActivate')}
                        </Link>
                      </div>
                    );
                  }
                  return (
                    <div className="space-y-2 pt-1">
                      <p className="text-xs text-bd-muted">
                        {t('dashboard.ordersPage.deliveredCodesLabel', {
                          count: String(allCodes.length),
                        })}
                      </p>
                      <div className="flex flex-wrap items-center gap-2">
                        {allCodes.map(renderCopyBtn)}
                      </div>
                      <p className="text-[11px] text-bd-subtle">
                        {t('dashboard.ordersPage.codesFungibleHint')}
                        <Link
                          href="/dashboard/codes"
                          className="ml-1 text-bd-ui-accent hover:underline"
                        >
                          {t('dashboard.ordersPage.viewCodesLink')}
                        </Link>
                      </p>
                    </div>
                  );
                })()}

              {/* 咨询订单：预约问卷入口 */}
              {order.status === 'granted' &&
                order.product_type === 'consultation' &&
                order.meta?.booking_id && (
                  <div className="pt-1">
                    <Link
                      href={`/dashboard/consultation/${order.meta.booking_id}`}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
                    >
                      {t('dashboard.ordersPage.goConsultation')}
                    </Link>
                  </div>
                )}
            </div>
          ))}

          {/* 分页 */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-center gap-4 pt-2 text-xs text-bd-muted">
              <button
                type="button"
                onClick={() => void loadOrders(page - 1)}
                disabled={page <= 1}
                className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
              >
                {t('dashboard.ordersPage.prevPage')}
              </button>
              <span>
                {page} / {Math.ceil(total / PAGE_SIZE)}
              </span>
              <button
                type="button"
                onClick={() => void loadOrders(page + 1)}
                disabled={page * PAGE_SIZE >= total}
                className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
              >
                {t('dashboard.ordersPage.nextPage')}
              </button>
            </div>
          )}
        </div>
      )}

      <PurchaseModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        resumeOrderId={resumeOrderId}
        onSuccess={() => void loadOrders(1)}
      />
    </div>
  );
}
