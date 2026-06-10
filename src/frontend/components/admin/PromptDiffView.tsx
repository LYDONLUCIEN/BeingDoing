'use client';

import { useMemo, useState } from 'react';
import type { PromptCatalogSimpleChatDiff } from '@/lib/api/admin';
import type { PhaseKey } from '@/lib/explore/session';
import { computeLineDiff, DIFF_ROW_CLASS } from '@/lib/lineDiff';

type DiffSource = 'canonical' | 'override' | 'effective';

const SOURCE_LABELS: Record<DiffSource, string> = {
  canonical: 'Canonical YAML',
  override: 'Lab Override',
  effective: 'Effective 预览',
};

interface PromptDiffViewProps {
  diff: PromptCatalogSimpleChatDiff;
  previewPhase: PhaseKey;
}

function getSourceText(diff: PromptCatalogSimpleChatDiff, source: DiffSource): string {
  if (source === 'canonical') return diff.canonical_template;
  if (source === 'override') return diff.override_template || '';
  return diff.effective_preview;
}

export function PromptDiffView({ diff, previewPhase }: PromptDiffViewProps) {
  const [viewMode, setViewMode] = useState<'compare' | 'single'>('compare');
  const [leftSource, setLeftSource] = useState<DiffSource>('canonical');
  const [rightSource, setRightSource] = useState<DiffSource>('effective');
  const [singleSource, setSingleSource] = useState<DiffSource>('canonical');

  const leftText = getSourceText(diff, leftSource);
  const rightText = getSourceText(diff, rightSource);
  const singleText = getSourceText(diff, singleSource);

  const diffRows = useMemo(() => computeLineDiff(leftText, rightText), [leftText, rightText]);

  const canCompareOverride = diff.has_override && !!diff.override_template;

  return (
    <section className="rounded-2xl bg-bd-card border border-bd-border p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-bd-fg">simple_chat_system · 只读对比</h3>
        <span className="text-[10px] text-bd-subtle">预览阶段：{previewPhase}</span>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setViewMode('compare')}
          className={`px-2.5 py-1 rounded-lg text-xs border ${
            viewMode === 'compare' ? 'border-bd-ui-accent bg-bd-overlay-md' : 'border-bd-border'
          }`}
        >
          并排 diff
        </button>
        <button
          type="button"
          onClick={() => setViewMode('single')}
          className={`px-2.5 py-1 rounded-lg text-xs border ${
            viewMode === 'single' ? 'border-bd-ui-accent bg-bd-overlay-md' : 'border-bd-border'
          }`}
        >
          单视图
        </button>
      </div>

      {viewMode === 'compare' ? (
        <>
          <div className="flex flex-wrap gap-2 items-center text-xs">
            <label className="inline-flex items-center gap-1">
              左
              <select
                value={leftSource}
                onChange={(e) => setLeftSource(e.target.value as DiffSource)}
                className="rounded border border-bd-border bg-bd-overlay px-2 py-1"
              >
                {(Object.keys(SOURCE_LABELS) as DiffSource[]).map((k) => (
                  <option key={k} value={k} disabled={k === 'override' && !canCompareOverride}>
                    {SOURCE_LABELS[k]}
                  </option>
                ))}
              </select>
            </label>
            <span className="text-bd-subtle">vs</span>
            <label className="inline-flex items-center gap-1">
              右
              <select
                value={rightSource}
                onChange={(e) => setRightSource(e.target.value as DiffSource)}
                className="rounded border border-bd-border bg-bd-overlay px-2 py-1"
              >
                {(Object.keys(SOURCE_LABELS) as DiffSource[]).map((k) => (
                  <option key={k} value={k} disabled={k === 'override' && !canCompareOverride}>
                    {SOURCE_LABELS[k]}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!canCompareOverride && (leftSource === 'override' || rightSource === 'override') ? (
            <p className="text-xs text-bd-subtle">未选择 profile 或尚无 override 模板。</p>
          ) : (
            <div className="rounded-lg border border-bd-border overflow-hidden max-h-[420px] overflow-y-auto">
              <div className="grid grid-cols-2 text-[10px] font-mono border-b border-bd-border bg-bd-overlay-sm sticky top-0">
                <div className="px-2 py-1 border-r border-bd-border">{SOURCE_LABELS[leftSource]}</div>
                <div className="px-2 py-1">{SOURCE_LABELS[rightSource]}</div>
              </div>
              {diffRows.map((row, idx) => (
                <div
                  key={`${row.type}-${idx}`}
                  className={`grid grid-cols-2 text-[11px] font-mono border-b border-bd-border/40 ${DIFF_ROW_CLASS[row.type]}`}
                >
                  <pre className="px-2 py-0.5 whitespace-pre-wrap break-all border-r border-bd-border/40 min-h-[1.25rem]">
                    {row.left ?? ''}
                  </pre>
                  <pre className="px-2 py-0.5 whitespace-pre-wrap break-all min-h-[1.25rem]">
                    {row.right ?? ''}
                  </pre>
                </div>
              ))}
            </div>
          )}
          <p className="text-[10px] text-bd-subtle">
            <span className="inline-block w-3 h-3 bg-emerald-100 border border-emerald-200 mr-1 align-middle" />
            新增
            <span className="inline-block w-3 h-3 bg-rose-100 border border-rose-200 mx-1 ml-3 align-middle" />
            删除
            <span className="inline-block w-3 h-3 bg-amber-100 border border-amber-200 mx-1 ml-3 align-middle" />
            变更
          </p>
        </>
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            {(Object.keys(SOURCE_LABELS) as DiffSource[]).map((k) => (
              <button
                key={k}
                type="button"
                disabled={k === 'override' && !canCompareOverride}
                onClick={() => setSingleSource(k)}
                className={`px-2.5 py-1 rounded-lg text-xs border disabled:opacity-40 ${
                  singleSource === k ? 'border-bd-ui-accent bg-bd-overlay-md' : 'border-bd-border'
                }`}
              >
                {SOURCE_LABELS[k]}
              </button>
            ))}
          </div>
          {singleSource === 'override' && !canCompareOverride ? (
            <p className="text-xs text-bd-subtle">未选择 profile 或尚无 override 模板。</p>
          ) : (
            <textarea
              readOnly
              rows={12}
              className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-[11px] font-mono"
              value={singleText}
            />
          )}
        </>
      )}

      {diff.override_meta ? (
        <p className="text-[10px] text-bd-subtle">
          Override：{diff.override_meta.profile_name} · {diff.override_meta.version_id}
        </p>
      ) : null}
      <p className="text-[10px] text-bd-subtle font-mono">{diff.canonical_source}</p>
    </section>
  );
}
