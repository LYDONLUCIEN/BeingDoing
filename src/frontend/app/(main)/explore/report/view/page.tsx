'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { FileText, ChevronLeft, Download, Loader2, Clock } from 'lucide-react';
import {
  PHASES,
  clearLastActivationCode,
  getLastActivationCode,
  setLastActivationCode,
} from '@/lib/explore/session';
import LikedContentSection from '@/components/explore/LikedContentSection';
import ReportRecheckModal from '@/components/explore/ReportRecheckModal';
import PurchaseModal from '@/components/payment/PurchaseModal';
import { useLocale } from '@/hooks/useLocale';
import { getMyReportInfo, type MyReportInfo } from '@/lib/api/report';
import { fetchReportAuthorize, setReportAuthorize } from '@/lib/api/teamAnalysis';
import { useReportPdfDownload } from '@/hooks/useReportPdfDownload';
import { Headphones, Share2 } from 'lucide-react';

function ReportViewContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t, locale } = useLocale();

  // URL query code 优先于 localStorage；读到后写回「上次激活码」
  const codeParam = searchParams.get('code')?.trim() ?? '';
  const activationCode = useMemo(() => {
    if (codeParam) {
      setLastActivationCode(codeParam);
      return codeParam;
    }
    return getLastActivationCode();
  }, [codeParam]);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [consultOpen, setConsultOpen] = useState(false);

  // 报告审核状态（阻塞式审核流：pending_review 时不展示报告内容与下载入口）
  const [reportInfo, setReportInfo] = useState<MyReportInfo | null>(null);
  const [infoLoading, setInfoLoading] = useState(false);
  /** 查询流程是否结束（有码时等接口返回，无码立即为 true） */
  const [infoSettled, setInfoSettled] = useState(false);
  /** 403：当前账号无权查看该码的报告 */
  const [forbidden, setForbidden] = useState(false);

  const { status, error: pdfError, downloading, check, prepare, saveNow } = useReportPdfDownload({ activationCode });

  // 复核申请弹窗（报告复核体系：用户不能重新生成，只能申请复核）
  const [recheckOpen, setRecheckOpen] = useState(false);
  /** 复核进行中（pending/regenerating/pending_confirm）：显示提示条并禁用申请入口 */
  const recheckInProgress = reportInfo?.recheck_status != null;

  // 报告页加载后（approved）先查一次生成状态：
  // - 已有缓存（含提交时/审核期后台预生成完成）→ 直接显示「下载 PDF 报告」
  // - 生成失败 → 警示块（重试 / 申请复核）；无缓存且从未生成 → 「报告异常」警示块
  // statusChecked：首次 check 返回前不渲染异常警示块，避免 idle 闪现误报
  const [statusChecked, setStatusChecked] = useState(false);
  const reportId = reportInfo?.report_id ?? null;
  const isApproved = reportInfo?.review_status === 'approved';
  useEffect(() => {
    if (isApproved && reportId) {
      setStatusChecked(false);
      void check(reportId).then((s) => {
        setStatusChecked(true);
        // 后台正在生成（如审核期预生成未完成）：接管轮询，完成后自动变为「下载」按钮；
        // trigger 幂等（任务进行中不会重启），不会重复生成
        if (s === 'generating') void prepare(reportId);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isApproved, reportId]);

  useEffect(() => {
    if (!activationCode) {
      setInfoSettled(true);
      return;
    }
    let cancelled = false;
    setInfoLoading(true);
    setInfoSettled(false);
    setForbidden(false);
    setReportInfo(null);
    getMyReportInfo(activationCode)
      .then((info) => {
        if (!cancelled) setReportInfo(info);
      })
      .catch((e: any) => {
        if (cancelled) return;
        const status = e?.response?.status;
        if (status === 404) {
          // 该码无报告/码不存在：走「尚未解锁」分支
          setReportInfo({ report_id: null, review_status: 'not_started', review_deadline: null, recheck_status: null });
        } else if (status === 403) {
          // 无权查看：清除残留的本地激活码
          clearLastActivationCode();
          setForbidden(true);
        }
        // 其它查询失败保持原页面行为（下载按钮点击时另有错误提示）
      })
      .finally(() => {
        if (!cancelled) {
          setInfoLoading(false);
          setInfoSettled(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activationCode]);

  const handleGenerate = async () => {
    if (!reportId || status === 'generating') return;
    setFetchError(null);
    await prepare(reportId);
  };

  const handleDownloadPdf = async () => {
    if (!reportId) return;
    setFetchError(null);
    await saveNow(reportId);
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
      // 只到小时级别（2026-09-01：分钟级显得过于精确，审核为 3~24h 随机窗口）
      hour: '2-digit',
    });
  }, [reportInfo?.review_deadline, locale]);

  // 审核状态查询中：避免先闪现报告内容再切换到占位
  if (infoLoading || !infoSettled) {
    return (
      <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
        <Loader2 size={24} className="animate-spin text-bd-subtle" />
      </div>
    );
  }

  // 403：当前账号无权查看该报告，引导从个人空间重新进入
  if (forbidden) {
    return (
      <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-lg w-full text-center space-y-8"
        >
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-bd-overlay-md border-2 border-bd-border">
            <FileText className="w-7 h-7 text-bd-subtle" />
          </div>
          <div className="space-y-3">
            <h1 className="text-3xl font-bold">{t('explore.report.forbiddenTitle')}</h1>
            <p className="text-bd-muted leading-relaxed">{t('explore.report.forbiddenDesc')}</p>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-6 py-3 text-sm font-medium hover:opacity-90 transition-opacity"
          >
            {t('explore.report.gotoMyReports')}
          </Link>
        </motion.div>
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

  // 无激活码（或查询后仍无报告信息）：引导空态，不再渲染 approved 空壳
  if (!reportInfo) {
    return (
      <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-lg w-full text-center space-y-8"
        >
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-bd-overlay-md border-2 border-bd-border">
            <FileText className="w-7 h-7 text-bd-subtle" />
          </div>
          <div className="space-y-3">
            <h1 className="text-3xl font-bold">{t('explore.report.noCodeTitle')}</h1>
            <p className="text-bd-muted leading-relaxed">{t('explore.report.noCodeDesc')}</p>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-6 py-3 text-sm font-medium hover:opacity-90 transition-opacity"
          >
            {t('explore.report.gotoMyReports')}
          </Link>
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

        {/* 报告生成 / 下载按钮区：生成与下载分离，避免 Chrome 拦截异步自动下载 */}
        {activationCode && reportId && (
          <div className="space-y-2">
            {/* 复核进行中提示条：报告不锁定，仍可查看下载旧版 */}
            {recheckInProgress && (
              <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-xs text-amber-600 dark:text-amber-400 leading-relaxed">
                报告复核中，内容可能更新，完成后将通过站内信与邮件通知你。
              </div>
            )}
            {status === 'ready' ? (
              <div className="flex flex-wrap items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  disabled={downloading}
                  className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-6 py-3 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {downloading ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      下载中…
                    </>
                  ) : (
                    <>
                      <Download size={16} />
                      下载 PDF 报告
                    </>
                  )}
                </button>
                {/* 申请复核（用户不能重新生成；复核由管理员人工处理） */}
                <span
                  title={
                    recheckInProgress
                      ? '已有复核申请在处理中，完成后可再次申请'
                      : '报告内容有问题？提交后由管理员人工复核，必要时重新生成；期间你仍可查看当前报告'
                  }
                  className="inline-block"
                >
                  <button
                    type="button"
                    onClick={() => setRecheckOpen(true)}
                    disabled={recheckInProgress}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-bd-border bg-bd-card px-4 py-3 text-xs font-medium text-bd-muted hover:bg-bd-overlay-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-bd-card"
                  >
                    {recheckInProgress ? '复核处理中' : '申请复核'}
                  </button>
                </span>
              </div>
            ) : isGenerating ? (
              <button
                type="button"
                disabled
                className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-6 py-3 text-sm font-medium opacity-60"
              >
                <Loader2 size={16} className="animate-spin" />
                报告生成中…
              </button>
            ) : status === 'error' ? (
              /* 生成失败警示块：用户无主动生成权，仅保留失败重试 + 复核入口 */
              <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-4 space-y-3">
                <p className="text-sm font-medium text-red-500">报告生成失败</p>
                <p className="text-xs text-red-500/80 leading-relaxed">
                  报告生成过程中出现问题，你可以重试，或提交复核申请由管理员处理。
                </p>
                <div className="flex flex-wrap items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={handleGenerate}
                    className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-5 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity"
                  >
                    <FileText size={16} />
                    重新尝试生成
                  </button>
                  <button
                    type="button"
                    onClick={() => setRecheckOpen(true)}
                    disabled={recheckInProgress}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-bd-border bg-bd-card px-4 py-2.5 text-xs font-medium text-bd-muted hover:bg-bd-overlay-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-bd-card"
                  >
                    {recheckInProgress ? '复核处理中' : '申请复核'}
                  </button>
                </div>
              </div>
            ) : statusChecked && status === 'none' ? (
              /* approved 但无可用 markdown 且从未生成：报告异常警示块，仅留复核入口 */
              <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-4 space-y-3">
                <p className="text-sm font-medium text-red-500">报告异常</p>
                <p className="text-xs text-red-500/80 leading-relaxed">
                  报告内容尚未就绪，请提交复核申请，我们会尽快为你处理。
                </p>
                <button
                  type="button"
                  onClick={() => setRecheckOpen(true)}
                  disabled={recheckInProgress}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-5 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {recheckInProgress ? '复核处理中' : '申请复核'}
                </button>
              </div>
            ) : null}
            {isGenerating && (
              <p className="text-xs text-bd-subtle animate-pulse">
                AI 正在为您撰写专属报告，通常需要 1-5 分钟，完成后此处会出现「下载 PDF 报告」按钮
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

        {/* 复核申请弹窗 */}
        {reportId && (
          <ReportRecheckModal
            open={recheckOpen}
            onClose={() => setRecheckOpen(false)}
            reportId={reportId}
            activationCode={activationCode}
            onSubmitted={(res) => {
              // 建单成功后立即把页面切到「复核处理中」态
              if (res.path === 'recheck') {
                setReportInfo((prev) => (prev ? { ...prev, recheck_status: 'pending' } : prev));
              }
            }}
          />
        )}

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

export default function ReportViewPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4 py-12">
          <Loader2 size={24} className="animate-spin text-bd-subtle" />
        </div>
      }
    >
      <ReportViewContent />
    </Suspense>
  );
}
