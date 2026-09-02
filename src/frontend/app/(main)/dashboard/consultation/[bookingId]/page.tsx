'use client';

/**
 * 咨询预约问卷页（P-D）
 * /dashboard/consultation/[bookingId]
 *
 * 状态视图：
 * - pending_survey：问卷表单（选报告/主题/候选时间段/联系方式/备注）
 * - submitted：已提交，等待管理员联系确认时间
 * - scheduled：已预约（显示实际时间）
 * - completed：已完成
 * - cancelled：已取消（退款）
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  CalendarCheck,
  Check,
  CheckCircle2,
  ChevronLeft,
  Clock,
  Loader2,
  Plus,
  Send,
  X,
  XCircle,
} from 'lucide-react';
import { useLocale } from '@/hooks/useLocale';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  fetchBooking,
  fetchMyReports,
  submitSurvey,
  type ConsultationBooking,
  type MyReportItem,
} from '@/lib/api/consultation';

export default function ConsultationBookingPage() {
  const { t } = useLocale();
  const router = useRouter();
  const params = useParams();
  const bookingId = String(params?.bookingId ?? '');

  const [booking, setBooking] = useState<ConsultationBooking | null>(null);
  const [reports, setReports] = useState<MyReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 表单状态
  const [reportId, setReportId] = useState('');
  const [topics, setTopics] = useState('');
  const [slots, setSlots] = useState<string[]>(['']);
  const [contact, setContact] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const load = useCallback(async () => {
    if (!bookingId) return;
    setLoading(true);
    setError(null);
    try {
      const [b, r] = await Promise.all([fetchBooking(bookingId), fetchMyReports()]);
      setBooking(b);
      setReports(r);
      if (r.length > 0 && !reportId) setReportId(r[0].report_id);
    } catch (e) {
      setError(getApiErrorMessage(e, t('consultation.loadFailed')));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);

  useEffect(() => {
    void load();
  }, [load]);

  const addSlot = () => {
    if (slots.length < 5) setSlots([...slots, '']);
  };
  const removeSlot = (idx: number) => {
    setSlots(slots.filter((_, i) => i !== idx));
  };
  const updateSlot = (idx: number, value: string) => {
    setSlots(slots.map((s, i) => (i === idx ? value : s)));
  };

  const handleSubmit = async () => {
    setFormError(null);
    const filledSlots = slots.map((s) => s.trim()).filter(Boolean);
    if (!reportId) return setFormError(t('consultation.errReport'));
    if (!topics.trim()) return setFormError(t('consultation.errTopics'));
    if (filledSlots.length === 0) return setFormError(t('consultation.errSlots'));
    if (!contact.trim()) return setFormError(t('consultation.errContact'));

    setSubmitting(true);
    try {
      const updated = await submitSurvey(bookingId, {
        report_id: reportId,
        topics: topics.trim(),
        time_slots: filledSlots,
        contact: contact.trim(),
        note: note.trim() || undefined,
      });
      setBooking(updated);
      showToast(t('consultation.submitSuccess'));
    } catch (e) {
      setFormError(getApiErrorMessage(e, t('consultation.submitFailed')));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <button
        type="button"
        onClick={() => router.push('/dashboard/codes?tab=orders')}
        className="flex items-center gap-2 text-sm text-bd-subtle hover:text-bd-muted transition-colors"
      >
        <ChevronLeft size={16} />
        {t('consultation.backOrders')}
      </button>

      <header>
        <h1 className="text-2xl font-bold text-bd-fg">{t('consultation.title')}</h1>
        <p className="text-sm text-bd-muted mt-1">{t('consultation.subtitle')}</p>
      </header>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 size={24} className="animate-spin text-bd-subtle" />
        </div>
      ) : error ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-8 text-center space-y-4">
          <p className="text-sm text-bd-err">{error}</p>
          <button
            type="button"
            onClick={() => void load()}
            className="text-sm text-bd-ui-accent hover:opacity-80"
          >
            {t('consultation.retry')}
          </button>
        </div>
      ) : booking?.status === 'pending_survey' ? (
        /* ─── 问卷表单 ─── */
        <section className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-6 space-y-5">
          {/* 选择报告 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-bd-fg">{t('consultation.fieldReport')}</label>
            <select
              value={reportId}
              onChange={(e) => setReportId(e.target.value)}
              className="w-full rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg focus:outline-none focus:ring-1 focus:ring-bd-ui-accent"
            >
              {reports.map((r) => (
                <option key={r.report_id} value={r.report_id}>
                  {r.activation_code}
                </option>
              ))}
            </select>
          </div>

          {/* 主题/期望 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-bd-fg">{t('consultation.fieldTopics')}</label>
            <textarea
              value={topics}
              onChange={(e) => setTopics(e.target.value)}
              rows={4}
              placeholder={t('consultation.topicsPlaceholder')}
              className="w-full rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg placeholder:text-bd-subtle focus:outline-none focus:ring-1 focus:ring-bd-ui-accent"
            />
          </div>

          {/* 候选时间段 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-bd-fg">{t('consultation.fieldSlots')}</label>
            {slots.map((slot, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <input
                  value={slot}
                  onChange={(e) => updateSlot(idx, e.target.value)}
                  placeholder={t('consultation.slotPlaceholder')}
                  className="flex-1 rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg placeholder:text-bd-subtle focus:outline-none focus:ring-1 focus:ring-bd-ui-accent"
                />
                {slots.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeSlot(idx)}
                    className="p-1.5 text-bd-subtle hover:text-bd-err"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            ))}
            {slots.length < 5 && (
              <button
                type="button"
                onClick={addSlot}
                className="inline-flex items-center gap-1 text-xs text-bd-ui-accent hover:opacity-80"
              >
                <Plus size={14} />
                {t('consultation.addSlot')}
              </button>
            )}
          </div>

          {/* 联系方式 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-bd-fg">{t('consultation.fieldContact')}</label>
            <input
              value={contact}
              onChange={(e) => setContact(e.target.value)}
              placeholder={t('consultation.contactPlaceholder')}
              className="w-full rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg placeholder:text-bd-subtle focus:outline-none focus:ring-1 focus:ring-bd-ui-accent"
            />
          </div>

          {/* 备注 */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-bd-fg">
              {t('consultation.fieldNote')}
              <span className="ml-1 text-xs text-bd-subtle">{t('consultation.optional')}</span>
            </label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg focus:outline-none focus:ring-1 focus:ring-bd-ui-accent"
            />
          </div>

          {formError && <p className="text-xs text-bd-err">{formError}</p>}

          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={submitting}
            className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-bd-ui-accent text-bd-ui-accent-fg px-4 py-3 text-sm font-semibold hover:opacity-90 disabled:opacity-60"
          >
            {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            {t('consultation.submit')}
          </button>
        </section>
      ) : (
        /* ─── 状态视图 ─── */
        <section className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-8 text-center space-y-4">
          {booking?.status === 'submitted' && (
            <>
              <Clock className="w-10 h-10 mx-auto text-amber-500" />
              <h2 className="text-lg font-semibold text-bd-fg">{t('consultation.submittedTitle')}</h2>
              <p className="text-sm text-bd-muted">{t('consultation.submittedDesc')}</p>
            </>
          )}
          {booking?.status === 'scheduled' && (
            <>
              <CalendarCheck className="w-10 h-10 mx-auto text-emerald-500" />
              <h2 className="text-lg font-semibold text-bd-fg">{t('consultation.scheduledTitle')}</h2>
              <p className="text-sm text-bd-muted">
                {t('consultation.scheduledDesc')}
                <span className="block mt-1 font-medium text-bd-fg">
                  {booking.scheduled_at
                    ? new Date(booking.scheduled_at).toLocaleString()
                    : '—'}
                </span>
              </p>
            </>
          )}
          {booking?.status === 'completed' && (
            <>
              <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500" />
              <h2 className="text-lg font-semibold text-bd-fg">{t('consultation.completedTitle')}</h2>
              <p className="text-sm text-bd-muted">{t('consultation.completedDesc')}</p>
            </>
          )}
          {booking?.status === 'cancelled' && (
            <>
              <XCircle className="w-10 h-10 mx-auto text-bd-subtle" />
              <h2 className="text-lg font-semibold text-bd-fg">{t('consultation.cancelledTitle')}</h2>
              <p className="text-sm text-bd-muted">{t('consultation.cancelledDesc')}</p>
            </>
          )}

          {/* 已提交问卷的回显 */}
          {booking?.topics && (
            <div className="mt-4 text-left rounded-xl border border-bd-border bg-bd-card p-4 space-y-2">
              <h3 className="text-xs font-semibold text-bd-subtle">{t('consultation.yourSurvey')}</h3>
              <p className="text-sm text-bd-fg whitespace-pre-wrap">{booking.topics}</p>
              {booking.time_slots.length > 0 && (
                <p className="text-xs text-bd-muted">
                  {t('consultation.fieldSlots')}：{booking.time_slots.join(' / ')}
                </p>
              )}
            </div>
          )}
        </section>
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
