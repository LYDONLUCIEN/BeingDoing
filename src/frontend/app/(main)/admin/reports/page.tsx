'use client';

import { useEffect, useState } from 'react';
import {
  fetchAdminReportDetail,
  fetchAdminReports,
  syncReportsFromActivations,
  type AdminReportItem,
} from '@/lib/api/admin';

export default function AdminReportsPage() {
  const [items, setItems] = useState<AdminReportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [detail, setDetail] = useState<any>(null);
  const [detailReportId, setDetailReportId] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const loadReports = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminReports({ q: query || undefined });
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
  }, []);

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

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-3 text-xs">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索 report_id / activation_code / user_id"
          className="min-w-[280px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
        />
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

      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">
          {error}
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
                  <th className="px-2 py-2 text-left font-medium">report_id</th>
                  <th className="px-2 py-2 text-left font-medium">activation_code</th>
                  <th className="px-2 py-2 text-left font-medium">user_id</th>
                  <th className="px-2 py-2 text-left font-medium">完成步骤</th>
                  <th className="px-2 py-2 text-left font-medium">状态</th>
                  <th className="px-2 py-2 text-left font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.report_id} className="border-b border-bd-border/60 last:border-0">
                    <td className="px-2 py-2 font-mono text-[11px]">{item.report_id}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.activation_code}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.user_id}</td>
                    <td className="px-2 py-2">{item.completed_steps}/5</td>
                    <td className="px-2 py-2">{item.status}</td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <div className="flex items-center gap-2 whitespace-nowrap flex-nowrap">
                        <button
                          type="button"
                          onClick={() => openDetail(item.report_id)}
                          className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                        >
                          查看
                        </button>
                        <a
                          href={`/api/v1/admin/reports/${encodeURIComponent(item.report_id)}/download`}
                          className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                          target="_blank"
                          rel="noreferrer"
                        >
                          下载JSON
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

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
                  <a
                    href={`/api/v1/admin/reports/${encodeURIComponent(detailReportId)}/download`}
                    className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                    target="_blank"
                    rel="noreferrer"
                  >
                    下载JSON
                  </a>
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

