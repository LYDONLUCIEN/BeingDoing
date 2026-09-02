'use client';

/**
 * 咨询预约列表页（P-D）
 * /dashboard/consultation
 *
 * 站内信/交付邮件的统一入口（文案不写内部 booking_id UUID），
 * 列出我的全部咨询预约单，点击进入详情/问卷页。
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  CalendarCheck,
  CheckCircle2,
  ChevronRight,
  Clock,
  Loader2,
  PenLine,
  XCircle,
} from 'lucide-react';
import { useLocale } from '@/hooks/useLocale';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  fetchMyBookings,
  type ConsultationBooking,
  type ConsultationStatus,
} from '@/lib/api/consultation';

const STATUS_ICON: Record<ConsultationStatus, typeof Clock> = {
  pending_survey: PenLine,
  submitted: Clock,
  scheduled: CalendarCheck,
  completed: CheckCircle2,
  cancelled: XCircle,
};

const STATUS_COLOR: Record<ConsultationStatus, string> = {
  pending_survey: 'text-amber-500',
  submitted: 'text-amber-500',
  scheduled: 'text-emerald-500',
  completed: 'text-emerald-500',
  cancelled: 'text-bd-subtle',
};

export default function ConsultationListPage() {
  const { t } = useLocale();
  const router = useRouter();

  const [bookings, setBookings] = useState<ConsultationBooking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const statusLabel: Record<ConsultationStatus, string> = {
    pending_survey: t('consultation.statusPendingSurvey'),
    submitted: t('consultation.statusSubmitted'),
    scheduled: t('consultation.statusScheduled'),
    completed: t('consultation.statusCompleted'),
    cancelled: t('consultation.statusCancelled'),
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMyBookings(1, 50);
      setBookings(res.items);
    } catch (e) {
      setError(getApiErrorMessage(e, t('consultation.loadFailed')));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-bd-fg">{t('consultation.listTitle')}</h1>
        <p className="text-sm text-bd-muted mt-1">{t('consultation.listSubtitle')}</p>
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
      ) : bookings.length === 0 ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-8 text-center space-y-3">
          <p className="text-sm text-bd-fg">{t('consultation.listEmpty')}</p>
          <p className="text-xs text-bd-muted">{t('consultation.listEmptyHint')}</p>
          <button
            type="button"
            onClick={() => router.push('/dashboard/codes?tab=orders')}
            className="text-sm text-bd-ui-accent hover:opacity-80"
          >
            {t('consultation.goOrders')}
          </button>
        </div>
      ) : (
        <ul className="space-y-3">
          {bookings.map((b) => {
            const Icon = STATUS_ICON[b.status] ?? Clock;
            return (
              <li key={b.id}>
                <button
                  type="button"
                  onClick={() => router.push(`/dashboard/consultation/${b.id}`)}
                  className="w-full bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-4 flex items-center gap-3 text-left hover:border-bd-ui-accent/50 transition-colors"
                >
                  <Icon size={20} className={STATUS_COLOR[b.status] ?? 'text-bd-subtle'} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-bd-fg">
                      {t('consultation.title')}
                      <span className={`ml-2 text-xs ${STATUS_COLOR[b.status] ?? ''}`}>
                        {statusLabel[b.status] ?? b.status}
                      </span>
                    </p>
                    <p className="text-xs text-bd-muted mt-0.5">
                      {b.status === 'scheduled' && b.scheduled_at
                        ? `${t('consultation.scheduledDesc')} ${new Date(b.scheduled_at).toLocaleString()}`
                        : `${t('consultation.createdAt')}：${
                            b.created_at ? new Date(b.created_at).toLocaleString() : '—'
                          }`}
                    </p>
                  </div>
                  <ChevronRight size={16} className="text-bd-subtle shrink-0" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
