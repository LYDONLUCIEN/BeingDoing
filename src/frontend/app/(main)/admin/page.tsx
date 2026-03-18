'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  fetchAdminDashboardOverview,
  syncAdminDashboardOverview,
  type AdminDashboardOverview,
  type AdminDashboardOverviewPayload,
} from '@/lib/api/admin';

export default function AdminDashboardPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AdminDashboardOverview | null>(null);
  const [meta, setMeta] = useState<Pick<AdminDashboardOverviewPayload, 'generated_at' | 'source'> | null>(null);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchAdminDashboardOverview();
        if (!cancelled) {
          setData(res?.overview ?? null);
          setMeta({ generated_at: res?.generated_at, source: res?.source });
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载 Dashboard 失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, []);

  const funnelOrder = useMemo(
    () => ['values', 'strengths', 'interests', 'purpose', 'rumination'],
    [],
  );
  const stepLabel: Record<string, string> = {
    values: '价值观',
    strengths: '优势',
    interests: '热忱',
    purpose: '使命',
    rumination: '沉淀',
  };

  const handleManualSync = async () => {
    setSyncing(true);
    setError(null);
    try {
      const res = await syncAdminDashboardOverview();
      setData(res?.overview ?? null);
      setMeta({ generated_at: res?.generated_at, source: res?.source });
    } catch (e: any) {
      setError(e?.message || '手动同步失败');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-bd-subtle mb-2">Admin</p>
        <h1 className="text-2xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          总览 Dashboard
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          默认从 data/static 读取统计缓存。你可以点击手动同步，从 /data 实时重算并覆盖缓存。
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
          <button
            type="button"
            onClick={handleManualSync}
            disabled={syncing}
            className="px-3 py-1.5 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg disabled:opacity-60"
          >
            {syncing ? '同步中...' : '手动同步（从 /data 重算）'}
          </button>
          <span className="text-bd-subtle">
            上次生成：{meta?.generated_at ? new Date(meta.generated_at).toLocaleString() : '—'}
          </span>
        </div>
      </header>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 text-xs px-4 py-3">
          {error}
        </div>
      )}

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">今日新激活码</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
            {loading ? '...' : data?.today_new_activations ?? 0}
          </p>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">用户总数</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
            {loading ? '...' : data?.user_count ?? 0}
          </p>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">已生成报告数</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
            {loading ? '...' : data?.report_count ?? 0}
          </p>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">累计访问次数</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
            {loading ? '...' : data?.visit_count ?? 0}
          </p>
        </div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
          <h2 className="text-sm font-medium mb-2" style={{ color: 'var(--bd-fg)' }}>
            五步骤漏斗（报告维度）
          </h2>
          <div className="space-y-2">
            {funnelOrder.map((k) => {
              const item = data?.funnel?.find((x) => x.step_id === k);
              const count = item?.count ?? 0;
              const pct = item?.pct ?? 0;
              return (
                <div key={k} className="text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-bd-muted">{stepLabel[k]}</span>
                    <span className="text-bd-fg">{count} ({pct}%)</span>
                  </div>
                  <div className="h-2 rounded-full bg-bd-overlay-md overflow-hidden">
                    <div
                      className="h-2 rounded-full bg-bd-ui-accent"
                      style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
          <h2 className="text-sm font-medium mb-2" style={{ color: 'var(--bd-fg)' }}>
            Token 统计（累计 + 分步骤）
          </h2>
          <div className="text-xs text-bd-muted space-y-2">
            <p>
              累计输入：<span className="text-bd-fg font-medium">{data?.token_totals?.input_tokens ?? 0}</span>
            </p>
            <p>
              累计输出：<span className="text-bd-fg font-medium">{data?.token_totals?.output_tokens ?? 0}</span>
            </p>
            <p>
              总 Token：<span className="text-bd-fg font-semibold">{data?.token_totals?.total_tokens ?? 0}</span>
            </p>
            <div className="pt-2 border-t border-bd-border/60 space-y-1">
              {funnelOrder.map((k) => {
                const s = data?.token_by_step?.[k];
                return (
                  <div key={k} className="text-[11px]">
                    <p>
                      {stepLabel[k]}：总 <span className="text-bd-fg">{s?.total_tokens ?? 0}</span>
                    </p>
                    <p className="text-bd-subtle">
                      输入 {s?.input_tokens ?? 0} / 输出 {s?.output_tokens ?? 0}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

