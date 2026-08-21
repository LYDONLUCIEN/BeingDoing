'use client';

import { useEffect, useState } from 'react';
import {
  downloadReportJson,
  exportReportsBatch,
  fetchAdminReportDetail,
  fetchAdminReports,
  syncReportsFromActivations,
  getReportConversationStats,
  approveAdminReport,
  renderAdminReportPdf,
  fetchGeneratingReports,
  fetchReportRenderConfig,
  updateReportRenderConfig,
  type AdminReportItem,
  type AdminReportReviewStatus,
  type ConversationStatsResult,
} from '@/lib/api/admin';
import { useReportPdfDownload } from '@/hooks/useReportPdfDownload';
import ReportRecheckPanel from '@/components/admin/ReportRecheckPanel';

export default function AdminReportsPage() {
  const [items, setItems] = useState<AdminReportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [detail, setDetail] = useState<any>(null);
  const [detailReportId, setDetailReportId] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [exportFormat, setExportFormat] = useState<'md' | 'txt'>('md');
  const [exporting, setExporting] = useState(false);
  const [statsResult, setStatsResult] = useState<ConversationStatsResult | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsReportId, setStatsReportId] = useState<string | null>(null);

  // 审核状态筛选 + 人工确认审核
  const [reviewFilter, setReviewFilter] = useState<'' | AdminReportReviewStatus>('');
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  // 复核面板（仅当报告存在未关闭复核单时可打开）
  const [recheckReportId, setRecheckReportId] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  // PDF 异步下载（admin 不传 activationCode）；check/prepare/saveNow 不隐式触发生成（先查状态）
  const {
    status: pdfStatus,
    error: pdfError,
    activeReportId,
    check,
    prepare,
    saveNow,
  } = useReportPdfDownload();

  // 渲染引擎配置（ADR-0019，全局即时生效）
  const [renderEngine, setRenderEngine] = useState<string>('weasyprint');
  const [engineSaving, setEngineSaving] = useState(false);
  useEffect(() => {
    fetchReportRenderConfig()
      .then((cfg) => setRenderEngine(cfg.engine))
      .catch(() => { /* 读取失败用默认 */ });
  }, []);
  const handleEngineChange = async (engine: string) => {
    if (engine === renderEngine || engineSaving) return;
    setEngineSaving(true);
    try {
      const saved = await updateReportRenderConfig(engine);
      setRenderEngine(saved);
      setToast({
        type: 'success',
        msg: saved === 'xunlu' ? '已切换为设计版渲染器（版式精，PDF 较大）' : '已切换为简洁版渲染器（PDF 体积小）',
      });
    } catch (e: any) {
      setToast({ type: 'error', msg: e?.message || '切换渲染引擎失败' });
    } finally {
      setEngineSaving(false);
    }
  };

  // 生成中状态（真源在后端单轨锁）：定时拉取，刷新页面也能恢复按钮态
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());
  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const ids = await fetchGeneratingReports();
        if (!stopped) setGeneratingIds(new Set(ids));
      } catch { /* 查询失败保持现状 */ }
    };
    void tick();
    const timer = setInterval(tick, 3000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);

  const loadReports = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminReports({
        q: query || undefined,
        review_status: reviewFilter || undefined,
      });
      setItems(res.items || []);
    } catch (e: any) {
      setError(e?.message || '加载报告失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewFilter]);

  const openDetail = async (reportId: string) => {
    setDetailOpen(true);
    setDetailReportId(reportId);
    try {
      const res = await fetchAdminReportDetail(reportId);
      setDetail(res);
    } catch (e: any) {
      setError(e?.message || '加载报告详情失败');
    }
  };

  const handleSyncReports = async () => {
    setSyncing(true);
    try {
      await syncReportsFromActivations();
      await loadReports();
    } catch (e: any) {
      setError(e?.message || '同步报告失败');
    } finally {
      setSyncing(false);
    }
  };

  const toggleSelect = (reportId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(reportId)) {
        next.delete(reportId);
      } else {
        next.add(reportId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (prev.size === items.length) {
        return new Set();
      }
      return new Set(items.map((i) => i.report_id));
    });
  };

  const handleBatchExport = async () => {
    if (selectedIds.size === 0) {
      setError('请先勾选要导出的报告');
      return;
    }
    if (selectedIds.size > 50) {
      setError('单次最多导出 50 个，请分批操作');
      return;
    }
    setExporting(true);
    setError(null);
    try {
      await exportReportsBatch(Array.from(selectedIds), exportFormat);
    } catch (e: any) {
      setError(e?.message || '批量导出失败');
    } finally {
      setExporting(false);
    }
  };

  const openStats = async (reportId: string) => {
    setStatsReportId(reportId);
    setStatsLoading(true);
    setStatsResult(null);
    try {
      const res = await getReportConversationStats(reportId);
      setStatsResult(res);
    } catch (e: any) {
      setError(e?.message || '加载统计失败');
    } finally {
      setStatsLoading(false);
    }
  };

  const closeStats = () => {
    setStatsReportId(null);
    setStatsResult(null);
  };

  // 人工确认审核：二次确认 → approve API → toast + 刷新
  const handleApprove = async (reportId: string) => {
    if (
      !window.confirm(
        `确认审核通过报告 ${reportId} 吗？\n通过后用户即可查看并下载报告内容。`,
      )
    ) {
      return;
    }
    setApprovingId(reportId);
    try {
      await approveAdminReport(reportId);
      setToast({ type: 'success', msg: '已确认审核，报告批复通过' });
      await loadReports();
    } catch (e: any) {
      setToast({ type: 'error', msg: e?.message || '审核操作失败' });
    } finally {
      setApprovingId(null);
    }
  };

  // 审核状态 badge：not_started=灰「未开始」/ pending_review=黄「待审核」/ approved+manual=绿「人工已审」/ approved+auto=青「自动批复」
  const renderReviewBadge = (item: AdminReportItem) => {
    const base =
      'inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-medium whitespace-nowrap';
    const reviewStatus = item.review_status ?? 'approved'; // 存量报告视为 approved
    if (reviewStatus === 'not_started') {
      return <span className={`${base} bg-gray-100 text-gray-500 border-gray-200`}>未开始</span>;
    }
    if (reviewStatus === 'pending_review') {
      return (
        <span className={`${base} bg-amber-100 text-amber-700 border-amber-200`}>待审核</span>
      );
    }
    if (item.review_type === 'auto') {
      return <span className={`${base} bg-teal-100 text-teal-700 border-teal-200`}>自动批复</span>;
    }
    if (item.review_type === 'manual') {
      return (
        <span className={`${base} bg-emerald-100 text-emerald-700 border-emerald-200`}>
          人工已审
        </span>
      );
    }
    return (
      <span className={`${base} bg-emerald-100 text-emerald-700 border-emerald-200`}>已审核</span>
    );
  };

  // 下载单个 report 的完整明细 zip（带认证 token，走 axios 拉取）
  const handleDownloadJson = async (reportId: string) => {
    setError(null);
    try {
      await downloadReportJson(reportId);
    } catch (e: any) {
      setError(e?.message || '下载失败');
    }
  };

  // 下载报告 PDF（纯渲染下载：先查状态，md 不存在不隐式触发 LLM 生成）
  const handleDownloadPdf = async (reportId: string) => {
    setError(null);
    const s = await check(reportId);
    if (s === 'none') {
      setError('报告尚未生成 markdown，admin 下载不触发 LLM 生成；请先由用户侧或复核流程生成');
      return;
    }
    if (s === 'generating') {
      // 后台正在生成：接管轮询直到就绪
      await prepare(reportId);
    }
    await saveNow(reportId);
  };

  // 重渲染报告 PDF（xunlu 新版式渲染器；不重新生成内容，仅按现有 markdown 出新版式，ADR-0019）
  const [rerenderingId, setRerenderingId] = useState<string | null>(null);
  const handleRenderPdf = async (reportId: string) => {
    setError(null);
    setRerenderingId(reportId);
    try {
      await renderAdminReportPdf(reportId);
    } catch (e: any) {
      // blob 响应的错误体需要额外解析
      let msg = e?.message || '重渲染失败';
      const data = e?.response?.data;
      if (data instanceof Blob) {
        try {
          const parsed = JSON.parse(await data.text());
          if (parsed?.detail) msg = parsed.detail;
        } catch { /* 忽略解析失败 */ }
      }
      setError(msg);
    } finally {
      setRerenderingId(null);
    }
  };

  // 注意：admin 不再提供「重新生成」按钮（2026-08-16 起，只能下载用户已生成的报告）；
  // 后端 force 能力保留，仅供运维通过脚本/Swagger 手动触发。
  // 2026-08-18 起新增复核体系：仅当报告有未关闭复核单时出现「复核」入口，
  // 重新生成（staging）/ 确认发布 / 驳回均在复核面板内完成。

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          报告概览
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          查看所有 report_id，支持按关键字搜索并查看五步骤绑定详情。
        </p>
      </header>

      {/* PDF 渲染引擎配置（ADR-0019，全局即时生效）：简洁版体积小 / 设计版版式精 */}
      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-4 text-xs">
        <span className="font-medium" style={{ color: 'var(--bd-fg)' }}>
          PDF 渲染引擎
        </span>
        <label className="inline-flex items-center gap-1.5 cursor-pointer">
          <input
            type="radio"
            name="render-engine"
            checked={renderEngine === 'weasyprint'}
            onChange={() => handleEngineChange('weasyprint')}
            disabled={engineSaving}
          />
          简洁版（WeasyPrint，体积小约 1MB）
        </label>
        <label className="inline-flex items-center gap-1.5 cursor-pointer">
          <input
            type="radio"
            name="render-engine"
            checked={renderEngine === 'xunlu'}
            onChange={() => handleEngineChange('xunlu')}
            disabled={engineSaving}
          />
          设计版（xunlu，版式精，体积大约 9MB）
        </label>
        {engineSaving && <span style={{ color: 'var(--bd-fg-muted)' }}>保存中...</span>}
        <span style={{ color: 'var(--bd-fg-muted)' }}>
          全局即时生效，无需重启；作用于用户下载与 admin 下载
        </span>
      </section>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-3 text-xs">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索 report_id / activation_code / user_id"
          className="min-w-[280px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
        />
        <select
          value={reviewFilter}
          onChange={(e) => setReviewFilter(e.target.value as '' | AdminReportReviewStatus)}
          className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
          aria-label="审核状态筛选"
        >
          <option value="">审核状态：全部</option>
          <option value="not_started">未开始</option>
          <option value="pending_review">待审核</option>
          <option value="approved">已审核</option>
        </select>
        <button
          type="button"
          onClick={loadReports}
          className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg"
        >
          搜索
        </button>
        <button
          type="button"
          onClick={handleSyncReports}
          disabled={syncing}
          className="px-3 py-2 rounded-lg border border-bd-border text-bd-fg disabled:opacity-60"
        >
          {syncing ? '同步中...' : '从激活码补齐报告'}
        </button>
      </section>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-3 text-xs">
        <span className="text-bd-subtle">
          已选 {selectedIds.size} / {items.length}
        </span>
        <select
          value={exportFormat}
          onChange={(e) => setExportFormat(e.target.value as 'md' | 'txt')}
          className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
        >
          <option value="md">Markdown (.md)</option>
          <option value="txt">纯文本 (.txt)</option>
        </select>
        <button
          type="button"
          onClick={handleBatchExport}
          disabled={exporting || selectedIds.size === 0}
          className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg disabled:opacity-60"
        >
          {exporting ? '导出中...' : '批量导出 (zip)'}
        </button>
      </section>

      {(error || pdfError) && (
        <section className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">
          {error || pdfError}
        </section>
      )}

      {pdfStatus === 'generating' && activeReportId && (
        <section className="rounded-xl border border-amber-200 bg-amber-50 text-amber-700 px-4 py-3 text-xs animate-pulse">
          报告 {activeReportId.slice(0, 8)}... 正在生成中，请勿关闭页面（通常需要 10-30 秒）
        </section>
      )}

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        {loading ? (
          <p className="text-xs text-bd-subtle">加载中...</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-bd-subtle">暂无报告。</p>
        ) : (
          <div className="overflow-x-auto -mx-2 pb-1">
            <table className="min-w-[1100px] w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                  <th className="px-2 py-2 text-left font-medium w-8">
                    <input
                      type="checkbox"
                      checked={items.length > 0 && selectedIds.size === items.length}
                      onChange={toggleSelectAll}
                      aria-label="全选"
                    />
                  </th>
                  <th className="px-2 py-2 text-left font-medium">report_id</th>
                  <th className="px-2 py-2 text-left font-medium">activation_code</th>
                  <th className="px-2 py-2 text-left font-medium">user_id</th>
                  <th className="px-2 py-2 text-left font-medium">完成步骤</th>
                  <th className="px-2 py-2 text-left font-medium">状态</th>
                  <th className="px-2 py-2 text-left font-medium">审核状态</th>
                  <th className="px-2 py-2 text-left font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.report_id} className="border-b border-bd-border/60 last:border-0">
                    <td className="px-2 py-2 w-8">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.report_id)}
                        onChange={() => toggleSelect(item.report_id)}
                        aria-label={`选择 ${item.report_id}`}
                      />
                    </td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.report_id}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.activation_code}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.user_id}</td>
                    <td className="px-2 py-2">{item.completed_steps}/5</td>
                    <td className="px-2 py-2">{item.status}</td>
                    <td className="px-2 py-2">
                      <div className="flex flex-col gap-1 items-start">
                        {renderReviewBadge(item)}
                        {item.recheck_status && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full border border-amber-300 bg-amber-50 text-amber-700 text-[10px] font-medium whitespace-nowrap">
                            复核中
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <div className="flex items-center gap-2 whitespace-nowrap flex-nowrap">
                        {item.review_status === 'pending_review' && (
                          <button
                            type="button"
                            onClick={() => handleApprove(item.report_id)}
                            disabled={approvingId === item.report_id}
                            className="px-2 py-1 rounded border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 whitespace-nowrap disabled:opacity-60"
                          >
                            {approvingId === item.report_id ? '审核中...' : '确认审核'}
                          </button>
                        )}
                        {item.recheck_status && (
                          <button
                            type="button"
                            onClick={() => setRecheckReportId(item.report_id)}
                            className="px-2 py-1 rounded border border-amber-300 bg-amber-50 text-amber-700 hover:bg-amber-100 whitespace-nowrap"
                          >
                            复核
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => openDetail(item.report_id)}
                          className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                        >
                          查看
                        </button>
                        <button
                          type="button"
                          onClick={() => openStats(item.report_id)}
                          className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                        >
                          统计
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDownloadJson(item.report_id)}
                          className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                        >
                          下载完整数据
                        </button>
                        {/* disabled 按钮不触发 hover，tooltip 需包一层 span */}
                        <span
                          title={
                            item.report_unlocked === false
                              ? '用户尚未完成全部探索阶段，暂不可下载'
                              : undefined
                          }
                          className="inline-block"
                        >
                          <button
                            type="button"
                            onClick={() => handleDownloadPdf(item.report_id)}
                            disabled={
                              item.report_unlocked === false ||
                              generatingIds.has(item.report_id) ||
                              (pdfStatus === 'generating' && activeReportId === item.report_id)
                            }
                            className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                          >
                            {generatingIds.has(item.report_id) ||
                            (pdfStatus === 'generating' && activeReportId === item.report_id)
                              ? '生成中...'
                              : '下载PDF'}
                          </button>
                        </span>
                        {/* 重渲染：用 xunlu 新版式渲染器出 PDF（不重新生成内容）；无 markdown 缓存时后端 409 */}
                        <span
                          title="用 xunlu 新版式渲染器重新渲染现有报告（内容不变，仅版式更新）"
                          className="inline-block"
                        >
                          <button
                            type="button"
                            onClick={() => handleRenderPdf(item.report_id)}
                            disabled={
                              item.report_unlocked === false ||
                              rerenderingId === item.report_id
                            }
                            className="px-2 py-1 rounded border border-sky-300 bg-sky-50 text-sky-700 hover:bg-sky-100 whitespace-nowrap disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:bg-sky-50"
                          >
                            {rerenderingId === item.report_id ? '渲染中...' : '重渲染PDF'}
                          </button>
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Toast */}
      {toast && (
        <div
          role="alert"
          className={`fixed bottom-8 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium shadow-lg z-[130] ${
            toast.type === 'success'
              ? 'bg-emerald-600/95 text-white'
              : 'bg-red-600/95 text-white'
          }`}
          style={{ animation: 'toast-in 0.25s ease-out' }}
        >
          {toast.msg}
        </div>
      )}

      {/* 复核面板 */}
      {recheckReportId && (
        <ReportRecheckPanel
          reportId={recheckReportId}
          onClose={() => setRecheckReportId(null)}
          onChanged={() => void loadReports()}
        />
      )}

      {(statsReportId !== null || statsLoading) && (
        <div
          className="fixed inset-0 z-[120] bg-black/40 backdrop-blur-[1px] flex items-center justify-center p-4"
          onClick={closeStats}
        >
          <div
            className="w-full max-w-lg rounded-2xl bg-bd-card border border-bd-border shadow-2xl p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium" style={{ color: 'var(--bd-fg)' }}>
                对话统计 {statsReportId ? `(${statsReportId.slice(0, 8)}...)` : ''}
              </h2>
              <button
                type="button"
                onClick={closeStats}
                className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md"
              >
                关闭
              </button>
            </div>

            {statsLoading ? (
              <p className="text-xs text-bd-subtle">加载中...</p>
            ) : statsResult ? (
              <>
                <div className="rounded-xl border border-bd-border bg-bd-overlay p-4 space-y-2">
                  <div className="flex items-baseline gap-4">
                    <div>
                      <span className="text-[11px] text-bd-subtle">总轮数</span>
                      <div className="text-xl font-semibold text-bd-fg">
                        {statsResult.total_turns}
                      </div>
                    </div>
                    <div>
                      <span className="text-[11px] text-bd-subtle">平均每轮</span>
                      <div className="text-xl font-semibold text-bd-fg">
                        {statsResult.avg_minutes.toFixed(1)}
                        <span className="text-xs ml-1">分</span>
                      </div>
                    </div>
                    <div>
                      <span className="text-[11px] text-bd-subtle">总时长</span>
                      <div className="text-xl font-semibold text-bd-fg">
                        {statsResult.total_minutes.toFixed(0)}
                        <span className="text-xs ml-1">分</span>
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-bd-fg">{statsResult.reminder_text}</p>
                  {(statsResult.skipped_no_ts > 0 || statsResult.skipped_long_turns > 0) && (
                    <p className="text-[11px] text-bd-subtle">
                      {statsResult.skipped_no_ts > 0 && `跳过缺时间戳 ${statsResult.skipped_no_ts} 轮；`}
                      {statsResult.skipped_long_turns > 0 &&
                        `跳过异常时长(>2h) ${statsResult.skipped_long_turns} 轮`}
                    </p>
                  )}
                </div>

                {statsResult.per_phase.length > 0 && (
                  <div>
                    <h3 className="text-xs font-medium text-bd-subtle mb-2">各阶段明细</h3>
                    <div className="space-y-1">
                      {statsResult.per_phase.map((ph) => (
                        <div
                          key={ph.phase_id}
                          className="flex items-center justify-between rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
                        >
                          <span className="text-bd-fg">{ph.phase_name}</span>
                          <span className="text-bd-subtle">
                            {ph.turns}轮 / 均{ph.avg_minutes.toFixed(1)}分 / 总{ph.total_minutes.toFixed(0)}分
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <p className="text-xs text-bd-subtle">暂无统计数据</p>
            )}
          </div>
        </div>
      )}

      {detailOpen && (
        <div
          className="fixed inset-0 z-[120] bg-black/40 backdrop-blur-[1px] flex items-center justify-center p-4"
          onClick={() => setDetailOpen(false)}
        >
          <div
            className="w-full max-w-5xl max-h-[85vh] rounded-2xl bg-bd-card border border-bd-border shadow-2xl flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-3 border-b border-bd-border flex items-center justify-between">
              <h2 className="text-sm font-medium" style={{ color: 'var(--bd-fg)' }}>
                报告详情 {detailReportId ? `(${detailReportId})` : ''}
              </h2>
              <div className="flex items-center gap-2">
                {detailReportId && (
                  <button
                    type="button"
                    onClick={() => handleDownloadJson(detailReportId)}
                    className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                  >
                    下载完整数据
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setDetailOpen(false)}
                  className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                >
                  关闭
                </button>
              </div>
            </div>
            <div className="p-5 overflow-y-auto overflow-x-auto">
              {detail ? (
                <pre className="text-[11px] whitespace-pre bg-bd-overlay-md rounded-xl p-3 border border-bd-border min-w-[900px]">
                  {JSON.stringify(detail, null, 2)}
                </pre>
              ) : (
                <p className="text-xs text-bd-subtle">请选择一份报告查看详情。</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

