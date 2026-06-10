'use client';

import { useState } from 'react';
import type { PromptCatalogLayer, PromptContentSegment } from '@/lib/api/admin';
import { extractLayerCopyText } from '@/lib/promptCatalogUtils';
import { PromptContentRenderer } from './PromptContentRenderer';

const CATEGORY_BADGE: Record<string, string> = {
  intro: 'bg-blue-100 text-blue-800 border-blue-200',
  main: 'bg-slate-100 text-slate-700 border-slate-200',
  fallback: 'bg-orange-100 text-orange-800 border-orange-200',
  addon: 'bg-violet-100 text-violet-800 border-violet-200',
  runtime: 'bg-amber-100 text-amber-900 border-amber-200',
  outro: 'bg-emerald-100 text-emerald-800 border-emerald-200',
};

interface LayerStackViewProps {
  layers: PromptCatalogLayer[];
  variableSamples?: Record<string, string>;
  activePhase: string;
  highlightQuery?: string;
  onCopy?: (text: string, label: string) => void;
}

function NestedConditionBlock({
  conditions,
  variableSamples,
  activePhase,
  highlightQuery = '',
}: {
  conditions: Array<{
    condition: string;
    content: string;
    segments?: PromptContentSegment[];
  }>;
  variableSamples?: Record<string, string>;
  activePhase: string;
  highlightQuery?: string;
}) {
  if (!conditions.length) return null;
  return (
    <div className="mt-2 space-y-2 border-l-2 border-bd-border pl-3">
      {conditions.map((c) => {
        const active =
          c.condition === 'rumination_step_addon' && activePhase === 'rumination';
        return (
          <div
            key={c.condition}
            className={`rounded-lg border px-2 py-2 ${
              active ? 'border-violet-300 bg-violet-50/50' : 'border-bd-border/60 opacity-60'
            }`}
          >
            <p className="text-[10px] text-bd-subtle mb-1 font-mono">{`{% if ${c.condition} %}`}</p>
            <PromptContentRenderer
              segments={c.segments}
              content={c.content}
              variableSamples={variableSamples}
              muted={!active}
              highlightQuery={highlightQuery}
            />
          </div>
        );
      })}
    </div>
  );
}

export function LayerStackView({
  layers,
  variableSamples,
  activePhase,
  highlightQuery = '',
  onCopy,
}: LayerStackViewProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggle = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="space-y-2">
      {layers.map((layer, idx) => {
        const isRuntime = layer.kind === 'runtime';
        const collapsed = isRuntime && layer.collapsed_default !== false && !expanded[layer.id];
        const inactiveBranch = layer.kind === 'static' && layer.active === false;
        const badge = CATEGORY_BADGE[layer.category || (isRuntime ? 'runtime' : 'main')] || CATEGORY_BADGE.main;

        return (
          <div
            key={layer.id}
            className={`rounded-xl border overflow-hidden ${
              inactiveBranch
                ? 'border-bd-border/50 opacity-50'
                : layer.active
                  ? 'border-bd-ui-accent/40'
                  : 'border-bd-border'
            }`}
          >
            <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-bd-overlay-sm border-b border-bd-border/60">
              <span className="text-[10px] font-mono text-bd-subtle">#{idx + 1}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded border ${badge}`}>
                {layer.category || layer.kind}
              </span>
              {isRuntime ? (
                <span className="text-[10px] px-1.5 py-0.5 rounded border bg-amber-50 text-amber-800 border-amber-200">
                  runtime
                </span>
              ) : null}
              <span className="text-xs font-medium text-bd-fg flex-1 min-w-0 truncate">{layer.label}</span>
              {isRuntime ? (
                <button
                  type="button"
                  onClick={() => toggle(layer.id)}
                  className="text-[10px] px-2 py-0.5 rounded border border-bd-border hover:bg-bd-overlay-md"
                >
                  {collapsed ? '展开' : '收起'}
                </button>
              ) : null}
              {onCopy ? (
                <button
                  type="button"
                  onClick={() => onCopy(extractLayerCopyText(layer, variableSamples), layer.label)}
                  className="text-[10px] px-2 py-0.5 rounded border border-bd-border hover:bg-bd-overlay-md"
                >
                  复制
                </button>
              ) : null}
            </div>
            {!collapsed ? (
              <div className="px-3 py-3 space-y-2">
                {isRuntime ? (
                  <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-[10px] text-bd-subtle">
                    {layer.inject_after ? (
                      <>
                        <dt>注入位置</dt>
                        <dd className="text-bd-muted">{layer.inject_after}</dd>
                      </>
                    ) : null}
                    {layer.trigger ? (
                      <>
                        <dt>触发条件</dt>
                        <dd className="text-bd-muted">{layer.trigger}</dd>
                      </>
                    ) : null}
                    {layer.source_path ? (
                      <>
                        <dt>源码</dt>
                        <dd className="font-mono text-bd-muted break-all">{layer.source_path}</dd>
                      </>
                    ) : null}
                  </dl>
                ) : null}
                <PromptContentRenderer
                  segments={layer.segments}
                  content={layer.content}
                  variableSamples={variableSamples}
                  muted={inactiveBranch}
                  highlightQuery={highlightQuery}
                />
                {layer.nested_conditions?.length ? (
                  <NestedConditionBlock
                    conditions={layer.nested_conditions}
                    variableSamples={variableSamples}
                    activePhase={activePhase}
                    highlightQuery={highlightQuery}
                  />
                ) : null}
              </div>
            ) : (
              <div className="px-3 py-2 text-[10px] text-bd-subtle italic">运行时注入槽（已折叠）</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
