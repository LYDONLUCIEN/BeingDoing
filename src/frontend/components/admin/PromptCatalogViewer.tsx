'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchPromptCatalog,
  type PromptCatalogData,
  type PromptCatalogPhase,
  type PromptCatalogSection,
  type PromptLabBinding,
} from '@/lib/api/admin';
import { PHASES, type PhaseKey } from '@/lib/explore/session';
import {
  CATEGORY_LABELS,
  collectCatalogCategories,
  collectCatalogTags,
  defaultCatalogFilters,
  downloadJson,
  extractSectionCopyText,
  phaseHasVisibleContent,
  sectionMatchesFilters,
  type CatalogFilterState,
} from '@/lib/promptCatalogUtils';
import { ForkFromScratchPanel } from './ForkFromScratchPanel';
import { LayerStackView } from './LayerStackView';
import { PromptContentRenderer } from './PromptContentRenderer';
import { PromptDiffView } from './PromptDiffView';
import { SavepointSelectorPanel } from './SavepointSelectorPanel';

const PHASE_BORDER: Record<string, string> = {
  blue: 'border-blue-300',
  amber: 'border-amber-300',
  rose: 'border-rose-300',
  emerald: 'border-emerald-300',
  violet: 'border-violet-300',
};

const PHASE_HEADER: Record<string, string> = {
  blue: 'bg-blue-50 text-blue-900',
  amber: 'bg-amber-50 text-amber-900',
  rose: 'bg-rose-50 text-rose-900',
  emerald: 'bg-emerald-50 text-emerald-900',
  violet: 'bg-violet-50 text-violet-900',
};

function SectionBlock({
  section,
  variableSamples,
  activePhase,
  forceOpen,
  filters,
  onCopy,
}: {
  section: PromptCatalogSection;
  variableSamples?: Record<string, string>;
  activePhase: string;
  forceOpen?: boolean;
  filters: CatalogFilterState;
  onCopy?: (text: string, label: string) => void;
}) {
  const [open, setOpen] = useState(section.key === 'main_dialogue');
  const isOpen = forceOpen || open;

  return (
    <div className="rounded-xl border border-bd-border overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 hover:bg-bd-overlay-sm">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex-1 flex items-center justify-between text-left min-w-0"
        >
          <span className="text-xs font-medium text-bd-fg truncate">{section.label}</span>
          <span className="text-[10px] text-bd-subtle font-mono ml-2 shrink-0">
            {CATEGORY_LABELS[section.category] || section.category}
          </span>
        </button>
        {onCopy ? (
          <button
            type="button"
            onClick={() => onCopy(extractSectionCopyText(section, variableSamples), section.label)}
            className="text-[10px] px-2 py-0.5 rounded border border-bd-border hover:bg-bd-overlay-md shrink-0"
          >
            复制
          </button>
        ) : null}
        <button type="button" onClick={() => setOpen((v) => !v)} className="text-xs text-bd-subtle px-1">
          {isOpen ? '▾' : '▸'}
        </button>
      </div>
      {isOpen ? (
        <div className="px-3 pb-3 space-y-2 border-t border-bd-border/60">
          {section.source_path ? (
            <p className="text-[10px] text-bd-subtle pt-2 font-mono break-all">{section.source_path}</p>
          ) : null}
          {section.layer_stack ? (
            <LayerStackView
              layers={section.layer_stack}
              variableSamples={variableSamples}
              activePhase={activePhase}
              highlightQuery={filters.searchQuery}
              onCopy={onCopy}
            />
          ) : section.items ? (
            <div className="space-y-3">
              {section.items.map((item, i) => (
                <div key={`${item.role}-${i}`} className="rounded-lg border border-bd-border/70 p-2">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <p className="text-[10px] text-bd-subtle">{item.label || item.role}</p>
                    {onCopy ? (
                      <button
                        type="button"
                        onClick={() =>
                          onCopy(
                            item.content || item.segments?.map((s) => s.content || '').join('') || '',
                            item.label || item.role,
                          )
                        }
                        className="text-[10px] px-1.5 py-0.5 rounded border border-bd-border hover:bg-bd-overlay-md"
                      >
                        复制
                      </button>
                    ) : null}
                  </div>
                  <PromptContentRenderer
                    segments={item.segments}
                    content={item.content}
                    variableSamples={variableSamples}
                    highlightQuery={filters.searchQuery}
                  />
                </div>
              ))}
            </div>
          ) : (
            <PromptContentRenderer
              segments={section.segments}
              content={section.content}
              variableSamples={variableSamples}
              highlightQuery={filters.searchQuery}
            />
          )}
        </div>
      ) : null}
    </div>
  );
}

function PhaseAccordion({
  phase,
  expanded,
  onToggle,
  variableSamples,
  filters,
  forceExpand,
  onCopy,
}: {
  phase: PromptCatalogPhase;
  expanded: boolean;
  onToggle: () => void;
  variableSamples?: Record<string, string>;
  filters: CatalogFilterState;
  forceExpand?: boolean;
  onCopy?: (text: string, label: string) => void;
}) {
  const [rumStepOpen, setRumStepOpen] = useState<number | null>(3);
  const isExpanded = forceExpand || expanded;

  const visibleSections = phase.sections.filter((sec) => sectionMatchesFilters(sec, phase.key, filters));

  return (
    <div className={`rounded-2xl border-2 overflow-hidden ${PHASE_BORDER[phase.color] || 'border-bd-border'}`}>
      <button
        type="button"
        onClick={onToggle}
        className={`w-full flex items-center justify-between px-4 py-3 ${PHASE_HEADER[phase.color] || 'bg-bd-overlay-sm'}`}
      >
        <span className="text-sm font-semibold">
          {phase.label}
          <span className="ml-2 text-xs font-normal opacity-70">{phase.key}</span>
        </span>
        <span className="text-xs">{isExpanded ? '▾' : '▸'}</span>
      </button>
      {isExpanded ? (
        <div className="p-4 space-y-3 bg-bd-card">
          {visibleSections.map((sec) => (
            <SectionBlock
              key={sec.key}
              section={sec}
              variableSamples={variableSamples}
              activePhase={phase.key}
              forceOpen={!!filters.searchQuery.trim()}
              filters={filters}
              onCopy={onCopy}
            />
          ))}

          {phase.rumination_steps?.length ? (
            <div className="pt-2 space-y-2">
              <h4 className="text-xs font-medium text-bd-fg">筛选子步 1–7</h4>
              {phase.rumination_steps.map((rs) => {
                const rsSections = rs.sections.filter((sec) =>
                  sectionMatchesFilters(sec, 'rumination', filters),
                );
                if (!rsSections.length && filters.phaseFilter !== 'all' && filters.phaseFilter !== 'rumination') {
                  return null;
                }
                if (!rsSections.length && filters.searchQuery.trim()) return null;
                return (
                  <div key={rs.step} className="rounded-xl border border-violet-200 overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setRumStepOpen((cur) => (cur === rs.step ? null : rs.step))}
                      className="w-full flex items-center justify-between px-3 py-2 bg-violet-50/80 text-left"
                    >
                      <span className="text-xs font-medium text-violet-900">
                        步骤 {rs.step}
                        <span className="ml-2 text-[10px] font-normal opacity-70">
                          opening: {rs.opening_mode}
                        </span>
                      </span>
                      <span className="text-xs text-violet-700">
                        {rumStepOpen === rs.step || filters.searchQuery.trim() ? '▾' : '▸'}
                      </span>
                    </button>
                    {rumStepOpen === rs.step || filters.searchQuery.trim() ? (
                      <div className="p-3 space-y-2 bg-bd-card">
                        {rsSections.map((sec) => (
                          <SectionBlock
                            key={sec.key}
                            section={sec}
                            variableSamples={variableSamples}
                            activePhase="rumination"
                            forceOpen={!!filters.searchQuery.trim()}
                            filters={filters}
                            onCopy={onCopy}
                          />
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export interface PromptCatalogViewerProps {
  profileId?: string;
  bindings?: PromptLabBinding[];
}

export function PromptCatalogViewer({ profileId = '', bindings = [] }: PromptCatalogViewerProps) {
  const [locale, setLocale] = useState<'zh' | 'en'>('zh');
  const [previewPhase, setPreviewPhase] = useState<PhaseKey>('values');
  const [catalog, setCatalog] = useState<PromptCatalogData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [expandedPhase, setExpandedPhase] = useState<PhaseKey | null>('values');
  const [filters, setFilters] = useState<CatalogFilterState>(defaultCatalogFilters());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPromptCatalog({
        locale,
        profileId: profileId || undefined,
        previewPhase,
      });
      setCatalog(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '加载 Prompt Catalog 失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [locale, profileId, previewPhase]);

  useEffect(() => {
    void load();
  }, [load]);

  const variableSamples = catalog?.variable_samples;

  const phaseMap = useMemo(() => {
    const m = new Map<string, PromptCatalogPhase>();
    catalog?.phases.forEach((p) => m.set(p.key, p));
    return m;
  }, [catalog]);

  const categories = useMemo(() => (catalog ? collectCatalogCategories(catalog) : []), [catalog]);
  const tags = useMemo(() => (catalog ? collectCatalogTags(catalog) : []), [catalog]);

  const searchActive = !!filters.searchQuery.trim();

  const matchingPhases = useMemo(() => {
    if (!catalog || !searchActive) return new Set<PhaseKey>();
    const hits = new Set<PhaseKey>();
    catalog.phases.forEach((p) => {
      if (phaseHasVisibleContent(p, filters)) hits.add(p.key as PhaseKey);
    });
    return hits;
  }, [catalog, filters, searchActive]);

  useEffect(() => {
    if (!searchActive || matchingPhases.size === 0) return;
    if (matchingPhases.size === 1) {
      setExpandedPhase(Array.from(matchingPhases)[0]);
    }
  }, [searchActive, matchingPhases]);

  const handleCopy = async (text: string, label: string) => {
    if (!text.trim()) {
      setNotice('无可复制内容');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setNotice(`已复制：${label}`);
      setTimeout(() => setNotice(null), 2000);
    } catch {
      setNotice('复制失败');
    }
  };

  const handleExportPhase = () => {
    if (!catalog) return;
    const phase = phaseMap.get(previewPhase);
    if (!phase) return;
    downloadJson(`prompt-catalog-${previewPhase}-${locale}.json`, phase);
    setNotice(`已导出阶段 ${previewPhase}`);
    setTimeout(() => setNotice(null), 2000);
  };

  const handleExportFull = () => {
    if (!catalog) return;
    downloadJson(`prompt-catalog-full-${locale}.json`, catalog);
    setNotice('已导出完整 Catalog');
    setTimeout(() => setNotice(null), 2000);
  };

  const updateFilter = <K extends keyof CatalogFilterState>(key: K, value: CatalogFilterState[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-bd-fg">Prompt Catalog</h2>
          <p className="text-sm text-bd-muted leading-relaxed mt-1">
            只读浏览 simple_chat 提示词结构（不含 LangGraph）。Canonical YAML 不可在线编辑；override 仍在 Prompt Lab 标签页管理。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-bd-border overflow-hidden text-xs">
            <button
              type="button"
              onClick={() => setLocale('zh')}
              className={`px-3 py-1.5 ${locale === 'zh' ? 'bg-bd-ui-accent text-bd-ui-accent-fg' : 'hover:bg-bd-overlay-sm'}`}
            >
              中文
            </button>
            <button
              type="button"
              onClick={() => setLocale('en')}
              className={`px-3 py-1.5 ${locale === 'en' ? 'bg-bd-ui-accent text-bd-ui-accent-fg' : 'hover:bg-bd-overlay-sm'}`}
            >
              EN
            </button>
          </div>
          <select
            value={previewPhase}
            onChange={(e) => setPreviewPhase(e.target.value as PhaseKey)}
            className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
          >
            {PHASES.map((p) => (
              <option key={p.key} value={p.key}>
                Effective 预览 · {p.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md disabled:opacity-50"
          >
            刷新
          </button>
        </div>
      </header>

      <SavepointSelectorPanel
        profileId={profileId}
        bindings={bindings}
        onNotice={setNotice}
        onError={setError}
      />

      <ForkFromScratchPanel profileId={profileId} onNotice={setNotice} onError={setError} />

      {notice ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-700 px-4 py-3 text-xs">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">{error}</div>
      ) : null}

      <section className="rounded-2xl bg-bd-card border border-bd-border p-4 space-y-3">
        <h3 className="text-sm font-medium text-bd-fg">搜索与筛选</h3>
        <input
          value={filters.searchQuery}
          onChange={(e) => updateFilter('searchQuery', e.target.value)}
          placeholder="关键词搜索（匹配提示词正文、标签、路径）"
          className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-sm"
        />
        <div className="flex flex-wrap gap-2">
          <select
            value={filters.phaseFilter}
            onChange={(e) => updateFilter('phaseFilter', e.target.value as PhaseKey | 'all')}
            className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
          >
            <option value="all">全部阶段</option>
            {PHASES.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </select>
          <select
            value={filters.categoryFilter}
            onChange={(e) => updateFilter('categoryFilter', e.target.value)}
            className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
          >
            <option value="all">全部分类</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_LABELS[c] || c}
              </option>
            ))}
          </select>
          <select
            value={filters.tagFilter}
            onChange={(e) => updateFilter('tagFilter', e.target.value)}
            className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs min-w-[140px]"
          >
            <option value="all">全部 tag</option>
            {tags.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setFilters(defaultCatalogFilters())}
            className="px-2.5 py-1.5 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md"
          >
            清除筛选
          </button>
          <button
            type="button"
            disabled={!catalog}
            onClick={handleExportPhase}
            className="px-2.5 py-1.5 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md disabled:opacity-50"
          >
            导出当前阶段 JSON
          </button>
          <button
            type="button"
            disabled={!catalog}
            onClick={handleExportFull}
            className="px-2.5 py-1.5 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md disabled:opacity-50"
          >
            导出完整 Catalog
          </button>
        </div>
        {searchActive ? (
          <p className="text-[10px] text-bd-subtle">
            搜索命中 {matchingPhases.size} 个阶段，匹配区块已高亮并自动展开。
          </p>
        ) : null}
      </section>

      {loading && !catalog ? <p className="text-xs text-bd-subtle">加载 Catalog…</p> : null}

      {catalog ? (
        <>
          {catalog.simple_chat_system_diff ? (
            <PromptDiffView diff={catalog.simple_chat_system_diff} previewPhase={previewPhase} />
          ) : null}

          <div className="space-y-4">
            {PHASES.map((meta) => {
              const phase = phaseMap.get(meta.key);
              if (!phase) return null;
              if (!phaseHasVisibleContent(phase, filters)) return null;
              const forceExpand = searchActive && matchingPhases.has(meta.key);
              return (
                <div key={meta.key}>
                  <PhaseAccordion
                    phase={phase}
                    expanded={expandedPhase === meta.key}
                    variableSamples={variableSamples}
                    filters={filters}
                    forceExpand={forceExpand}
                    onCopy={(text, label) => void handleCopy(text, label)}
                    onToggle={() =>
                      setExpandedPhase((cur) => (cur === meta.key ? null : meta.key))
                    }
                  />
                </div>
              );
            })}
          </div>
        </>
      ) : null}
    </div>
  );
}
