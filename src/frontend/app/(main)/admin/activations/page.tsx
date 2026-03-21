'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  type ActivationSyncSource,
  batchCreateActivations,
  batchDeleteActivations,
  batchUpdateActivationStatus,
  fetchActivationRecycleBin,
  fetchAdminActivations,
  restoreActivationsFromRecycle,
  permanentDeleteFromRecycleBin,
  syncActivations,
  type AdminActivationItem,
  type AdminActivationRecycleItem,
} from '@/lib/api/admin';

type FilterStatus = 'all' | 'active' | 'expired' | 'revoked';
type ActivationTypeFilter = 'all' | 'normal' | 'fork';
type TabKey = 'active' | 'recycle';

export default function AdminActivationsPage() {
  const [items, setItems] = useState<AdminActivationItem[]>([]);
  const [recycleItems, setRecycleItems] = useState<AdminActivationRecycleItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<FilterStatus>('all');
  const [activationType, setActivationType] = useState<ActivationTypeFilter>('all');
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<TabKey>('active');
  const [selectedCodes, setSelectedCodes] = useState<string[]>([]);
  const [createCount, setCreateCount] = useState(10);
  const [createTtlDays, setCreateTtlDays] = useState(30);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [syncSources, setSyncSources] = useState<ActivationSyncSource[]>([
    'analytics_reports',
    'reports_registry',
    'simple_activations_file',
  ]);
  const [syncDryRun, setSyncDryRun] = useState(false);

  const loadActiveList = async () => {
    const res = await fetchAdminActivations({
      status: status === 'all' ? undefined : status,
      q: query || undefined,
      activation_type: activationType === 'all' ? undefined : activationType,
    });
    setItems(res);
  };

  const loadRecycleList = async () => {
    const res = await fetchActivationRecycleBin();
    setRecycleItems(res);
  };

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        if (tab === 'active') {
          const res = await fetchAdminActivations({
            status: status === 'all' ? undefined : status,
            q: query || undefined,
            activation_type: activationType === 'all' ? undefined : activationType,
          });
          if (!cancelled) setItems(res);
        } else {
          const res = await fetchActivationRecycleBin();
          if (!cancelled) setRecycleItems(res);
        }
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
  }, [status, query, tab, activationType]);

  useEffect(() => {
    setSelectedCodes([]);
  }, [tab]);

  const statusLabel: Record<string, string> = {
    active: 'Active',
    expired: 'Expired',
    revoked: 'Revoked',
    deleted: 'Deleted',
  };

  const statusColor: Record<string, string> = {
    active: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    expired: 'bg-amber-100 text-amber-700 border-amber-200',
    revoked: 'bg-rose-100 text-rose-700 border-rose-200',
    deleted: 'bg-neutral-200 text-neutral-700 border-neutral-300',
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

  const visibleCodes = useMemo(() => {
    if (tab === 'active') return items.map((x) => x.activation_code);
    return recycleItems.map((x) => x.activation_code);
  }, [items, recycleItems, tab]);

  const allSelected = visibleCodes.length > 0 && selectedCodes.length === visibleCodes.length;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedCodes([]);
      return;
    }
    setSelectedCodes(visibleCodes);
  };

  const toggleCode = (code: string) => {
    setSelectedCodes((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    );
  };

  const handleBatchStatus = async (nextStatus: 'active' | 'expired' | 'revoked') => {
    if (!selectedCodes.length) return;
    setWorking(true);
    setError(null);
    try {
      await batchUpdateActivationStatus({ codes: selectedCodes, status: nextStatus });
      await loadActiveList();
      setSelectedCodes([]);
      setNotice(`已更新 ${selectedCodes.length} 条状态为 ${nextStatus}`);
    } catch (e: any) {
      setError(e?.message || '批量更新状态失败');
    } finally {
      setWorking(false);
    }
  };

  const handleBatchDelete = async () => {
    if (!selectedCodes.length) return;
    if (!window.confirm(`确认删除选中的 ${selectedCodes.length} 个激活码？将进入垃圾桶并在 30 天后自动清理。`)) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      await batchDeleteActivations({ codes: selectedCodes });
      await loadActiveList();
      setSelectedCodes([]);
      setNotice(`已删除 ${selectedCodes.length} 条到垃圾桶`);
    } catch (e: any) {
      setError(e?.message || '批量删除失败');
    } finally {
      setWorking(false);
    }
  };

  const handleBatchRestore = async () => {
    if (!selectedCodes.length) return;
    setWorking(true);
    setError(null);
    try {
      await restoreActivationsFromRecycle({ codes: selectedCodes });
      await loadRecycleList();
      setSelectedCodes([]);
      setNotice(`已恢复 ${selectedCodes.length} 条激活码`);
    } catch (e: any) {
      setError(e?.message || '恢复失败');
    } finally {
      setWorking(false);
    }
  };

  const handlePermanentDelete = async () => {
    if (!selectedCodes.length) return;
    if (
      !window.confirm(
        `确认永久删除选中的 ${selectedCodes.length} 个激活码？此操作不可恢复，将清除报告、对话、日志等所有相关数据。`,
      )
    ) {
      return;
    }
    setWorking(true);
    setError(null);
    try {
      const res = await permanentDeleteFromRecycleBin({ codes: selectedCodes });
      await loadRecycleList();
      setSelectedCodes([]);
      setNotice(`已永久删除 ${(res as { deleted?: number })?.deleted ?? selectedCodes.length} 条`);
    } catch (e: any) {
      setError(e?.message || '永久删除失败');
    } finally {
      setWorking(false);
    }
  };

  const handleBatchCreate = async () => {
    setWorking(true);
    setError(null);
    try {
      const result = await batchCreateActivations({
        ttl_days: createTtlDays,
        count: createCount,
      });
      if (tab === 'active') {
        await loadActiveList();
      }
      setNotice(`已创建 ${result?.count ?? createCount} 条通用激活码（${createTtlDays} 天）`);
    } catch (e: any) {
      setError(e?.message || '批量创建失败');
    } finally {
      setWorking(false);
    }
  };

  const handleSyncFromDb = async () => {
    setWorking(true);
    setError(null);
    try {
      const result = await syncActivations({
        sources: syncSources,
        dry_run: syncDryRun,
        mode: 'insert_only',
        default_status: 'revoked',
      });
      if (tab === 'active') {
        await loadActiveList();
      }
      const sourceText = (result?.sources || []).join(', ');
      if (result?.dry_run) {
        setNotice(
          `预览完成：来源 [${sourceText}]，扫描 ${result?.rows_scanned ?? 0}，可新增 ${result?.would_insert ?? 0}，冲突 ${result?.conflicts ?? 0}`,
        );
      } else {
        setNotice(
          `同步完成：来源 [${sourceText}]，扫描 ${result?.rows_scanned ?? 0}，新增 ${result?.synced ?? 0}，冲突 ${result?.conflicts ?? 0}`,
        );
      }
    } catch (e: any) {
      setError(e?.message || '多源同步失败');
    } finally {
      setWorking(false);
    }
  };

  const toggleSyncSource = (source: ActivationSyncSource) => {
    setSyncSources((prev) =>
      prev.includes(source) ? prev.filter((s) => s !== source) : [...prev, source],
    );
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header className="space-y-2">
        <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
          激活码管理
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          激活码为通用码（不区分步骤）。支持批量创建、状态调整、删除入垃圾桶与恢复。过期码不可用但保留历史，删除码进入垃圾桶并在 30 天后自动清理。
        </p>
      </header>

      {notice && (
        <section className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-700 px-4 py-3 text-xs">
          {notice}
        </section>
      )}

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => setTab('active')}
          className={`px-4 py-2 rounded-xl text-xs border ${
            tab === 'active'
              ? 'bg-bd-ui-accent text-bd-ui-accent-fg border-transparent'
              : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
          }`}
        >
          激活码列表
        </button>
        <button
          type="button"
          onClick={() => setTab('recycle')}
          className={`px-4 py-2 rounded-xl text-xs border ${
            tab === 'recycle'
              ? 'bg-bd-ui-accent text-bd-ui-accent-fg border-transparent'
              : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
          }`}
        >
          激活码垃圾桶
        </button>
      </section>

      {tab === 'active' && (
        <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <p className="text-[11px] text-bd-subtle">数量</p>
            <input
              type="number"
              min={1}
              max={500}
              value={createCount}
              onChange={(e) => setCreateCount(Number(e.target.value || 1))}
              className="w-24 rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
          </div>
          <div className="space-y-1">
            <p className="text-[11px] text-bd-subtle">有效期(天)</p>
            <input
              type="number"
              min={1}
              max={3650}
              value={createTtlDays}
              onChange={(e) => setCreateTtlDays(Number(e.target.value || 30))}
              className="w-28 rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
          </div>
          <button
            type="button"
            onClick={handleBatchCreate}
            disabled={working}
            className="px-4 py-2 rounded-lg text-xs font-medium bg-bd-ui-accent text-bd-ui-accent-fg disabled:opacity-60"
          >
            批量创建
          </button>
          <button
            type="button"
            onClick={handleSyncFromDb}
            disabled={working || syncSources.length === 0}
            className="px-4 py-2 rounded-lg text-xs font-medium border border-bd-border text-bd-fg disabled:opacity-60"
          >
            {syncDryRun ? '预览同步' : '执行同步'}
          </button>
          <div className="w-full mt-1 flex flex-wrap items-center gap-3 text-[11px] text-bd-muted">
            <span>同步来源:</span>
            <label className="inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={syncSources.includes('analytics_reports')}
                onChange={() => toggleSyncSource('analytics_reports')}
              />
              analytics_reports
            </label>
            <label className="inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={syncSources.includes('reports_registry')}
                onChange={() => toggleSyncSource('reports_registry')}
              />
              reports_registry
            </label>
            <label className="inline-flex items-center gap-1">
              <input
                type="checkbox"
                checked={syncSources.includes('simple_activations_file')}
                onChange={() => toggleSyncSource('simple_activations_file')}
              />
              simple_activations_file
            </label>
            <label className="inline-flex items-center gap-1 ml-2">
              <input
                type="checkbox"
                checked={syncDryRun}
                onChange={(e) => setSyncDryRun(e.target.checked)}
              />
              dry-run（仅预览）
            </label>
          </div>
        </section>
      )}

      {/* 筛选区域 */}
      {tab === 'active' && (
      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex flex-col gap-3 w-full">
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
            <span className="text-bd-subtle">类型</span>
            {(
              [
                { key: 'all' as const, label: '全部' },
                { key: 'normal' as const, label: '正式' },
                { key: 'fork' as const, label: 'Fork' },
              ]
            ).map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setActivationType(key)}
                className={`px-3 py-1.5 rounded-full border text-[11px] ${
                  activationType === key
                    ? 'bg-violet-600 text-white border-transparent'
                    : 'text-bd-muted border-bd-border hover:text-bd-fg hover:bg-bd-overlay-md'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
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
      )}

      {/* 批量操作 */}
      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-2 text-xs">
        <span className="text-bd-subtle">已选 {selectedCodes.length} 项</span>
        {tab === 'active' ? (
          <>
            <button
              type="button"
              disabled={working || !selectedCodes.length}
              onClick={() => handleBatchStatus('expired')}
              className="px-3 py-1.5 rounded-lg border border-amber-200 bg-amber-50 text-amber-700 disabled:opacity-50"
            >
              批量设为过期
            </button>
            <button
              type="button"
              disabled={working || !selectedCodes.length}
              onClick={() => handleBatchStatus('revoked')}
              className="px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 disabled:opacity-50"
            >
              批量停用
            </button>
            <button
              type="button"
              disabled={working || !selectedCodes.length}
              onClick={handleBatchDelete}
              className="px-3 py-1.5 rounded-lg border border-neutral-300 bg-neutral-100 text-neutral-700 disabled:opacity-50"
            >
              删除到垃圾桶
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              disabled={working || !selectedCodes.length}
              onClick={handleBatchRestore}
              className="px-3 py-1.5 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-700 disabled:opacity-50"
            >
              从垃圾桶恢复
            </button>
            <button
              type="button"
              disabled={working || !selectedCodes.length}
              onClick={handlePermanentDelete}
              className="px-3 py-1.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 disabled:opacity-50"
            >
              永久删除（不可恢复）
            </button>
          </>
        )}
      </section>

      {/* 列表区域 */}
      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        {loading ? (
          <p className="text-xs text-bd-subtle">加载中…</p>
        ) : error ? (
          <p className="text-xs text-red-500">{error}</p>
        ) : (tab === 'active' ? items.length === 0 : recycleItems.length === 0) ? (
          <p className="text-xs text-bd-subtle">{tab === 'active' ? '暂无激活码记录。' : '垃圾桶为空。'}</p>
        ) : (
          <div className="overflow-x-auto -mx-2">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                  <th className="px-2 py-2 text-left font-medium">
                    <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} />
                  </th>
                  <th className="px-2 py-2 text-left font-medium">激活码</th>
                  <th className="px-2 py-2 text-left font-medium">类型</th>
                  <th className="px-2 py-2 text-left font-medium">Session ID</th>
                  <th className="px-2 py-2 text-left font-medium">模式</th>
                  {tab === 'active' ? (
                    <>
                      <th className="px-2 py-2 text-left font-medium">状态</th>
                      <th className="px-2 py-2 text-left font-medium">创建时间</th>
                      <th className="px-2 py-2 text-left font-medium">过期时间</th>
                      <th className="px-2 py-2 text-left font-medium">最后活跃</th>
                      <th className="px-2 py-2 text-left font-medium">归属用户</th>
                    </>
                  ) : (
                    <>
                      <th className="px-2 py-2 text-left font-medium">删除时间</th>
                      <th className="px-2 py-2 text-left font-medium">清理时间</th>
                      <th className="px-2 py-2 text-left font-medium">剩余天数</th>
                      <th className="px-2 py-2 text-left font-medium">操作人</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {(tab === 'active' ? items : recycleItems).map((item) => (
                  <tr key={item.activation_code} className="border-b border-bd-border/60 last:border-0">
                    <td className="px-2 py-2">
                      <input
                        type="checkbox"
                        checked={selectedCodes.includes(item.activation_code)}
                        onChange={() => toggleCode(item.activation_code)}
                      />
                    </td>
                    <td className="px-2 py-2 font-mono text-[11px]" style={{ color: 'var(--bd-fg)' }}>
                      {item.activation_code}
                    </td>
                    <td className="px-2 py-2">
                      {tab === 'active' && 'activation_type' in item ? (
                        (item as AdminActivationItem).activation_type === 'fork' ? (
                          <span className="inline-flex items-center rounded-full border border-violet-300 bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-700 px-2 py-0.5 text-[10px] font-medium">
                            Fork
                          </span>
                        ) : (
                          <span className="text-[10px] text-bd-muted">正式</span>
                        )
                      ) : (
                        <span className="text-[10px] text-bd-subtle">—</span>
                      )}
                    </td>
                    <td className="px-2 py-2 font-mono text-[11px] text-bd-subtle max-w-[160px] truncate">
                      {item.session_id}
                    </td>
                    <td className="px-2 py-2 text-[11px] text-bd-muted">{item.mode}</td>
                    {tab === 'active' ? (
                      <>
                        <td className="px-2 py-2">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-medium ${
                              statusColor[(item as AdminActivationItem).status] || 'bg-bd-overlay-md text-bd-subtle border-bd-border'
                            }`}
                          >
                            {statusLabel[(item as AdminActivationItem).status] || (item as AdminActivationItem).status}
                          </span>
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {formatTime((item as AdminActivationItem).created_at)}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {formatTime((item as AdminActivationItem).expires_at)}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {formatTime((item as AdminActivationItem).last_activity_at)}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {(item as AdminActivationItem).owner_email || (item as AdminActivationItem).owner_user_id || '未绑定'}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {formatTime((item as AdminActivationRecycleItem).deleted_at)}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {formatTime((item as AdminActivationRecycleItem).purge_after)}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {(item as AdminActivationRecycleItem).days_remaining ?? '—'}
                        </td>
                        <td className="px-2 py-2 text-[11px] text-bd-muted whitespace-nowrap">
                          {(item as AdminActivationRecycleItem).deleted_by_email || (item as AdminActivationRecycleItem).deleted_by_user_id || '—'}
                        </td>
                      </>
                    )}
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


