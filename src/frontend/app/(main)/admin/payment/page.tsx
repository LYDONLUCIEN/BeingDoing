'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Copy, ShoppingCart, Ticket, X } from 'lucide-react';
import PaymentOrdersTab from '@/components/admin/PaymentOrdersTab';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  createCoupons,
  deleteCoupon,
  fenToYuan,
  listCoupons,
  updateCouponAmount,
  yuanToFen,
  type CouponItem,
  type CouponSource,
  type CouponStatus,
  type CreatedCoupon,
} from '@/lib/api/payment';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

type PageTab = 'orders' | 'coupons';
type StatusFilter = 'all' | CouponStatus;
type SourceFilter = 'all' | CouponSource;

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<CouponStatus, string> = {
  unused: '未使用',
  locked: '锁定中',
  used: '已使用',
};

const STATUS_COLOR: Record<CouponStatus, string> = {
  unused: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  locked: 'bg-amber-100 text-amber-700 border-amber-200',
  used: 'bg-neutral-200 text-neutral-600 border-neutral-300',
};

const SOURCE_LABEL: Record<CouponSource, string> = {
  admin: '后台创建',
  email_auto: '邮件自动',
};

export default function AdminPaymentPage() {
  // 默认落在订单 tab
  const [tab, setTab] = useState<PageTab>('orders');

  // 列表状态
  const [coupons, setCoupons] = useState<CouponItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');
  const [loading, setLoading] = useState(false);

  // 创建表单
  const [createAmount, setCreateAmount] = useState('50');
  const [createCount, setCreateCount] = useState(1);
  const [creating, setCreating] = useState(false);
  const [lastCreated, setLastCreated] = useState<CreatedCoupon[]>([]);

  // 行内编辑 / 行操作
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingAmount, setEditingAmount] = useState('');
  const [rowWorkingId, setRowWorkingId] = useState<string | null>(null);

  // 复制反馈 + 本地 toast
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  const loadCoupons = useCallback(
    async (p: number, sf: StatusFilter, sof: SourceFilter) => {
      setLoading(true);
      try {
        const res = await listCoupons({
          page: p,
          page_size: PAGE_SIZE,
          status: sf === 'all' ? undefined : sf,
          source: sof === 'all' ? undefined : sof,
        });
        setCoupons(res.items);
        setTotal(res.total);
        setPage(res.page || p);
      } catch (e: unknown) {
        setToast({ type: 'error', msg: getApiErrorMessage(e, '加载折扣券列表失败') });
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadCoupons(1, 'all', 'all');
  }, [loadCoupons]);

  const reload = () => loadCoupons(page, statusFilter, sourceFilter);

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

  const parseAmountToFen = (raw: string): number | null => {
    const yuan = Number(raw);
    if (!Number.isFinite(yuan) || yuan <= 0) return null;
    const fen = yuanToFen(yuan);
    return fen > 0 ? fen : null;
  };

  const handleCreate = async () => {
    const fen = parseAmountToFen(createAmount);
    if (fen === null) {
      setToast({ type: 'error', msg: '请输入有效金额（元，需大于 0）' });
      return;
    }
    const count = Math.floor(createCount);
    if (!Number.isFinite(count) || count < 1 || count > 500) {
      setToast({ type: 'error', msg: '数量需为 1-500 的整数' });
      return;
    }
    setCreating(true);
    try {
      const res = await createCoupons({ amount: fen, count });
      setLastCreated(res.created);
      setToast({
        type: 'success',
        msg: `已创建 ${res.created.length} 张折扣券（面额 ¥${fenToYuan(fen)}）`,
      });
      await loadCoupons(1, statusFilter, sourceFilter);
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '创建折扣券失败') });
    } finally {
      setCreating(false);
    }
  };

  const startEditAmount = (item: CouponItem) => {
    setEditingId(item.id);
    setEditingAmount(fenToYuan(item.amount));
  };

  const handleSaveAmount = async (item: CouponItem) => {
    const fen = parseAmountToFen(editingAmount);
    if (fen === null) {
      setToast({ type: 'error', msg: '请输入有效金额（元，需大于 0）' });
      return;
    }
    setRowWorkingId(item.id);
    try {
      await updateCouponAmount(item.id, fen);
      setToast({ type: 'success', msg: `券 ${item.code} 面额已调整为 ¥${fenToYuan(fen)}` });
      setEditingId(null);
      await reload();
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '调整面额失败') });
    } finally {
      setRowWorkingId(null);
    }
  };

  const handleDelete = async (item: CouponItem) => {
    if (
      !window.confirm(
        `确认作废折扣券 ${item.code}（¥${fenToYuan(item.amount)}）？\n作废后不可恢复。`,
      )
    ) {
      return;
    }
    setRowWorkingId(item.id);
    try {
      await deleteCoupon(item.id);
      setToast({ type: 'success', msg: `券 ${item.code} 已作废` });
      await reload();
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '作废失败') });
    } finally {
      setRowWorkingId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
          支付管理
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          折扣券为通用码：固定金额、无门槛、永久有效、核销一次即作废；下单锁定、关单释放。
        </p>
      </header>

      {/* Tab 切换 */}
      <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setTab('orders')}
          className={`px-4 py-2 rounded-xl text-xs border inline-flex items-center gap-1.5 ${
            tab === 'orders'
              ? 'bg-bd-ui-accent text-bd-ui-accent-fg border-transparent'
              : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
          }`}
        >
          <ShoppingCart className="w-3.5 h-3.5" />
          订单管理
        </button>
        <button
          type="button"
          onClick={() => setTab('coupons')}
          className={`px-4 py-2 rounded-xl text-xs border inline-flex items-center gap-1.5 ${
            tab === 'coupons'
              ? 'bg-bd-ui-accent text-bd-ui-accent-fg border-transparent'
              : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
          }`}
        >
          <Ticket className="w-3.5 h-3.5" />
          折扣券
        </button>
      </section>

      {/* 订单管理 tab */}
      {tab === 'orders' && <PaymentOrdersTab />}

      {tab === 'coupons' && (
        <>
          {/* 创建折扣券 */}
          <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-4 shadow-sm space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <p className="text-[11px] text-bd-subtle">面额（元）</p>
                <input
                  type="number"
                  min={0.01}
                  step={0.01}
                  value={createAmount}
                  onChange={(e) => setCreateAmount(e.target.value)}
                  className="w-28 rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
                />
              </div>
              <div className="space-y-1">
                <p className="text-[11px] text-bd-subtle">数量（1-500）</p>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={createCount}
                  onChange={(e) => setCreateCount(Number(e.target.value || 1))}
                  className="w-28 rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
                />
              </div>
              <button
                type="button"
                onClick={handleCreate}
                disabled={creating}
                className="px-4 py-2 rounded-lg text-xs font-medium bg-bd-ui-accent text-bd-ui-accent-fg disabled:opacity-60"
              >
                {creating ? '创建中…' : '创建折扣券'}
              </button>
            </div>

            {/* 新创建券码展示 */}
            {lastCreated.length > 0 && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 dark:bg-emerald-950/20 dark:border-emerald-800 px-4 py-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs text-emerald-700 dark:text-emerald-300">
                    本次创建 {lastCreated.length} 张（面额 ¥{fenToYuan(lastCreated[0].amount)}）
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        copyText(
                          lastCreated.map((c) => c.code).join('\n'),
                          `已复制 ${lastCreated.length} 个券码`,
                        )
                      }
                      className="text-[11px] text-emerald-700 dark:text-emerald-300 hover:underline"
                    >
                      复制全部
                    </button>
                    <button
                      type="button"
                      onClick={() => setLastCreated([])}
                      className="text-emerald-700/60 hover:text-emerald-700 dark:text-emerald-300/60 dark:hover:text-emerald-300"
                      aria-label="关闭"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {lastCreated.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => copyText(c.code, `已复制：${c.code}`)}
                      title="点击复制"
                      className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-white/70 dark:bg-emerald-950/40 dark:border-emerald-800 px-2 py-1 font-mono text-[11px] text-emerald-800 dark:text-emerald-200 hover:bg-white"
                    >
                      {c.code}
                      <Copy className="w-3 h-3 opacity-60" />
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* 筛选 */}
          <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-4 text-xs">
            <label className="inline-flex items-center gap-2">
              <span className="text-bd-subtle">状态</span>
              <select
                value={statusFilter}
                onChange={(e) => {
                  const v = e.target.value as StatusFilter;
                  setStatusFilter(v);
                  loadCoupons(1, v, sourceFilter);
                }}
                className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
              >
                <option value="all">全部</option>
                <option value="unused">未使用</option>
                <option value="locked">锁定中</option>
                <option value="used">已使用</option>
              </select>
            </label>
            <label className="inline-flex items-center gap-2">
              <span className="text-bd-subtle">来源</span>
              <select
                value={sourceFilter}
                onChange={(e) => {
                  const v = e.target.value as SourceFilter;
                  setSourceFilter(v);
                  loadCoupons(1, statusFilter, v);
                }}
                className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
              >
                <option value="all">全部</option>
                <option value="admin">后台创建</option>
                <option value="email_auto">邮件自动</option>
              </select>
            </label>
            <span className="text-[11px] text-bd-subtle ml-auto">共 {total} 张</span>
          </section>

          {/* 折扣券列表 */}
          <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-5 shadow-sm">
            {loading ? (
              <p className="text-xs text-bd-subtle">加载中…</p>
            ) : coupons.length === 0 ? (
              <p className="text-xs text-bd-subtle">暂无折扣券记录。</p>
            ) : (
              <div className="overflow-x-auto -mx-2">
                <table className="min-w-full text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                      <th className="px-2 py-2 text-left font-medium">券码</th>
                      <th className="px-2 py-2 text-left font-medium">面额</th>
                      <th className="px-2 py-2 text-left font-medium">状态</th>
                      <th className="px-2 py-2 text-left font-medium">来源</th>
                      <th className="px-2 py-2 text-left font-medium">创建时间</th>
                      <th className="px-2 py-2 text-left font-medium">使用信息</th>
                      <th className="px-2 py-2 text-left font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {coupons.map((item) => (
                      <tr key={item.id} className="border-b border-bd-border/60 last:border-0">
                        <td className="px-2 py-2">
                          <button
                            type="button"
                            onClick={() => copyText(item.code, `已复制：${item.code}`)}
                            title="点击复制"
                            className="inline-flex items-center gap-1 font-mono text-[11px] hover:text-bd-fg"
                            style={{ color: 'var(--bd-fg)' }}
                          >
                            {item.code}
                            {copiedCode === item.code ? (
                              <Check className="w-3 h-3 text-emerald-500" />
                            ) : (
                              <Copy className="w-3 h-3 opacity-50" />
                            )}
                          </button>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap text-[11px] text-bd-muted">
                          ¥{fenToYuan(item.amount)}
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
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {SOURCE_LABEL[item.source] || item.source}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {formatTime(item.created_at)}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted">
                          {item.status === 'used' ? (
                            <span title={item.used_order_no ? `订单号：${item.used_order_no}` : undefined}>
                              {item.used_by_email || '—'} · {formatTime(item.used_at)}
                            </span>
                          ) : item.status === 'locked' ? (
                            <span className="font-mono" title="锁定它的订单号">
                              锁定订单：{item.locked_order_no || '—'}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          {item.status === 'unused' ? (
                            editingId === item.id ? (
                              <div className="inline-flex items-center gap-1.5">
                                <input
                                  type="number"
                                  min={0.01}
                                  step={0.01}
                                  value={editingAmount}
                                  onChange={(e) => setEditingAmount(e.target.value)}
                                  className="w-20 rounded-md border border-bd-border bg-bd-overlay px-2 py-1 text-[11px]"
                                  autoFocus
                                />
                                <button
                                  type="button"
                                  onClick={() => handleSaveAmount(item)}
                                  disabled={rowWorkingId === item.id}
                                  className="px-2 py-1 rounded-md bg-bd-ui-accent text-bd-ui-accent-fg text-[11px] disabled:opacity-50"
                                >
                                  保存
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setEditingId(null)}
                                  disabled={rowWorkingId === item.id}
                                  className="px-2 py-1 rounded-md border border-bd-border text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md text-[11px]"
                                >
                                  取消
                                </button>
                              </div>
                            ) : (
                              <div className="inline-flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => startEditAmount(item)}
                                  className="px-2 py-1 rounded-md border border-bd-border text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md text-[11px]"
                                >
                                  改金额
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDelete(item)}
                                  disabled={rowWorkingId === item.id}
                                  className="px-2 py-1 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-[11px] disabled:opacity-50"
                                >
                                  作废
                                </button>
                              </div>
                            )
                          ) : (
                            <span className="text-bd-subtle">—</span>
                          )}
                        </td>
                      </tr>
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
                  onClick={() => loadCoupons(page - 1, statusFilter, sourceFilter)}
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
                  onClick={() => loadCoupons(page + 1, statusFilter, sourceFilter)}
                  disabled={page * PAGE_SIZE >= total}
                  className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
                >
                  下一页
                </button>
              </div>
            )}
          </section>
        </>
      )}

      {/* Toast */}
      {toast && (
        <div
          role="alert"
          className={`fixed bottom-8 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium shadow-lg z-[100] ${
            toast.type === 'success'
              ? 'bg-emerald-600/95 text-white'
              : 'bg-red-600/95 text-white'
          }`}
          style={{ animation: 'toast-in 0.25s ease-out' }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
