import type {
  PromptCatalogData,
  PromptCatalogLayer,
  PromptCatalogPhase,
  PromptCatalogSection,
} from '@/lib/api/admin';
import type { PhaseKey } from '@/lib/explore/session';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

export const CATEGORY_LABELS: Record<string, string> = {
  intro: '引导语',
  main: '主对话',
  fallback: '兜底',
  runtime: 'runtime',
  addon: 'addon',
  outro: '结束语',
};

export interface CatalogFilterState {
  searchQuery: string;
  phaseFilter: PhaseKey | 'all';
  categoryFilter: string;
  tagFilter: string;
}

export function defaultCatalogFilters(): CatalogFilterState {
  return {
    searchQuery: '',
    phaseFilter: 'all',
    categoryFilter: 'all',
    tagFilter: 'all',
  };
}

function collectSectionText(section: PromptCatalogSection): string {
  const parts: string[] = [section.label, section.key, section.category, section.content || ''];
  if (section.segments?.length) {
    parts.push(...section.segments.map((s) => s.content || s.name || ''));
  }
  if (section.layer_stack?.length) {
    section.layer_stack.forEach((layer) => {
      parts.push(layer.label, layer.id, layer.category || '', layer.content || '');
      layer.segments?.forEach((s) => parts.push(s.content || s.name || ''));
      layer.nested_conditions?.forEach((c) => parts.push(c.condition, c.content));
    });
  }
  section.items?.forEach((item) => {
    parts.push(item.label || '', item.role, item.content || '');
    item.segments?.forEach((s) => parts.push(s.content || s.name || ''));
  });
  return parts.filter(Boolean).join('\n');
}

export function sectionMatchesFilters(
  section: PromptCatalogSection,
  phaseKey: string,
  filters: CatalogFilterState,
): boolean {
  if (filters.phaseFilter !== 'all' && phaseKey !== filters.phaseFilter) {
    return false;
  }
  if (filters.categoryFilter !== 'all' && section.category !== filters.categoryFilter) {
    return false;
  }
  if (filters.tagFilter !== 'all' && section.key !== filters.tagFilter) {
    const layerHit = section.layer_stack?.some((l) => l.id === filters.tagFilter);
    if (!layerHit) return false;
  }
  const q = filters.searchQuery.trim().toLowerCase();
  if (!q) return true;
  return collectSectionText(section).toLowerCase().includes(q);
}

export function phaseHasVisibleContent(phase: PromptCatalogPhase, filters: CatalogFilterState): boolean {
  const mainHit = phase.sections.some((sec) => sectionMatchesFilters(sec, phase.key, filters));
  if (mainHit) return true;
  if (!phase.rumination_steps?.length) return false;
  return phase.rumination_steps.some((rs) =>
    rs.sections.some((sec) => sectionMatchesFilters(sec, 'rumination', filters)),
  );
}

export function collectCatalogTags(catalog: PromptCatalogData): string[] {
  const tags = new Set<string>();
  catalog.phases.forEach((phase) => {
    phase.sections.forEach((sec) => {
      tags.add(sec.key);
      sec.layer_stack?.forEach((l) => tags.add(l.id));
    });
    phase.rumination_steps?.forEach((rs) => {
      rs.sections.forEach((sec) => {
        tags.add(sec.key);
        sec.layer_stack?.forEach((l) => tags.add(l.id));
      });
    });
  });
  return Array.from(tags).sort();
}

export function collectCatalogCategories(catalog: PromptCatalogData): string[] {
  const cats = new Set<string>();
  const walk = (sections: PromptCatalogSection[]) => {
    sections.forEach((sec) => {
      if (sec.category) cats.add(sec.category);
      sec.layer_stack?.forEach((l) => {
        if (l.category) cats.add(l.category);
      });
    });
  };
  catalog.phases.forEach((p) => {
    walk(p.sections);
    p.rumination_steps?.forEach((rs) => walk(rs.sections));
  });
  return Array.from(cats).sort();
}

export function extractLayerCopyText(
  layer: PromptCatalogLayer,
  variableSamples?: Record<string, string>,
): string {
  if (layer.content) return layer.content;
  if (layer.segments?.length) {
    return layer.segments
      .map((s) => (s.type === 'variable' ? variableSamples?.[s.name || ''] || s.raw || `{{ ${s.name} }}` : s.content || ''))
      .join('');
  }
  return '';
}

export function extractSectionCopyText(
  section: PromptCatalogSection,
  variableSamples?: Record<string, string>,
): string {
  if (section.layer_stack?.length) {
    return section.layer_stack.map((l) => extractLayerCopyText(l, variableSamples)).filter(Boolean).join('\n\n');
  }
  if (section.items?.length) {
    return section.items
      .map((item) => item.content || item.segments?.map((s) => s.content || '').join('') || '')
      .filter(Boolean)
      .join('\n\n');
  }
  return section.content || section.segments?.map((s) => s.content || '').join('') || '';
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function formatAdminTime(iso?: string | null): string {
  if (!iso) return '—';
  // 委托 formatLocalDateTime，确保 tz-aware 字符串按浏览器本地时区显示
  // （历史 naive 数据在 toDate 内部会补 'Z' 视作 UTC）
  const formatted = formatLocalDateTime(iso);
  // 若解析失败，toDate 返回占位符 '-'，这里回退到原值便于排查
  return formatted === '-' ? iso : formatted;
}
