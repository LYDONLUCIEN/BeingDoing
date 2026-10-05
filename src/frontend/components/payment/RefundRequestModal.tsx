'use client';

/**
 * 退款申请弹窗（用户侧，2026-10-05 统一退款申请单）
 *
 * 数据源 GET /payment/orders/{id}/refund-options：行级分摊明细（码 × 分摊实付 ×
 * 实时状态）+ 全退/部分退可用性 + 在途申请与历史。
 * - 全退：一行确认（金额 = 剩余可退）
 * - 部分退（仅年度套餐/咨询）：勾选要退的码（金额 = Σ 所选行分摊实付，实时合计）
 * - 待审批申请可撤回；驳回理由用户可见；驳回/撤回后可重新申请
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, RotateCcw, X } from 'lucide-react';
import { getApiErrorMessage, isRequestCanceled } from '@/lib/api/client';
import {
  createRefundRequest,
  fenToYuan,
  fetchRefundOptions,
  withdrawRefund,
  type OrderItem,
  type RefundLineItem,
  type RefundOptions,
} from '@/lib/api/payment';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

const STATUS_LABEL: Record<string, string> = {
  pending_review: '待审批',
  refunding: '退款中',
  succeeded: '已退款',
  failed: '退款失败',
  rejected: '已驳回',
  withdrawn: '已撤回',
};

interface Props {
  order: OrderItem;
  onClose: () => void;
  /** 申请/撤回成功后回调（外层刷新订单列表） */
  onChanged: () => void;
}

export default function RefundRequestModal({ order, onClose, onChanged }: Props) {
  const [options, setOptions] = useState<RefundOptions | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [refundType, setRefundType] = useState<'full' | 'partial'>('full');
  const [selectedLineIds, setSelectedLineIds] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [workingWithdraw, setWorkingWithdraw] = useState(false);

  const loadOptions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchRefundOptions(order.id);
      setOptions(data);
      setRefundType(data.full_allowed ? 'full' : 'partial');
      setError(null);
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [order.id]);

  useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  const availableLines = useMemo(
    () => (options?.lines ?? []).filter((l) => l.effective_status === 'available'),
    [options]
  );

  const selectedAmount = useMemo(
    () =>
      availableLines
        .filter((l) => selectedLineIds.includes(l.id))
        .reduce((sum, l) => sum + l.amount_paid_alloc, 0),
    [availableLines, selectedLineIds]
  );

  const fullAmount = options?.remaining_refundable ?? 0;

  const canSubmit = useMemo(() => {
    if (submitting || !options) return false;
    if (!reason.trim()) return false;
    if (refundType === 'full') return options.full_allowed;
    return options.partial_allowed && selectedLineIds.length > 0;
  }, [submitting, options, reason, refundType, selectedLineIds]);

  const toggleLine = (line: RefundLineItem) => {
    setSelectedLineIds((prev) =>
      prev.includes(line.id) ? prev.filter((id) => id !== line.id) : [...prev, line.id]
    );
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await createRefundRequest(order.id, {
        refund_type: refundType,
        line_ids: refundType === 'partial' ? selectedLineIds : undefined,
        reason: reason.trim(),
      });
      onChanged();
      onClose();
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      setError(getApiErrorMessage(e));
      // 守卫被触发（如码刚被用）时刷新能力视图
      void loadOptions();
    } finally {
      setSubmitting(false);
    }
  };

  const handleWithdraw = async () => {
    const pending = options?.pending_request;
    if (!pending || workingWithdraw) return;
    setWorkingWithdraw(true);
    try {
      await withdrawRefund(pending.id);
      await loadOptions();
      onChanged();
    } catch (e: unknown) {
      if (isRequestCanceled(e)) return;
      setError(getApiErrorMessage(e));
    } finally {
      setWorkingWithdraw(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="text-lg font-semibold">申请退款</h3>
            <p className="mt-1 text-sm text-gray-500">
              订单号 <span className="font-mono">{order.order_no}</span> · 实付 ¥
              {fenToYuan(order.amount_paid)}
              {(order.amount_refunded ?? 0) > 0 && (
                <span className="ml-1 text-purple-600">
                  （已退 ¥{fenToYuan(order.amount_refunded ?? 0)}）
                </span>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            aria-label="关闭"
          >
            <X size={20} />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-10 text-gray-400">
            <Loader2 className="mr-2 animate-spin" size={18} />
            加载退款信息…
          </div>
        )}

        {!loading && error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!loading && options && (
          <>
            {/* 在途申请 */}
            {options.pending_request && (
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-amber-800">
                    待审批申请（¥{fenToYuan(options.pending_request.requested_amount)}）
                  </span>
                  <button
                    onClick={() => void handleWithdraw()}
                    disabled={workingWithdraw}
                    className="flex items-center gap-1 rounded-md border border-amber-300 bg-white px-2 py-1 text-xs text-amber-700 hover:bg-amber-100 disabled:opacity-50"
                  >
                    {workingWithdraw ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <RotateCcw size={12} />
                    )}
                    撤回申请
                  </button>
                </div>
                <p className="mt-1 text-amber-700">
                  提交于 {formatLocalDateTime(options.pending_request.created_at)}，请等待管理员审批。
                </p>
              </div>
            )}

            {/* 不可退提示 */}
            {!options.full_allowed && !options.partial_allowed && !options.pending_request && (
              <div className="mb-4 rounded-lg bg-gray-100 p-4 text-sm text-gray-600">
                该订单当前不可退款（激活码已被使用、咨询已预约或订单状态不允许）。
                如有特殊情况请通过反馈渠道联系我们。
              </div>
            )}

            {/* 历史申请（含驳回理由） */}
            {options.history.length > 0 && (
              <details className="mb-4 rounded-lg border px-3 py-2 text-sm">
                <summary className="cursor-pointer text-gray-600">
                  历史退款申请（{options.history.length} 条）
                </summary>
                <ul className="mt-2 space-y-2">
                  {options.history.map((r) => (
                    <li key={r.id} className="rounded bg-gray-50 p-2 text-xs text-gray-600">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono">{r.refund_no}</span>
                        <span className="rounded bg-white px-1.5 py-0.5">
                          {STATUS_LABEL[r.status] ?? r.status}
                        </span>
                        <span>
                          {r.refund_type === 'full' ? '全额' : '部分'} ¥
                          {fenToYuan(r.requested_amount)}
                          {r.approved_amount != null &&
                            r.approved_amount !== r.requested_amount &&
                            ` → 批准 ¥${fenToYuan(r.approved_amount)}`}
                        </span>
                      </div>
                      {r.reason_admin && (
                        <p className="mt-1 text-gray-500">管理员：{r.reason_admin}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {/* 申请表单 */}
            {(options.full_allowed || options.partial_allowed) && !options.pending_request && (
              <div className="space-y-4">
                {options.full_allowed && options.partial_allowed && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => setRefundType('full')}
                      className={`flex-1 rounded-lg border px-3 py-2 text-sm ${
                        refundType === 'full'
                          ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      全额退款 ¥{fenToYuan(fullAmount)}
                    </button>
                    <button
                      onClick={() => {
                        setRefundType('partial');
                        setSelectedLineIds([]);
                      }}
                      className={`flex-1 rounded-lg border px-3 py-2 text-sm ${
                        refundType === 'partial'
                          ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      部分退款
                    </button>
                  </div>
                )}

                {refundType === 'full' && (
                  <div className="rounded-lg bg-indigo-50 p-3 text-sm text-indigo-800">
                    退款金额 <strong>¥{fenToYuan(fullAmount)}</strong>，原路退回支付账户；
                    退款成功后订单内全部激活码将作废。
                  </div>
                )}

                {refundType === 'partial' && options.partial_allowed && (
                  <div>
                    <p className="mb-2 text-sm text-gray-600">
                      选择要退款的激活码（每枚按分摊实付折算，退多少作废多少）：
                    </p>
                    <ul className="max-h-44 space-y-1 overflow-y-auto">
                      {availableLines.map((line) => (
                        <li key={line.id}>
                          <label className="flex cursor-pointer items-center justify-between rounded-lg border px-3 py-2 text-sm hover:bg-gray-50">
                            <span className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={selectedLineIds.includes(line.id)}
                                onChange={() => toggleLine(line)}
                                className="h-4 w-4 accent-indigo-600"
                              />
                              <span className="font-mono">{line.item_ref}</span>
                            </span>
                            <span className="text-gray-500">¥{fenToYuan(line.amount_paid_alloc)}</span>
                          </label>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-2 text-right text-sm text-gray-600">
                      已选 {selectedLineIds.length} 项，合计{' '}
                      <strong className="text-indigo-700">¥{fenToYuan(selectedAmount)}</strong>
                    </p>
                  </div>
                )}

                <div>
                  <label className="mb-1 block text-sm text-gray-600">退款理由（必填）</label>
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    rows={3}
                    maxLength={500}
                    placeholder="请说明退款原因，便于我们更快处理"
                    className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-indigo-400 focus:outline-none"
                  />
                </div>

                {error && (
                  <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                    <AlertCircle size={16} className="mt-0.5 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <button
                    onClick={onClose}
                    className="rounded-lg border border-gray-200 px-4 py-2 text-sm hover:bg-gray-50"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => void handleSubmit()}
                    disabled={!canSubmit}
                    className="flex items-center gap-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {submitting ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <CheckCircle2 size={14} />
                    )}
                    提交申请
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
