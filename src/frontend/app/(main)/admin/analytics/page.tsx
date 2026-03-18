'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  fetchAdminAnalyticsDashboard,
  fetchAdminChatRecords,
  type AdminAnalyticsDashboard,
} from '@/lib/api/admin';

export default function AdminAnalyticsPage() {
  const [dashboard, setDashboard] = useState<AdminAnalyticsDashboard | null>(null);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [dimension, setDimension] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [records, setRecords] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const loadDashboard = async () => {
    setLoadingDashboard(true);
    setError(null);
    try {
      const res = await fetchAdminAnalyticsDashboard();
      setDashboard(res);
    } catch (e: any) {
      setError(e?.message || '加载埋点概览失败');
    } finally {
      setLoadingDashboard(false);
    }
  };

  const loadRecords = async (nextPage = page) => {
    setLoadingRecords(true);
    setError(null);
    try {
      const res = await fetchAdminChatRecords({
        page: nextPage,
        page_size: pageSize,
        dimension: dimension || undefined,
        session_id: sessionId || undefined,
      });
      setRecords(res.records || []);
      setTotal(Number(res.total || 0));
      setPage(Number(res.page || nextPage));
    } catch (e: any) {
      setError(e?.message || '加载埋点明细失败');
    } finally {
      setLoadingRecords(false);
    }
  };

  useEffect(() => {
    loadDashboard();
    loadRecords(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rowTokenSummary = useMemo(() => {
    return (records || []).reduce(
      (acc, r) => {
        acc.input += Number(r?.llm_input_tokens || 0);
        acc.output += Number(r?.llm_output_tokens || 0);
        return acc;
      },
      { input: 0, output: 0 },
    );
  }, [records]);

  const maxPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          埋点与 Token 统计
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          统计来源于后端埋点表（analytics_chat_turn）与历史日志聚合。Token 以 API 返回 usage 落库数据为主。
        </p>
      </header>

      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">
          {error}
        </section>
      )}

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">埋点概览</h2>
          <button
            type="button"
            onClick={loadDashboard}
            disabled={loadingDashboard}
            className="px-3 py-1.5 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md disabled:opacity-60"
          >
            {loadingDashboard ? '刷新中...' : '刷新概览'}
          </button>
        </div>
        {dashboard ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">总输入 Token</p>
              <p className="text-base font-semibold">{dashboard.llm_input_tokens}</p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">总输出 Token</p>
              <p className="text-base font-semibold">{dashboard.llm_output_tokens}</p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">报告数</p>
              <p className="text-base font-semibold">{dashboard.report_count}</p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">点赞数</p>
              <p className="text-base font-semibold">{dashboard.like_count}</p>
            </div>
          </div>
        ) : (
          <p className="text-xs text-bd-subtle">暂无埋点概览。</p>
        )}
      </section>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <div className="space-y-1">
            <p className="text-[11px] text-bd-subtle">维度</p>
            <input
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
              placeholder="values / strengths / interests / purpose / rumination"
              className="w-[320px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
          </div>
          <div className="space-y-1">
            <p className="text-[11px] text-bd-subtle">session_id / activation_code</p>
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="输入 session_id 或激活码"
              className="w-[260px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
          </div>
          <button
            type="button"
            onClick={() => loadRecords(1)}
            className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg text-xs"
          >
            查询明细
          </button>
        </div>

        <div className="mb-3 text-[11px] text-bd-subtle">
          本页汇总：输入 {rowTokenSummary.input} / 输出 {rowTokenSummary.output} / 总计{' '}
          {rowTokenSummary.input + rowTokenSummary.output}（当前页）
        </div>

        {loadingRecords ? (
          <p className="text-xs text-bd-subtle">加载明细中...</p>
        ) : records.length === 0 ? (
          <p className="text-xs text-bd-subtle">暂无匹配埋点记录。</p>
        ) : (
          <div className="overflow-x-auto -mx-2 pb-1">
            <table className="min-w-[1280px] w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">id</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">dimension</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">session_id</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">activation_code</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">user_id</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">输入Token</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">输出Token</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">总Token</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">用户输入字数</th>
                  <th className="px-2 py-2 text-left font-medium whitespace-nowrap">created_at</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r: any) => {
                  const inTokens = Number(r?.llm_input_tokens || 0);
                  const outTokens = Number(r?.llm_output_tokens || 0);
                  return (
                    <tr key={String(r?.id)} className="border-b border-bd-border/60 last:border-0">
                      <td className="px-2 py-2 font-mono text-[11px] whitespace-nowrap">{r?.id}</td>
                      <td className="px-2 py-2 whitespace-nowrap">{r?.dimension}</td>
                      <td className="px-2 py-2 font-mono text-[11px] whitespace-nowrap">{r?.session_id}</td>
                      <td className="px-2 py-2 font-mono text-[11px] whitespace-nowrap">{r?.activation_code || '—'}</td>
                      <td className="px-2 py-2 font-mono text-[11px] whitespace-nowrap">{r?.user_id || '—'}</td>
                      <td className="px-2 py-2 whitespace-nowrap">{inTokens}</td>
                      <td className="px-2 py-2 whitespace-nowrap">{outTokens}</td>
                      <td className="px-2 py-2 whitespace-nowrap">{inTokens + outTokens}</td>
                      <td className="px-2 py-2 whitespace-nowrap">{r?.user_input_chars ?? 0}</td>
                      <td className="px-2 py-2 whitespace-nowrap">{r?.created_at || ''}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 flex items-center justify-between text-xs">
          <p className="text-bd-subtle">
            第 {page}/{maxPage} 页 · 共 {total} 条
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => loadRecords(page - 1)}
              className="px-3 py-1.5 rounded-lg border border-bd-border disabled:opacity-50"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={page >= maxPage}
              onClick={() => loadRecords(page + 1)}
              className="px-3 py-1.5 rounded-lg border border-bd-border disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

