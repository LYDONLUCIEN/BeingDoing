'use client';

/**
 * Admin 咨询管理页（P-D）
 * /admin/consultations
 *
 * 状态机：pending_survey（待填问卷）→ submitted（已提交）→ scheduled（已预约）→ completed（已完成）
 * 操作：submitted → 「标记预约」（填实际时间+备注）；scheduled → 「标记完成」
 * 退款走「支付管理 → 订单管理」（仅未预约可退）。
 */

import { useCallback, useEffect, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Copy, Loader2, X } from 'lucide-react';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  adminCompleteConsultation,
  adminListConsultations,
  adminScheduleConsultation,
  type ConsultationBooking,
  type ConsultationStatus,
} from '@/lib/api/consultation';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

const PAGE_SIZE = 20;

type StatusFilter = 'all' | ConsultationStatus;

const STATUS_META: Record<string, { label: string; cls: string }> = {
  pending_survey: { label: '待填问卷', cls: 'bg-amber-500/15 text-amber-600 border-amber-500/40' },
  submitted: { label: '已提交', cls: 'bg-sky-500/15 text-sky-600 border-sky-500/40' },
  scheduled: { label: '已预约', cls: 'bg-emerald-500/15 text-emerald-600 border-emerald-500/40' },
  completed: { label: '已完成', cls: 'bg-stone-500/15 text-stone-500 border-stone-500/40' },
  cancelled: { label: '已取消', cls: 'bg-stone-500/15 text-stone-400 border-stone-500/30' },
};

export default function AdminConsultationsPage() {
  const [items, setItems] = useState<ConsultationBooking[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<StatusFilter>('all');
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // 详情/预约弹窗
  const [detail, setDetail] = useState<ConsultationBooking | null>(null);
  const [scheduleTime, setScheduleTime] = useState('');
  const [scheduleNote, setScheduleNote] = useState('');
  const [acting, setActing] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminListConsultations({
        status: status === 'all' ? undefined : status,
        page,
        page_size: PAGE_SIZE,
      });
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      showToast(getApiErrorMessage(e, '加载失败'));
    } finally {
      setLoading(false);
    }
  }, [status, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const copyText = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(key);
      setTimeout(() => setCopiedId(null), 1500);
    } catch {
      /* 忽略剪贴板失败 */
    }
  };

  const openDetail = (booking: ConsultationBooking) => {
    setDetail(booking);
    setScheduleTime('');
    setScheduleNote('');
  };

  const handleSchedule = async () => {
    if (!detail || !scheduleTime.trim()) {
      showToast('请填写预约时间（如 2026-07-25 20:00）');
      return;
    }
    setActing(true);
    try {
      await adminScheduleConsultation(detail.id, {
        scheduled_at: scheduleTime.trim(),
        admin_note: scheduleNote.trim() || undefined,
      });
      showToast('已标记预约');
      setDetail(null);
      void load();
    } catch (e) {
      showToast(getApiErrorMessage(e, '操作失败'));
    } finally {
      setActing(false);
    }
  };

  const handleComplete = async (booking: ConsultationBooking) => {
    if (!window.confirm('确认该咨询已完成？')) return;
    try {
      await adminCompleteConsultation(booking.id);
      showToast('已标记完成');
      void load();
    } catch (e) {
      showToast(getApiErrorMessage(e, '操作失败'));
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-bd-fg">咨询管理</h1>
        <p className="text-sm text-bd-muted mt-1">
          报告解读咨询（¥298/次）预约单管理；退款请前往「支付管理 → 订单管理」（仅未预约可退）
        </p>
      </header>

      {/* 筛选 */}
      <div className="flex items-center gap-3">
        <label className="text-sm text-bd-muted">状态：</label>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as StatusFilter);
            setPage(1);
          }}
          className="rounded-lg border border-bd-border bg-bd-card px-3 py-1.5 text-sm text-bd-fg"
        >
          <option value="all">全部</option>
          <option value="pending_survey">待填问卷</option>
          <option value="submitted">已提交</option>
          <option value="scheduled">已预约</option>
          <option value="completed">已完成</option>
          <option value="cancelled">已取消</option>
        </select>
        <span className="ml-auto text-xs text-bd-subtle">共 {total} 条</span>
      </div>

      {/* 列表 */}
      <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border shadow-sm overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 size={24} className="animate-spin text-bd-subtle" />
          </div>
        ) : items.length === 0 ? (
          <p className="py-16 text-center text-sm text-bd-muted">暂无咨询预约单</p>
        ) : (
          <table className="min-w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-bd-border text-left text-bd-subtle">
                <th className="px-4 py-3 font-medium">用户</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium">联系方式</th>
                <th className="px-4 py-3 font-medium">主题</th>
                <th className="px-4 py-3 font-medium">预约时间</th>
                <th className="px-4 py-3 font-medium">创建时间</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((b) => {
                const meta = STATUS_META[b.status] ?? STATUS_META.cancelled;
                return (
                  <tr key={b.id} className="border-b border-bd-border/60 hover:bg-bd-overlay-md/40">
                    <td className="px-4 py-3 text-bd-fg">{b.user_email ?? b.user_id}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block rounded-full border px-2 py-0.5 ${meta.cls}`}>
                        {meta.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {b.contact ? (
                        <button
                          type="button"
                          onClick={() => void copyText(b.contact!, b.id)}
                          className="inline-flex items-center gap-1 text-bd-fg hover:text-bd-ui-accent"
                        >
                          <span className="max-w-[120px] truncate">{b.contact}</span>
                          {copiedId === b.id ? (
                            <Check size={12} className="text-emerald-500" />
                          ) : (
                            <Copy size={12} />
                          )}
                        </button>
                      ) : (
                        <span className="text-bd-subtle">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="block max-w-[200px] truncate text-bd-muted" title={b.topics ?? ''}>
                        {b.topics ?? <span className="text-bd-subtle">（未填问卷）</span>}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-bd-muted">
                      {b.scheduled_at ? formatLocalDateTime(b.scheduled_at) : '—'}
                    </td>
                    <td className="px-4 py-3 text-bd-muted">
                      {b.created_at ? formatLocalDateTime(b.created_at) : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => openDetail(b)}
                          className="rounded-lg border border-bd-border px-2 py-1 text-bd-fg hover:bg-bd-overlay-md"
                        >
                          详情
                        </button>
                        {b.status === 'submitted' && (
                          <button
                            type="button"
                            onClick={() => openDetail(b)}
                            className="rounded-lg border border-emerald-500/50 px-2 py-1 text-emerald-600 hover:bg-emerald-500/10"
                          >
                            标记预约
                          </button>
                        )}
                        {b.status === 'scheduled' && (
                          <button
                            type="button"
                            onClick={() => void handleComplete(b)}
                            className="rounded-lg border border-emerald-500/50 px-2 py-1 text-emerald-600 hover:bg-emerald-500/10"
                          >
                            标记完成
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 text-sm text-bd-muted">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            <ChevronLeft size={16} /> 上一页
          </button>
          <span>
            第 {page} 页 / 共 {totalPages} 页
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            下一页 <ChevronRight size={16} />
          </button>
        </div>
      )}

      {/* 详情/预约弹窗 */}
      {detail && (
        <div
          className="fixed inset-0 z-[210] flex items-center justify-center bg-black/40 p-4"
          onClick={() => setDetail(null)}
        >
          <div
            className="w-full max-w-lg rounded-2xl bg-bd-card border border-bd-border shadow-xl p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-bd-fg">咨询详情</h2>
              <button type="button" onClick={() => setDetail(null)} className="text-bd-subtle hover:text-bd-fg">
                <X size={18} />
              </button>
            </div>

            <dl className="space-y-2 text-sm">
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-bd-subtle">用户</dt>
                <dd className="text-bd-fg">{detail.user_email ?? detail.user_id}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-bd-subtle">状态</dt>
                <dd className="text-bd-fg">{STATUS_META[detail.status]?.label ?? detail.status}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-bd-subtle">报告</dt>
                <dd className="font-mono text-xs text-bd-fg">{detail.report_id ?? '（未选）'}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-bd-subtle">主题</dt>
                <dd className="text-bd-fg whitespace-pre-wrap">{detail.topics ?? '（未填问卷）'}</dd>
              </div>
              {detail.time_slots.length > 0 && (
                <div className="flex gap-2">
                  <dt className="w-20 shrink-0 text-bd-subtle">候选时间</dt>
                  <dd className="text-bd-fg">{detail.time_slots.join(' / ')}</dd>
                </div>
              )}
              <div className="flex gap-2">
                <dt className="w-20 shrink-0 text-bd-subtle">联系方式</dt>
                <dd className="text-bd-fg">{detail.contact ?? '—'}</dd>
              </div>
              {detail.note && (
                <div className="flex gap-2">
                  <dt className="w-20 shrink-0 text-bd-subtle">备注</dt>
                  <dd className="text-bd-fg whitespace-pre-wrap">{detail.note}</dd>
                </div>
              )}
            </dl>

            {detail.status === 'submitted' && (
              <div className="space-y-3 border-t border-bd-border pt-4">
                <h3 className="text-sm font-semibold text-bd-fg">标记已预约</h3>
                <input
                  value={scheduleTime}
                  onChange={(e) => setScheduleTime(e.target.value)}
                  placeholder="实际预约时间，如 2026-07-25 20:00"
                  className="w-full rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg placeholder:text-bd-subtle"
                />
                <input
                  value={scheduleNote}
                  onChange={(e) => setScheduleNote(e.target.value)}
                  placeholder="管理员备注（可选）"
                  className="w-full rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg placeholder:text-bd-subtle"
                />
                <button
                  type="button"
                  onClick={() => void handleSchedule()}
                  disabled={acting}
                  className="w-full rounded-xl bg-emerald-600 text-white px-4 py-2.5 text-sm font-semibold hover:bg-emerald-700 disabled:opacity-60"
                >
                  {acting ? '提交中...' : '确认预约'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[220] flex items-center gap-2 rounded-xl bg-stone-900 text-white px-4 py-2.5 text-sm shadow-lg">
          <Check size={16} className="text-emerald-400" />
          {toast}
        </div>
      )}
    </div>
  );
}
