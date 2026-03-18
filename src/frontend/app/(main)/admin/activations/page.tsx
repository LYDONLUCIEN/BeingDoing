'use client';

import { useEffect, useState } from 'react';
import { fetchAdminActivations, type AdminActivationItem } from '@/lib/api/admin';

type FilterStatus = 'all' | 'active' | 'expired' | 'revoked';

export default function AdminActivationsPage() {
  const [items, setItems] = useState<AdminActivationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<FilterStatus>('all');
  const [mode, setMode] = useState<string>('all');
  const [query, setQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchAdminActivations({
          status: status === 'all' ? undefined : status,
          mode: mode === 'all' ? undefined : mode,
          q: query || undefined,
        });
        if (!cancelled) setItems(res);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || '加载激活码列表失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [status, mode, query]);

  const statusLabel: Record<string, string> = {
    active: 'Active',
    expired: 'Expired',
    revoked: 'Revoked',
  };

  const statusColor: Record<string, string> = {
    active: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    expired: 'bg-amber-100 text-amber-700 border-amber-200',
    revoked: 'bg-rose-100 text-rose-700 border-rose-200',
  };

  const formatTime = (iso: string) => {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
      d.getDate(),
    ).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(
      d.getMinutes(),
    ).padStart(2, '0')}`;
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
          激活码管理
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          查看 simple 模式下所有激活码的状态、模式与最近活跃时间。当前列表为只读，用于运营与调试。
        </p>
      </header>

      {/* 筛选区域 */}
      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-bd-subtle">状态</span>
          <button
            type="button"
            onClick={() => setStatus('all')}
            className={`px-3 py-1.5 rounded-full border text-[11px] ${
              status === 'all'
                ? 'bg-bd-ui-accent text-bd-ui-accent-fg border-transparent'
                : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
            }`}
          >
            全部
          </button>
          {(['active', 'expired', 'revoked'] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatus(s)}
              className={`px-3 py-1.5 rounded-full border text-[11px] ${
                status === s
                  ? 'bg-bd-ui-accent text-bd-ui-accent-fg border-transparent'
                  : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
              }`}
            >
              {statusLabel[s]}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-bd-subtle">模式</span>
          {['all', 'values', 'strengths', 'interests', 'combined'].map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 rounded-full border text-[11px] capitalize ${
                mode === m
                  ? 'bg-bd-ui-accent text-bd-ui-accent-fg border-transparent'
                  : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
              }`}
            >
              {m === 'all' ? '全部' : m}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-xs md:min-w-[220px]">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="按激活码 / session_id 搜索"
            className="w-full rounded-xl border border-bd-border bg-bd-overlay px-3 py-1.5 text-xs outline-none focus:border-neutral-400 focus:ring-1 focus:ring-neutral-300"
          />
        </div>
      </section>

      {/* 列表区域 */}
      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        {loading ? (
          <p className="text-xs text-bd-subtle">加载中…</p>
        ) : error ? (
          <p className="text-xs text-red-500">{error}</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-bd-subtle">暂无激活码记录。</p>
        ) : (
          <div className="overflow-x-auto -mx-2">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                  <th className="px-2 py-2 text-left font-medium">激活码</th>
                  <th className="px-2 py-2 text-left font-medium">Session ID</th>
                  <th className="px-2 py-2 text-left font-medium">模式</th>
                  <th className="px-2 py-2 text-left font-medium">状态</th>
                  <th className="px-2 py-2 text-left font-medium">创建时间</th>
                  <th className="px-2 py-2 text-left font-medium">过期时间</th>
                  <th className="px-2 py-2 text-left font-medium">最后活跃</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.activation_code} className="border-b border-bd-border/60 last:border-0">
                    <td className="px-2 py-2 font-mono text-[11px]" style={{ color: 'var(--bd-fg)' }}>
                      {item.activation_code}
                    </td>
                    <td className="px-2 py-2 font-mono text-[11px] text-bd-subtle max-w-[160px] truncate">
                      {item.session_id}
                    </td>
                    <td className="px-2 py-2 text-[11px] text-bd-muted">{item.mode}</td>
                    <td className="px-2 py-2">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-medium ${
                          statusColor[item.status] || 'bg-bd-overlay-md text-bd-subtle border-bd-border'
                        }`}
                      >
                        {statusLabel[item.status] || item.status}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                      {formatTime(item.created_at)}
                    </td>
                    <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                      {formatTime(item.expires_at)}
                    </td>
                    <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                      {formatTime(item.last_activity_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}


