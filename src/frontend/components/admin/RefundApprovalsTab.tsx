'use client';

/**
 * Admin 退款审批 Tab（2026-10-05 统一退款申请单）
 *
 * - 列表：状态/订单号筛选 + 分页，含申请人邮箱、申请/批准金额、审批留痕
 * - 详情：金额调整记录、行快照、订单实时行状态（审批参考——申请后码可能已被用）
 * - 操作：批准并执行（可下调金额，与申请额不一致必填理由）/ 驳回（必填理由，
 *   用户可见）/ 失败重试（同 refund_no 渠道幂等）/ 代录申请（线下协商场景）
 */

import { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Plus, RotateCcw } from 'lucide-react';
import { getApiErrorMessage, isRequestCanceled } from '@/lib/api/client';
import {
  adminApproveRefund,
  adminCreateRefund,
  adminGetRefund,
  adminListRefunds,
  adminRejectRefund,
  adminRetryRefund,
  fenToYuan,
  yuanToFen,
  type RefundItem,
  type RefundStatus,
} from '@/lib/api/payment';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<RefundStatus, string> = {
  pending_review: '待审批',
  refunding: '退款中',
  succeeded: '已退款',
  failed: '退款失败',
  rejected: '已驳回',
  withdrawn: '已撤回',
};

const STATUS_COLOR: Record<RefundStatus, string> = {
  pending_review: 'bg-amber-100 text-amber-700 border-amber-200',
  refunding: 'bg-orange-100 text-orange-700 border-orange-200',
  succeeded: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  failed: 'bg-red-100 text-red-700 border-red-200',
  rejected: 'bg-stone-100 text-stone-600 border-stone-200',
  withdrawn: 'bg-stone-100 text-stone-500 border-stone-200',
};

const LINE_STATUS_LABEL: Record<string, string> = {
  available: '可退',
  used: '已被使用',
  refunded: '已退款',
};

type DetailResult = Awaited<ReturnType<typeof adminGetRefund>>;

export default function RefundApprovalsTab() {
  const [items, setItems] = useState<RefundItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<RefundStatus | ''>('');
  const [orderNoFilter, setOrderNoFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  // 详情 / 审批 / 驳回 / 代录
  const [detail, setDetail] = useState<DetailResult | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [approveOpen, setApproveOpen] = useState(false);
  const [approveAmountYuan, setApproveAmountYuan] = useState('');
  const [approveNote, setApproveNote] = useState('');
  const [working, setWorking] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectNote, setRejectNote] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    order_id: '',
    refund_type: 'full' as 'full' | 'partial',
    amountYuan: '',
    reason: '',
    note: '',
  });

  const notify = (type: 'success' | 'error', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(
    async (p: number, status: RefundStatus | '', orderNo: string) => {
      setLoading(true);
      try {
        const res = await adminListRefunds({
          status: status || undefined,
          order_no: orderNo.trim() || undefined,
          page: p,
          page_size: PAGE_SIZE,
        });
        setItems(res.items);
        setTotal(res.total);
        setPage(res.page || p);
        setError(null);
      } catch (e: unknown) {
        if (isRequestCanceled(e)) return;
        setError(getApiErrorMessage(e, '加载退款单失败'));
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    void load(1, statusFilter, orderNoFilter);
  }, [load, statusFilter, orderNoFilter]);

  const openDetail = async (id: string) => {
    setDetailLoading(true);
    setApproveOpen(false);
    setRejectOpen(false);
    try {
      const data = await adminGetRefund(id);
      setDetail(data);
      setApproveAmountYuan(
        ((data.requested_amount ?? 0) / 100).toFixed(2)
      );
      setApproveNote('');
      setRejectNote('');
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      notify('error', getApiErrorMessage(e, '加载退款单详情失败'));
    } finally {
      setDetailLoading(false);
    }
  };

  const capFen = detail
    ? Math.min(
        (detail.order_lines ?? [])
          .filter((l) => l.effective_status === 'available')
          .reduce((sum, l) => sum + l.amount_paid_alloc, 0),
        detail.order.amount_paid - detail.order.amount_refunded
      )
    : 0;

  const handleApprove = async () => {
    if (!detail || working) return;
    const amountFen = yuanToFen(parseFloat(approveAmountYuan) || 0);
    setWorking(true);
    try {
      await adminApproveRefund(detail.id, {
        approved_amount: amountFen,
        note: approveNote.trim() || undefined,
      });
      notify('success', `退款单 ${detail.refund_no} 已批准并执行`);
      setDetail(null);
      await load(page, statusFilter, orderNoFilter);
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      notify('error', getApiErrorMessage(e, '批准失败'));
      // 上限可能已收缩（码被用），刷新详情
      void openDetail(detail.id);
    } finally {
      setWorking(false);
    }
  };

  const handleReject = async () => {
    if (!detail || !rejectNote.trim() || working) return;
    setWorking(true);
    try {
      await adminRejectRefund(detail.id, rejectNote.trim());
      notify('success', `退款单 ${detail.refund_no} 已驳回`);
      setDetail(null);
      await load(page, statusFilter, orderNoFilter);
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      notify('error', getApiErrorMessage(e, '驳回失败'));
    } finally {
      setWorking(false);
    }
  };

  const handleRetry = async () => {
    if (!detail || working) return;
    setWorking(true);
    try {
      await adminRetryRefund(detail.id);
      notify('success', `退款单 ${detail.refund_no} 重试成功`);
      await openDetail(detail.id);
      await load(page, statusFilter, orderNoFilter);
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      notify('error', getApiErrorMessage(e, '重试失败'));
      void openDetail(detail.id);
    } finally {
      setWorking(false);
    }
  };

  const handleCreate = async () => {
    if (working) return;
    const amountFen = createForm.amountYuan.trim()
      ? yuanToFen(parseFloat(createForm.amountYuan) || 0)
      : undefined;
    setWorking(true);
    try {
      await adminCreateRefund({
        order_id: createForm.order_id.trim(),
        refund_type: createForm.refund_type,
        amount: amountFen,
        reason: createForm.reason.trim(),
        note: createForm.note.trim() || undefined,
      });
      notify('success', '已代录退款申请，请在列表中审批执行');
      setCreateOpen(false);
      setCreateForm({
        order_id: '',
        refund_type: 'full',
        amountYuan: '',
        reason: '',
        note: '',
      });
      await load(1, statusFilter, orderNoFilter);
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      notify('error', getApiErrorMessage(e, '代录失败'));
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="space-y-4">
      {/* 筛选 + 代录入口 */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as RefundStatus | '')}
          className="rounded-lg border border-bd-border bg-bd-card px-3 py-1.5 text-sm"
        >
          <option value="">全部状态</option>
          {(Object.keys(STATUS_LABEL) as RefundStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <input
          value={orderNoFilter}
          onChange={(e) => setOrderNoFilter(e.target.value)}
          placeholder="按订单号筛选"
          className="w-56 rounded-lg border border-bd-border bg-bd-card px-3 py-1.5 text-sm font-mono"
        />
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="ml-auto flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          <Plus size={14} />代录退款申请
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-10 text-bd-muted">
          <Loader2 className="mr-2 animate-spin" size={18} />
          加载中…
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-bd-border bg-bd-card p-8 text-center text-sm text-bd-muted">
          暂无退款申请
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-bd-border bg-bd-card">
          <table className="w-full text-sm">
            <thead className="border-b border-bd-border text-left text-xs text-bd-muted">
              <tr>
                <th className="px-3 py-2">退款单号</th>
                <th className="px-3 py-2">订单号</th>
                <th className="px-3 py-2">用户</th>
                <th className="px-3 py-2">类型</th>
                <th className="px-3 py-2">金额</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">来源</th>
                <th className="px-3 py-2">申请时间</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr
                  key={r.id}
                  className="cursor-pointer border-b border-bd-border/50 hover:bg-bd-overlay-md"
                  onClick={() => void openDetail(r.id)}
                >
                  <td className="px-3 py-2 font-mono text-xs">{r.refund_no}</td>
                  <td className="px-3 py-2 font-mono text-xs">{r.order_no}</td>
                  <td className="px-3 py-2 text-xs">{r.user_email ?? r.user_id}</td>
                  <td className="px-3 py-2 text-xs">
                    {r.refund_type === 'full' ? '全额' : '部分'}
                  </td>
                  <td className="px-3 py-2 text-xs">
                    ¥{fenToYuan(r.requested_amount)}
                    {r.approved_amount != null && r.approved_amount !== r.requested_amount && (
                      <span className="text-indigo-600"> → ¥{fenToYuan(r.approved_amount)}</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded border px-1.5 py-0.5 text-xs ${
                        STATUS_COLOR[r.status] ?? ''
                      }`}
                    >
                      {STATUS_LABEL[r.status] ?? r.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs">
                    {r.originated === 'admin' ? '代录' : '用户'}
                  </td>
                  <td className="px-3 py-2 text-xs text-bd-muted">
                    {formatLocalDateTime(r.created_at)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {r.status === 'pending_review' && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                        待处理
                      </span>
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
        <div className="flex items-center justify-center gap-4 text-xs text-bd-muted">
          <button
            type="button"
            onClick={() => void load(page - 1, statusFilter, orderNoFilter)}
            disabled={page <= 1}
            className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50"
          >
            上一页
          </button>
          <span>
            第 {page} 页 / 共 {Math.ceil(total / PAGE_SIZE)} 页（总 {total} 条）
          </span>
          <button
            type="button"
            onClick={() => void load(page + 1, statusFilter, orderNoFilter)}
            disabled={page * PAGE_SIZE >= total}
            className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50"
          >
            下一页
          </button>
        </div>
      )}

      {/* 详情弹窗 */}
      {(detail || detailLoading) && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center px-5">
          <button
            type="button"
            className="absolute inset-0 bg-stone-900/25 backdrop-blur-[2px]"
            aria-label="关闭"
            onClick={() => !working && setDetail(null)}
          />
          <div className="relative max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-bd-border bg-bd-card px-6 py-5 shadow-xl space-y-4">
            {detailLoading || !detail ? (
              <div className="flex items-center justify-center py-10 text-bd-muted">
                <Loader2 className="mr-2 animate-spin" size={18} />加载详情…
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
                      退款单 <span className="font-mono">{detail.refund_no}</span>
                    </h3>
                    <p className="mt-1 text-xs text-bd-muted">
                      订单 <span className="font-mono">{detail.order.order_no}</span> · 实付 ¥
                      {fenToYuan(detail.order.amount_paid)} · 已退 ¥
                      {fenToYuan(detail.order.amount_refunded)} · 用户{' '}
                      {detail.user_email ?? detail.user_id}
                    </p>
                  </div>
                  <span
                    className={`rounded border px-2 py-0.5 text-xs ${STATUS_COLOR[detail.status]}`}
                  >
                    {STATUS_LABEL[detail.status]}
                  </span>
                </div>

                {/* 金额与申请信息 */}
                <div className="grid grid-cols-2 gap-2 rounded-lg bg-bd-overlay p-3 text-xs">
                  <p>
                    类型：{detail.refund_type === 'full' ? '全额退款' : '部分退款'}（
                    {detail.originated === 'admin' ? 'admin 代录' : '用户申请'}）
                  </p>
                  <p>申请金额：¥{fenToYuan(detail.requested_amount)}</p>
                  <p>
                    批准金额：
                    {detail.approved_amount != null ? `¥${fenToYuan(detail.approved_amount)}` : '—'}
                  </p>
                  <p>申请时间：{formatLocalDateTime(detail.created_at)}</p>
                  {detail.reviewed_at && (
                    <p className="col-span-2">
                      审批：{formatLocalDateTime(detail.reviewed_at)}（{detail.reviewed_by}）
                    </p>
                  )}
                  {detail.succeeded_at && (
                    <p className="col-span-2">退款成功：{formatLocalDateTime(detail.succeeded_at)}</p>
                  )}
                </div>

                <div className="rounded-lg border border-bd-border p-3 text-xs">
                  <p className="text-bd-muted">用户申请理由</p>
                  <p className="mt-1">{detail.reason_user || '—'}</p>
                  {detail.reason_admin && (
                    <>
                      <p className="mt-2 text-bd-muted">审批意见 / 驳回理由</p>
                      <p className="mt-1">{detail.reason_admin}</p>
                    </>
                  )}
                  {detail.failed_reason && (
                    <p className="mt-2 text-red-600">失败原因：{detail.failed_reason}</p>
                  )}
                </div>

                {/* 订单实时行状态（审批参考：申请后码可能已被用） */}
                <div>
                  <p className="mb-1 text-xs font-medium text-bd-muted">
                    订单明细行（实时状态；可退上限 = Σ 可退行分摊实付 与 剩余可退 取小）
                  </p>
                  <ul className="space-y-1">
                    {detail.order_lines.map((l) => (
                      <li
                        key={l.id}
                        className="flex items-center justify-between rounded border border-bd-border px-2 py-1 text-xs"
                      >
                        <span className="font-mono">{l.item_ref ?? l.item_type}</span>
                        <span className="flex items-center gap-2 text-bd-muted">
                          <span>¥{fenToYuan(l.amount_paid_alloc)}</span>
                          <span
                            className={
                              l.effective_status === 'available' ? 'text-emerald-600' : 'text-stone-500'
                            }
                          >
                            {LINE_STATUS_LABEL[l.effective_status] ?? l.effective_status}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1 text-right text-xs text-bd-muted">
                    当前可退上限：<strong className="text-indigo-600">¥{fenToYuan(capFen)}</strong>
                  </p>
                </div>

                {/* 审批操作 */}
                {detail.status === 'pending_review' && (
                  <div className="space-y-3 border-t border-bd-border pt-3">
                    {!approveOpen && !rejectOpen && (
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setRejectOpen(true)}
                          className="rounded-lg border border-bd-border px-4 py-1.5 text-xs text-bd-muted hover:text-bd-fg"
                        >
                          驳回
                        </button>
                        <button
                          type="button"
                          onClick={() => setApproveOpen(true)}
                          className="flex items-center gap-1 rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                        >
                          <CheckCircle2 size={13} />批准并执行
                        </button>
                      </div>
                    )}
                    {approveOpen && (
                      <div className="space-y-2 rounded-lg bg-emerald-50 p-3">
                        <p className="text-xs text-emerald-800">
                          批准金额（只能 ≤ 当前可退上限 ¥{fenToYuan(capFen)}；与申请额不一致须填调整理由）
                        </p>
                        <div className="flex items-center gap-2">
                          <span className="text-xs">¥</span>
                          <input
                            value={approveAmountYuan}
                            onChange={(e) => setApproveAmountYuan(e.target.value)}
                            className="w-28 rounded border px-2 py-1 text-sm"
                            placeholder="0.00"
                          />
                          <span className="text-xs text-bd-muted">
                            （申请 ¥{fenToYuan(detail.requested_amount)}）
                          </span>
                        </div>
                        <textarea
                          value={approveNote}
                          onChange={(e) => setApproveNote(e.target.value)}
                          rows={2}
                          placeholder="审批意见 / 金额调整理由"
                          className="w-full rounded border px-2 py-1 text-sm"
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setApproveOpen(false)}
                            className="rounded border px-3 py-1 text-xs"
                          >
                            取消
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleApprove()}
                            disabled={working}
                            className="flex items-center gap-1 rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                          >
                            {working ? <Loader2 size={12} className="animate-spin" /> : null}
                            确认批准并执行渠道退款
                          </button>
                        </div>
                      </div>
                    )}
                    {rejectOpen && (
                      <div className="space-y-2 rounded-lg bg-red-50 p-3">
                        <p className="text-xs text-red-700">驳回理由（必填，用户可见）</p>
                        <textarea
                          value={rejectNote}
                          onChange={(e) => setRejectNote(e.target.value)}
                          rows={2}
                          className="w-full rounded border px-2 py-1 text-sm"
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setRejectOpen(false)}
                            className="rounded border px-3 py-1 text-xs"
                          >
                            取消
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleReject()}
                            disabled={working || !rejectNote.trim()}
                            className="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
                          >
                            确认驳回
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 失败重试 */}
                {detail.status === 'failed' && (
                  <div className="flex justify-end border-t border-bd-border pt-3">
                    <button
                      type="button"
                      onClick={() => void handleRetry()}
                      disabled={working}
                      className="flex items-center gap-1 rounded-lg bg-orange-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-orange-700 disabled:opacity-50"
                    >
                      {working ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <RotateCcw size={13} />
                      )}
                      重试退款（渠道幂等，不会重复退）
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* 代录弹窗 */}
      {createOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center px-5">
          <button
            type="button"
            className="absolute inset-0 bg-stone-900/25 backdrop-blur-[2px]"
            aria-label="关闭"
            onClick={() => !working && setCreateOpen(false)}
          />
          <div className="relative w-full max-w-md rounded-2xl border border-bd-border bg-bd-card px-6 py-5 shadow-xl space-y-3">
            <h3 className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
              代录退款申请（线下协商）
            </h3>
            <p className="text-xs text-bd-subtle">
              代录后进入「待审批」，仍需在本列表中批准执行；代录人将留痕。
            </p>
            <div className="space-y-2 text-sm">
              <input
                value={createForm.order_id}
                onChange={(e) => setCreateForm({ ...createForm, order_id: e.target.value })}
                placeholder="订单 ID（订单详情中的 id）"
                className="w-full rounded border px-2 py-1.5 font-mono text-xs"
              />
              <div className="flex gap-2">
                {(['full', 'partial'] as const).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setCreateForm({ ...createForm, refund_type: t })}
                    className={`flex-1 rounded border px-2 py-1.5 text-xs ${
                      createForm.refund_type === t
                        ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                        : 'border-bd-border'
                    }`}
                  >
                    {t === 'full' ? '全额退款' : '部分退款'}
                  </button>
                ))}
              </div>
              <input
                value={createForm.amountYuan}
                onChange={(e) => setCreateForm({ ...createForm, amountYuan: e.target.value })}
                placeholder="代录金额（元，可选；不传按规则计算）"
                className="w-full rounded border px-2 py-1.5 text-sm"
              />
              <textarea
                value={createForm.reason}
                onChange={(e) => setCreateForm({ ...createForm, reason: e.target.value })}
                rows={2}
                placeholder="申请事由（必填，如：邮件协商退一半）"
                className="w-full rounded border px-2 py-1.5 text-sm"
              />
              <textarea
                value={createForm.note}
                onChange={(e) => setCreateForm({ ...createForm, note: e.target.value })}
                rows={2}
                placeholder="代录备注（可选，写入审批意见栏）"
                className="w-full rounded border px-2 py-1.5 text-sm"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="rounded border border-bd-border px-3 py-1.5 text-xs text-bd-muted"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleCreate()}
                disabled={working || !createForm.order_id.trim() || !createForm.reason.trim()}
                className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              >
                {working ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                代录并待审批
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div
          role="alert"
          className={`fixed bottom-8 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium shadow-lg z-[120] ${
            toast.type === 'success' ? 'bg-emerald-600/95 text-white' : 'bg-red-600/95 text-white'
          }`}
        >
          {toast.msg}
        </div>
      )}

    </section>
  );
}
