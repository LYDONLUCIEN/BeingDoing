'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { FileText, ChevronLeft, Download, Loader2 } from 'lucide-react';
import { PHASES, getLastActivationCode } from '@/lib/explore/session';
import LikedContentSection from '@/components/explore/LikedContentSection';
import { useLocale } from '@/hooks/useLocale';
import { getMyReportId, downloadReportPdf } from '@/lib/api/report';

export default function ReportViewPage() {
  const router = useRouter();
  const { t } = useLocale();

  const activationCode = useMemo(() => getLastActivationCode(), []);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const handleDownloadPdf = async () => {
    if (!activationCode || downloading) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const reportId = await getMyReportId(activationCode);
      if (!reportId) {
        setDownloadError('未找到您的报告，请先完成探索流程。');
        return;
      }
      await downloadReportPdf(reportId, { activationCode });
    } catch (e: any) {
      const msg =
        e?.response?.data?.detail ||
        e?.message ||
        '下载失败，请稍后重试。';
      // blob 错误响应需要解析
      if (e?.response?.data instanceof Blob) {
        try {
          const text = await e.response.data.text();
          const parsed = JSON.parse(text);
          setDownloadError(parsed?.detail || '下载失败，请稍后重试。');
        } catch {
          setDownloadError('下载失败，请稍后重试。');
        }
      } else {
        setDownloadError(msg);
      }
    } finally {
      setDownloading(false);
    }
  };

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
              disabled={downloading}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-6 py-3 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {downloading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  正在生成报告...
                </>
              ) : (
                <>
                  <Download size={16} />
                  下载 PDF 报告
                </>
              )}
            </button>
            {downloadError && (
              <p className="text-xs text-red-500">{downloadError}</p>
            )}
          </div>
        )}

        <div className="rounded-xl border border-bd-border bg-bd-card p-6 text-left space-y-4">
          <h3 className="font-semibold text-bd-fg">{t('explore.report.summary')}</h3>
          <p className="text-sm text-bd-muted leading-relaxed">{t('explore.report.summaryDesc')}</p>
        </div>

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
