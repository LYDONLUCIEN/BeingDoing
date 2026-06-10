'use client';

import { useMemo, useState } from 'react';
import type { PromptLabBinding } from '@/lib/api/admin';
import { formatAdminTime } from '@/lib/promptCatalogUtils';
import { useAdminSavepoints } from '@/hooks/useAdminSavepoints';
import { RefreshCw } from 'lucide-react';

interface SavepointSelectorPanelProps {
  profileId?: string;
  bindings?: PromptLabBinding[];
  onNotice?: (msg: string) => void;
  onError?: (msg: string) => void;
}

export function SavepointSelectorPanel({
  profileId = '',
  bindings = [],
  onNotice,
  onError,
}: SavepointSelectorPanelProps) {
  const { savepoints, loading, error, reload, loadSavepoint } = useAdminSavepoints();
  const [showAll, setShowAll] = useState(false);
  const [query, setQuery] = useState('');
  const [phaseFilter, setPhaseFilter] = useState<'all' | string>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const boundCodes = useMemo(() => {
    if (!profileId) return new Set<string>();
    return new Set(
      bindings.filter((b) => b.profile_id === profileId).map((b) => b.activation_code.toUpperCase()),
    );
  }, [bindings, profileId]);

  const scopedSavepoints = useMemo(() => {
    if (showAll) return savepoints;
    if (boundCodes.size === 0) return [];
    return savepoints.filter((sp) => boundCodes.has(sp.source_activation_code.toUpperCase()));
  }, [savepoints, showAll, boundCodes]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return scopedSavepoints.filter((sp) => {
      const phaseOk = phaseFilter === 'all' || sp.phase === phaseFilter;
      if (!phaseOk) return false;
      if (!q) return true;
      return (
        sp.display_name.toLowerCase().includes(q) ||
        sp.savepoint_id.toLowerCase().includes(q) ||
        sp.source_activation_code.toLowerCase().includes(q)
      );
    });
  }, [scopedSavepoints, query, phaseFilter]);

  const selected = filtered.find((sp) => sp.savepoint_id === selectedId) || filtered[0] || null;

  const handleResume = async () => {
    if (!selected) return;
    if (!confirm(`确定从检查点「${selected.display_name}」续测？将覆盖当前调试 report 状态。`)) return;
    setWorking(true);
    try {
      await loadSavepoint(selected);
      onNotice?.(`已加载检查点：${selected.display_name}`);
    } catch (e: unknown) {
      onError?.(e instanceof Error ? e.message : '加载检查点失败');
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="rounded-2xl bg-bd-card border border-bd-border p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-bd-fg">Savepoint 续测</h3>
          <p className="text-xs text-bd-subtle mt-1">
            {showAll
              ? '显示全部检查点（与沙箱页相同数据源）'
              : profileId
                ? `默认仅显示当前 Profile 已绑定 SBX/ADM 激活码下的检查点（${boundCodes.size} 个绑定）`
                : '请先在 Profile 编辑页选择 profile 并绑定 SBX/ADM 激活码'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className={`px-2.5 py-1 rounded-lg text-xs border ${
              showAll ? 'border-bd-ui-accent bg-bd-overlay-md' : 'border-bd-border hover:bg-bd-overlay-sm'
            }`}
          >
            {showAll ? '仅看绑定' : '看全部'}
          </button>
          <button
            type="button"
            onClick={() => void reload()}
            disabled={loading}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {(error || (!showAll && boundCodes.size === 0 && profileId)) && (
        <div className="text-xs text-amber-700 dark:text-amber-300 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 px-3 py-2">
          {error ||
            '当前 profile 尚无 SBX/ADM 绑定，请切换到「Profile 编辑」绑定激活码，或开启「看全部」。'}
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索名称 / savepoint_id / 激活码"
          className="min-w-[200px] flex-1 rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
        />
        <select
          value={phaseFilter}
          onChange={(e) => setPhaseFilter(e.target.value)}
          className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-2 text-xs"
        >
          <option value="all">全部 phase</option>
          <option value="values">values</option>
          <option value="strengths">strengths</option>
          <option value="interests">interests</option>
          <option value="purpose">purpose</option>
          <option value="rumination">rumination</option>
        </select>
      </div>

      {loading && filtered.length === 0 ? (
        <p className="text-xs text-bd-subtle">加载 Savepoint…</p>
      ) : filtered.length === 0 ? (
        <p className="text-xs text-bd-subtle">暂无匹配的检查点。</p>
      ) : (
        <div className="max-h-48 overflow-y-auto rounded-lg border border-bd-border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-bd-overlay-sm">
              <tr className="text-left text-bd-subtle border-b border-bd-border">
                <th className="px-3 py-2 font-medium w-8" />
                <th className="px-3 py-2 font-medium">名称</th>
                <th className="px-3 py-2 font-medium">phase</th>
                <th className="px-3 py-2 font-medium">激活码</th>
                <th className="px-3 py-2 font-medium">创建时间</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 50).map((sp) => (
                <tr
                  key={sp.savepoint_id}
                  className={`border-b border-bd-border/60 cursor-pointer hover:bg-bd-overlay-sm ${
                    selected?.savepoint_id === sp.savepoint_id ? 'bg-bd-overlay-md' : ''
                  }`}
                  onClick={() => setSelectedId(sp.savepoint_id)}
                >
                  <td className="px-3 py-2">
                    <input
                      type="radio"
                      checked={selected?.savepoint_id === sp.savepoint_id}
                      onChange={() => setSelectedId(sp.savepoint_id)}
                    />
                  </td>
                  <td className="px-3 py-2">{sp.display_name}</td>
                  <td className="px-3 py-2 font-mono text-bd-muted">{sp.phase}</td>
                  <td className="px-3 py-2 font-mono text-bd-muted">{sp.source_activation_code}</td>
                  <td className="px-3 py-2 text-bd-muted">{formatAdminTime(sp.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap gap-2 items-center">
        <button
          type="button"
          disabled={working || !selected}
          onClick={() => void handleResume()}
          className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg text-xs disabled:opacity-50"
        >
          {working ? '加载中…' : '从 Savepoint 续测'}
        </button>
        {selected ? (
          <span className="text-[10px] text-bd-subtle font-mono">
            已选：{selected.savepoint_id} · {selected.phase}/{selected.thread_id}
          </span>
        ) : null}
      </div>
    </section>
  );
}
