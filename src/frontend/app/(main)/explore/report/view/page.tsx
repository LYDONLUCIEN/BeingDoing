'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { FileText, ChevronLeft, Download, Loader2, Clock } from 'lucide-react';
import { PHASES, getLastActivationCode } from '@/lib/explore/session';
import LikedContentSection from '@/components/explore/LikedContentSection';
import PurchaseModal from '@/components/payment/PurchaseModal';
import { useLocale } from '@/hooks/useLocale';
import { getMyReportId, getMyReportInfo, type MyReportInfo } from '@/lib/api/report';
import { fetchReportAuthorize, setReportAuthorize } from '@/lib/api/teamAnalysis';
import { useReportPdfDownload } from '@/hooks/useReportPdfDownload';
import { Headphones, Share2 } from 'lucide-react';

export default function ReportViewPage() {
  const router = useRouter();
  const { t, locale } = useLocale();

  const activationCode = useMemo(() => getLastActivationCode(), []);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [consultOpen, setConsultOpen] = useState(false);

  // 报告审核状态（阻塞式审核流：pending_review 时不展示报告内容与下载入口）
  const [reportInfo, setReportInfo] = useState<MyReportInfo | null>(null);
  const [infoLoading, setInfoLoading] = useState(false);

  const { status, error: pdfError, download } = useReportPdfDownload({ activationCode });

  useEffect(() => {
    if (!activationCode) return;
    let cancelled = false;
    setInfoLoading(true);
    getMyReportInfo(activationCode)
      .then((info) => {
        if (!cancelled) setReportInfo(info);
      })
      .catch(() => {
        // 查询失败时保持原页面行为（下载按钮点击时另有错误提示）
      })
      .finally(() => {
        if (!cancelled) setInfoLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activationCode]);

  const handleDownloadPdf = async () => {
    if (!activationCode || status === 'generating') return;
    setFetchError(null);
    try {
      const reportId = await getMyReportId(activationCode);
      if (!reportId) {
        setFetchError('未找到您的报告，请先完成探索流程。');
        return;
      }
      await download(reportId);
    } catch (e: any) {
      setFetchError('获取报告信息失败，请稍后重试。');
    }
  };

  const isGenerating = status === 'generating';
  const displayError = fetchError || pdfError;

  const isPendingReview = reportInfo?.review_status === 'pending_review';
  const isNotStarted = reportInfo?.review_status === 'not_started';

  const reviewDeadlineText = useMemo(() => {
    if (!reportInfo?.review_deadline) return null;
    const d = new Date(reportInfo.review_deadline);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  }, [reportInfo?.review_deadline, locale]);

  // 审核状态查询中：避免先闪现报告内容再切换到占位
  if (infoLoading && !reportInfo) {
    return (
      <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
        <Loader2 size={24} className="animate-spin text-bd-subtle" />
      </div>
    );
  }

  // 报告审核中：全页占位，不渲染报告内容与下载按钮
  if (isPendingReview) {
    return (
      <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-lg w-full text-center space-y-8"
        >
          <button
            type="button"
            onClick={() => router.back()}
            className="flex items-center gap-2 text-sm text-bd-subtle hover:text-bd-muted transition-colors"
          >
            <ChevronLeft size={16} />
            {t('explore.report.back')}
          </button>

          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-500/15 border-2 border-amber-500">
            <Clock className="w-7 h-7 text-amber-500" />
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl font-bold">{t('explore.report.reviewPendingTitle')}</h1>
            <p className="text-bd-muted leading-relaxed">{t('explore.report.reviewPendingDesc')}</p>
          </div>

          {reviewDeadlineText && (
            <div className="rounded-xl border border-bd-border bg-bd-card p-6 space-y-1">
              <p className="text-xs text-bd-subtle">{t('explore.report.reviewDeadlineLabel')}</p>
              <p className="text-sm font-medium text-bd-fg">{reviewDeadlineText}</p>
            </div>
          )}

          <button
            type="button"
            onClick={() => router.push('/')}
            className="text-sm text-bd-subtle hover:text-bd-muted transition-colors underline underline-offset-4"
          >
            {t('explore.report.backHome')}
          </button>
        </motion.div>
      </div>
    );
  }

  // 五阶段未完成：报告尚未解锁（完成五阶段后首次进入本页即开始审核计时）
  if (isNotStarted) {
    return (
      <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-lg w-full text-center space-y-8"
        >
          <button
            type="button"
            onClick={() => router.back()}
            className="flex items-center gap-2 text-sm text-bd-subtle hover:text-bd-muted transition-colors"
          >
            <ChevronLeft size={16} />
            {t('explore.report.back')}
          </button>

          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-bd-overlay-md border-2 border-bd-border">
            <FileText className="w-7 h-7 text-bd-subtle" />
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl font-bold">{t('explore.report.reviewNotStartedTitle')}</h1>
            <p className="text-bd-muted leading-relaxed">{t('explore.report.reviewNotStartedDesc')}</p>
          </div>

          <button
            type="button"
            onClick={() => router.push('/')}
            className="text-sm text-bd-subtle hover:text-bd-muted transition-colors underline underline-offset-4"
          >
            {t('explore.report.backHome')}
          </button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="max-w-lg w-full text-center space-y-8"
      >
        <button
          type="button"
          onClick={() => router.back()}
          className="flex items-center gap-2 text-sm text-bd-subtle hover:text-bd-muted transition-colors"
        >
          <ChevronLeft size={16} />
          {t('explore.report.back')}
        </button>

        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-bd-ui-accent/20 border-2 border-[var(--bd-ui-accent)]">
          <FileText className="w-7 h-7" style={{ color: 'var(--bd-ui-accent)' }} />
        </div>

        <div className="space-y-3">
          <p className="text-xs tracking-widest uppercase text-bd-subtle">{t('explore.report.complete')}</p>
          <h1 className="text-3xl font-bold">{t('explore.report.title')}</h1>
          <p className="text-bd-muted leading-relaxed">
            {t('explore.report.desc')}
            <br />
            {t('explore.report.developing')}
          </p>
        </div>

        {/* PDF 下载按钮 */}
        {activationCode && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={handleDownloadPdf}
              disabled={isGenerating}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-6 py-3 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {isGenerating ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  报告生成中，请勿关闭页面...
                </>
              ) : (
                <>
                  <Download size={16} />
                  下载 PDF 报告
                </>
              )}
            </button>
            {isGenerating && (
              <p className="text-xs text-bd-subtle animate-pulse">
                AI 正在为您撰写专属报告，通常需要 10-30 秒
              </p>
            )}
            {displayError && (
              <p className="text-xs text-red-500">{displayError}</p>
            )}
          </div>
        )}

        <div className="rounded-xl border border-bd-border bg-bd-card p-6 text-left space-y-4">
          <h3 className="font-semibold text-bd-fg">{t('explore.report.summary')}</h3>
          <p className="text-sm text-bd-muted leading-relaxed">{t('explore.report.summaryDesc')}</p>
        </div>

        {/* 报告解读咨询购买卡（P-D） */}
        <div className="rounded-xl border border-[var(--bd-ui-accent)]/40 bg-bd-card p-6 text-left space-y-3">
          <div className="flex items-center gap-2">
            <Headphones className="w-5 h-5" style={{ color: 'var(--bd-ui-accent)' }} />
            <h3 className="font-semibold text-bd-fg">{t('explore.report.consultTitle')}</h3>
            <span className="ml-auto text-lg font-bold text-bd-fg">¥298</span>
          </div>
          <p className="text-sm text-bd-muted leading-relaxed">{t('explore.report.consultDesc')}</p>
          <button
            type="button"
            onClick={() => setConsultOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-5 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity"
          >
            {t('explore.report.consultCta')}
          </button>
        </div>

        <PurchaseModal
          open={consultOpen}
          onClose={() => setConsultOpen(false)}
          defaultProductType="consultation"
        />

        {/* 报告授权开关（P-E：赠品码激活人授权报告给所属人） */}
        {activationCode && <ReportAuthorizeCard activationCode={activationCode} />}

        {activationCode && <LikedContentSection activationCode={activationCode} />}

        <div className="grid grid-cols-2 gap-3">
          {PHASES.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => router.push(`/explore/chat/${p.key}`)}
              className="rounded-xl border border-bd-border bg-bd-card hover:bg-bd-overlay-md px-4 py-3 text-sm transition-colors text-left"
            >
              <span className="text-xs font-mono text-bd-ghost block mb-0.5">{p.num}</span>
              <span className="font-medium text-bd-fg">{p.label}</span>
              <span className="text-xs text-bd-subtle block mt-0.5">{t('explore.report.reviewChat')}</span>
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => router.push('/')}
          className="text-sm text-bd-subtle hover:text-bd-muted transition-colors underline underline-offset-4"
        >
          {t('explore.report.backHome')}
        </button>
      </motion.div>
    </div>
  );
}

/** 报告授权开关卡（P-E，ADR-0010）：仅赠品码的激活人可见；授权内容仅为报告 */
function ReportAuthorizeCard({ activationCode }: { activationCode: string }) {
  const { t } = useLocale();
  const [state, setState] = useState<{ authorized: boolean; purchaser_email: string | null } | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchReportAuthorize(activationCode)
      .then((s) => {
        if (!cancelled && s.is_activator && s.purchaser_email) {
          setState({ authorized: s.authorized, purchaser_email: s.purchaser_email });
        }
      })
      .catch(() => {
        /* 无所属人或查询失败：不展示该卡 */
      });
    return () => {
      cancelled = true;
    };
  }, [activationCode]);

  if (!state) return null;

  const toggle = async () => {
    setWorking(true);
    try {
      const res = await setReportAuthorize(activationCode, !state.authorized);
      setState({ ...state, authorized: res.authorized });
    } catch {
      /* 保持原状态 */
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="rounded-xl border border-bd-border bg-bd-card p-5 text-left space-y-2">
      <div className="flex items-center gap-2">
        <Share2 className="w-4 h-4 text-bd-muted" />
        <h3 className="text-sm font-semibold text-bd-fg">{t('explore.report.authTitle')}</h3>
        <button
          type="button"
          role="switch"
          aria-checked={state.authorized}
          disabled={working}
          onClick={() => void toggle()}
          className={`ml-auto relative h-6 w-11 rounded-full transition-colors ${
            state.authorized ? 'bg-emerald-500' : 'bg-bd-overlay-md'
          } ${working ? 'opacity-60' : ''}`}
        >
          <span
            className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
              state.authorized ? 'translate-x-[22px]' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>
      <p className="text-xs text-bd-muted leading-relaxed">
        {t('explore.report.authDesc', { purchaser: state.purchaser_email ?? '' })}
      </p>
    </div>
  );
}
