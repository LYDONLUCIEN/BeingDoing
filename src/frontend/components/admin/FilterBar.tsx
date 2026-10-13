'use client';

import { useEffect, useRef, useState } from 'react';
import type { FilterSchemaEntry, FilterValues } from '@/lib/api/admin';

interface FilterBarProps {
  /** 后端下发的过滤器 schema（GET /admin/filters/schema，数组序即展示序） */
  schema: FilterSchemaEntry[];
  /** 当前筛选值：key → 多选数组 / 单选或关键词字符串 / 日期区间对象 */
  values: FilterValues;
  /** 值变更回调（空值 key 已在本组件剔除；父组件通常顺带重置分页） */
  onChange: (next: FilterValues) => void;
  className?: string;
}

/** 与 admin 各页筛选控件同款的原生控件样式（users / data-export 页既有口径） */
const CONTROL_CLASS =
  'px-3 py-2 rounded-lg text-sm border outline-none focus:ring-2 focus:ring-bd-ui-accent/30';
const CONTROL_STYLE = {
  background: 'var(--bd-overlay-md, #fff)',
  borderColor: 'var(--bd-border)',
  color: 'var(--bd-fg)',
};

/**
 * 多选下拉面板（multi_enum 用，2026-10-13）。
 * 按钮态显示「标签（已选数）」；点开为 checkbox 列表面板，支持多选；
 * 点击面板外或按 Escape 关闭。全不勾 = 不限（删除该 key）。
 */
function MultiSelectDropdown({
  label,
  options,
  selected,
  onToggle,
  onClear,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (value: string, checked: boolean) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // 点击面板外 / Escape 关闭
  useEffect(() => {
    if (!open) return;
    const onDocDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const selectedLabels = options
    .filter((o) => selected.includes(o.value))
    .map((o) => o.label)
    .join('、');

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`${CONTROL_CLASS} flex items-center gap-1.5 whitespace-nowrap`}
        style={CONTROL_STYLE}
        title={selectedLabels || `全部${label}`}
      >
        <span style={{ color: 'var(--bd-fg-muted)' }}>{label}</span>
        {selected.length > 0 && (
          <span
            className="px-1.5 py-0.5 rounded-full text-xs font-medium leading-none"
            style={{ background: 'rgba(59,130,246,0.14)', color: '#2563eb' }}
          >
            {selected.length}
          </span>
        )}
        <span className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
          {open ? '▴' : '▾'}
        </span>
      </button>
      {open && (
        <div
          className="absolute z-30 mt-1 min-w-[10rem] max-h-64 overflow-y-auto rounded-xl border p-2 space-y-1 shadow-lg"
          style={{
            background: 'var(--bd-card, #fff)',
            borderColor: 'var(--bd-border)',
          }}
        >
          {options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm cursor-pointer hover:opacity-70"
              style={{ color: 'var(--bd-fg)' }}
            >
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                onChange={(e) => onToggle(opt.value, e.target.checked)}
              />
              {opt.label}
            </label>
          ))}
          {selected.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="w-full text-left px-2 py-1.5 rounded-lg text-xs hover:opacity-70"
              style={{ color: 'var(--bd-fg-muted)' }}
            >
              清空选择
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * 通用用户筛选条（ADR-0023）。
 * 按 schema 声明顺序渲染，类型映射：
 * - text       → 原生 input（受控，placeholder 用 label）
 * - enum       → 原生 select，第一项「全部」（value=''，选中即从 values 删除该 key）
 * - multi_enum → 自定义多选下拉面板（MultiSelectDropdown，全不勾即删除该 key）
 * - date_range → 两个原生 input[type=date]（两端皆空即删除该 key）
 *
 * 布局（2026-10-13）：flex-wrap 自然换行，超宽即折到下一行，不再横向滚动；
 * 下方数据表格的横向滚动由各页面表格容器自行承担（overflow-x-auto）。
 */
export function FilterBar({ schema, values, onChange, className }: FilterBarProps) {
  /** 写入单个 key；value 为 undefined 时删除该 key（空值 = 不限） */
  const setValue = (key: string, value: FilterValues[string]) => {
    const next: FilterValues = { ...values };
    if (value === undefined) {
      delete next[key];
    } else {
      next[key] = value;
    }
    onChange(next);
  };

  return (
    <div className={`flex flex-wrap items-center gap-3 ${className ?? ''}`}>
      {schema.map((entry) => {
        switch (entry.type) {
          case 'text': {
            const raw = values[entry.key];
            const text = typeof raw === 'string' ? raw : '';
            return (
              <input
                key={entry.key}
                type="text"
                placeholder={entry.key === 'q' ? `${entry.label}：邮箱/昵称` : entry.label}
                value={text}
                onChange={(e) =>
                  // 纯空白视为清空（后端对 text 过滤器要求非空字符串）
                  setValue(entry.key, e.target.value.trim() ? e.target.value : undefined)
                }
                className={`${CONTROL_CLASS} w-56`}
                style={CONTROL_STYLE}
              />
            );
          }
          case 'enum': {
            const raw = values[entry.key];
            const current = typeof raw === 'string' ? raw : '';
            return (
              <select
                key={entry.key}
                value={current}
                onChange={(e) => setValue(entry.key, e.target.value || undefined)}
                className={CONTROL_CLASS}
                style={CONTROL_STYLE}
              >
                <option value="">全部{entry.label}</option>
                {(entry.options ?? []).map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            );
          }
          case 'multi_enum': {
            const raw = values[entry.key];
            const current = Array.isArray(raw) ? raw : [];
            const toggle = (v: string, checked: boolean) => {
              const nextArr = checked ? [...current, v] : current.filter((x) => x !== v);
              // 全不勾 = 不限，删除该 key
              setValue(entry.key, nextArr.length > 0 ? nextArr : undefined);
            };
            return (
              <MultiSelectDropdown
                key={entry.key}
                label={entry.label}
                options={entry.options ?? []}
                selected={current}
                onToggle={toggle}
                onClear={() => setValue(entry.key, undefined)}
              />
            );
          }
          case 'date_range': {
            const raw = values[entry.key];
            const range =
              raw && typeof raw === 'object' && !Array.isArray(raw)
                ? (raw as { after?: string; before?: string })
                : {};
            const updateRange = (side: 'after' | 'before', v: string) => {
              const nextRange = { ...range, [side]: v };
              // 两端皆空 = 不限，删除该 key
              if (!nextRange.after && !nextRange.before) {
                setValue(entry.key, undefined);
              } else {
                setValue(entry.key, nextRange);
              }
            };
            return (
              // 日期区间作为整体换行（内部不折行）
              <div key={entry.key} className="flex flex-nowrap items-center gap-2 whitespace-nowrap">
                <span className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                  {entry.label}
                </span>
                <input
                  type="date"
                  value={range.after ?? ''}
                  onChange={(e) => updateRange('after', e.target.value)}
                  className={CONTROL_CLASS}
                  style={CONTROL_STYLE}
                />
                <span className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                  至
                </span>
                <input
                  type="date"
                  value={range.before ?? ''}
                  onChange={(e) => updateRange('before', e.target.value)}
                  className={CONTROL_CLASS}
                  style={CONTROL_STYLE}
                />
              </div>
            );
          }
          default:
            // 未知类型静默跳过（后端新增类型时前端不炸，下次迭代补映射）
            return null;
        }
      })}
      <button
        onClick={() => onChange({})}
        className="px-3 py-2 rounded-lg text-sm border hover:opacity-80 transition-opacity"
        style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg-muted)' }}
      >
        重置
      </button>
    </div>
  );
}
