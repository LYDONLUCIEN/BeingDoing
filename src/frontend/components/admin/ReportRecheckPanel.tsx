'use client';

/**
 * Admin 报告复核面板（2026-08-18，tasks/report-review-plan.md）
 *
 * 原则：admin 不能随意重新生成——本面板仅当报告存在未关闭复核单时可打开；
 * 「重新生成」生成到 staging（用户仍看旧版），admin 下载预览满意后
 * 「确认发布」才同步给用户（站内信+邮件通知）；复核单关闭后入口消失。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { X, Loader2, Download, RefreshCw } from 'lucide-react';
import {
  downloadAdminRecheckStagingPdf,
  fetchAdminReportRecheck,
  publishAdminReportRecheck,
  regenerateAdminReportRecheck,
  rejectAdminReportRecheck,
  type AdminRecheckInfo,
} from '@/lib/api/admin';

interface ReportRecheckPanelProps {
  reportId: string;
  onClose: () => void;
  /** 复核单关闭（发布/驳回）后通知父组件刷新列表 */
  onChanged: () => void;
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  regenerating: '重新生成中',
  pending_confirm: '新稿待确认',
  done: '已发布',
  rejected: '已驳回',
};

const POLL_INTERVAL_MS = 3000;

export default function ReportRecheckPanel({ reportId, onClose, onChanged }: ReportRecheckPanelProps) {
  const [info, setInfo] = useState<AdminRecheckInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null); // regenerate/publish/reject/download
  const [rejectReason, setRejectReason] = useState('');
  const [showReject, setShowReject] = useState(false);
  const pollingRef = useRef(false);

  const load = useCallback(async () => {
    try {
      const res = await fetchAdminReportRecheck(reportId);
      setInfo(res);
      return res;
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '加载复核信息失败');
      return null;
    }
  }, [reportId]);

  useEffect(() => {
    void load();
  }, [load]);

  // staging 生成中：轮询直到 done/error
  useEffect(() => {
    if (info?.staging_task?.status !== 'pending' || pollingRef.current) return;
    pollingRef.current = true;
    const timer = setInterval(async () => {
      const res = await load();
      if (res?.staging_task?.status !== 'pending') {
        clearInterval(timer);
        pollingRef.current = false;
      }
    }, POLL_INTERVAL_MS);
    return () => {
      clearInterval(timer);
      pollingRef.current = false;
    };
  }, [info?.staging_task?.status, load]);

  const current = info?.current ?? null;
  const generating = info?.staging_task?.status === 'pending' || current?.status === 'regenerating';

  const handleRegenerate = async () => {
    setWorking('regenerate');
    setError(null);
    try {
      await regenerateAdminReportRecheck(reportId);
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '触发失败');
    } finally {
      setWorking(null);
    }
  };

  const handleDownloadStaging = async () => {
    setWorking('download');
    setError(null);
    try {
      await downloadAdminRecheckStagingPdf(reportId);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '下载新稿失败（可能尚未生成）');
    } finally {
      setWorking(null);
    }
  };

  const handlePublish = async () => {
    if (
      !window.confirm(
        '确认发布新稿吗？\n发布后用户将同步看到新报告（站内信+邮件通知），旧版自动备份但页面不可恢复。',
      )
    ) {
      return;
    }
    setWorking('publish');
    setError(null);
    try {
      await publishAdminReportRecheck(reportId);
      onChanged();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '发布失败');
      setWorking(null);
    }
  };

  const handleReject = async () => {
    const reason = rejectReason.trim();
    if (!reason) {
      setError('驳回必须填写理由（将通过站内信告知用户）');
      return;
    }
    setWorking('reject');
    setError(null);
    try {
      await rejectAdminReportRecheck(reportId, reason);
      onChanged();
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '驳回失败');
      setWorking(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[120] bg-black/40 backdrop-blur-[1px] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl bg-bd-card border border-bd-border shadow-2xl p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium" style={{ color: 'var(--bd-fg)' }}>
            报告复核 <span className="font-mono text-xs text-bd-subtle">({reportId})</span>
          </h2>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => void load()}
              className="p-1.5 rounded-lg text-bd-subtle hover:bg-bd-overlay-md transition-colors"
              aria-label="刷新"
            >
              <RefreshCw size={14} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-bd-subtle hover:bg-bd-overlay-md transition-colors"
              aria-label="关闭"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        {!info ? (
          <p className="text-xs text-bd-subtle flex items-center gap-2">
            <Loader2 size={14} className="animate-spin" /> 加载中...
          </p>
        ) : !current ? (
          <p className="text-xs text-bd-subtle">该报告没有进行中的复核（历史共 {info.total_count} 次）。</p>
        ) : (
          <>
            <div className="rounded-xl border border-bd-border bg-bd-overlay p-4 space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-bd-subtle">状态：</span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700 font-medium">
                  {STATUS_LABEL[current.status] ?? current.status}
                </span>
                <span className="text-bd-subtle ml-auto">历史共 {info.total_count} 次</span>
              </div>
              <p>
                <span className="text-bd-subtle">申请时间：</span>
                {new Date(current.requested_at).toLocaleString('zh-CN')}
              </p>
              <p>
                <span className="text-bd-subtle">用户描述：</span>
                {current.description || '（用户未填写）'}
              </p>
              {current.regen_error && (
                <p className="text-red-600">上次生成失败：{current.regen_error}</p>
              )}
            </div>

            {generating && (
              <p className="text-xs text-amber-600 animate-pulse flex items-center gap-2">
                <Loader2 size={12} className="animate-spin" />
                AI 正在重新生成新稿（用户端仍看到旧版报告）…
              </p>
            )}

            {error && <p className="text-xs text-red-600">{error}</p>}

            <div className="flex flex-wrap items-center gap-2 text-xs">
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={generating || working !== null}
                className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg disabled:opacity-60"
              >
                {working === 'regenerate' ? '触发中...' : info.has_staging ? '再次重新生成' : '重新生成'}
              </button>
              <button
                type="button"
                onClick={handleDownloadStaging}
                disabled={!info.has_staging || generating || working !== null}
                className="inline-flex items-center gap-1 px-3 py-2 rounded-lg border border-bd-border text-bd-fg hover:bg-bd-overlay-md disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Download size={12} />
                {working === 'download' ? '下载中...' : '下载新稿预览'}
              </button>
              <button
                type="button"
                onClick={handlePublish}
                disabled={current.status !== 'pending_confirm' || generating || working !== null}
                className="px-3 py-2 rounded-lg border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {working === 'publish' ? '发布中...' : '确认发布'}
              </button>
              <button
                type="button"
                onClick={() => setShowReject((v) => !v)}
                disabled={generating || working !== null}
                className="px-3 py-2 rounded-lg border border-red-300 bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-60"
              >
                驳回
              </button>
            </div>

            {showReject && (
              <div className="space-y-2">
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  rows={3}
                  maxLength={2000}
                  placeholder="驳回理由（必填，将通过站内信告知用户）"
                  className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs text-bd-fg placeholder:text-bd-ghost focus:outline-none focus:border-red-400"
                />
                <button
                  type="button"
                  onClick={handleReject}
                  disabled={working !== null}
                  className="px-3 py-2 rounded-lg bg-red-600 text-white text-xs hover:bg-red-700 disabled:opacity-60"
                >
                  {working === 'reject' ? '提交中...' : '确认驳回'}
                </button>
              </div>
            )}

            <p className="text-[11px] text-bd-subtle leading-relaxed">
              提示：重新生成可反复进行（覆盖新稿），下载预览满意后再「确认发布」；
              发布前用户始终看到旧版报告。
            </p>
          </>
        )}
      </div>
    </div>
  );
}
