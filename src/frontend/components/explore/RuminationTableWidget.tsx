'use client';

import { useState, useCallback, useEffect } from 'react';

export interface RuminationTableColumn {
  key: string;
  label: string;
  /** 下拉选项；无则使用文本输入 */
  options?: string[];
}

export interface RuminationTablePayload {
  columns: RuminationTableColumn[];
  rows: Record<string, unknown>[];
  editableCols: string[];
  /** 可选：引导语 */
  guideText?: string;
  /** 可选：步骤标识 */
  step?: number;
  singleRowMode?: boolean;
  rowCursor?: number;
  totalRows?: number;
}

interface RuminationTableWidgetProps {
  payload: RuminationTablePayload;
  onConfirm: (rows: Record<string, unknown>[]) => void;
  disabled?: boolean;
  className?: string;
  /** glass：毛玻璃左栏内嵌，表头 Confirm 使用黑色圆角按钮 */
  uiVariant?: 'default' | 'glass';
  /** glass 时卡片标题（由页面传入 i18n 文案） */
  cardTitle?: string;
  /** 主按钮文案（i18n） */
  confirmLabel?: string;
  refillLabel?: string;
  /** true：主按钮变为「重新填写」，点击走 onRefill（恢复该步 initial 表） */
  tableRefillMode?: boolean;
  onRefill?: () => void;
}

export default function RuminationTableWidget({
  payload,
  onConfirm,
  disabled = false,
  className = '',
  uiVariant = 'default',
  cardTitle,
  confirmLabel = '确认',
  refillLabel = '重新填写',
  tableRefillMode = false,
  onRefill,
}: RuminationTableWidgetProps) {
  const [rows, setRows] = useState<Record<string, unknown>[]>(
    () => JSON.parse(JSON.stringify(payload.rows)) || []
  );

  useEffect(() => {
    setRows(JSON.parse(JSON.stringify(payload.rows)) || []);
  }, [
    payload.step,
    payload.rowCursor,
    payload.totalRows,
    JSON.stringify(payload.rows),
  ]);

  const editableSet = new Set(payload.editableCols || []);

  const handleCellChange = useCallback((rowIdx: number, colKey: string, value: unknown) => {
    setRows((prev) => {
      const next = [...prev];
      if (rowIdx < 0 || rowIdx >= next.length) return prev;
      next[rowIdx] = { ...next[rowIdx], [colKey]: value };
      return next;
    });
  }, []);

  const handleConfirm = useCallback(() => {
    onConfirm(rows);
  }, [rows, onConfirm]);

  if (!payload.columns?.length) return null;

  const isGlass = uiVariant === 'glass';

  const primaryBtn = tableRefillMode ? (
    <button
      type="button"
      onClick={() => onRefill?.()}
      disabled={disabled || !onRefill}
      className={
        isGlass
          ? 'bd-btn-black shrink-0 rounded-full px-4 py-2 text-sm font-medium text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed'
          : 'rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50'
      }
    >
      {refillLabel}
    </button>
  ) : (
    <button
      type="button"
      onClick={handleConfirm}
      disabled={disabled}
      className={
        isGlass
          ? 'bd-btn-black shrink-0 rounded-full px-4 py-2 text-sm font-medium text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed'
          : 'rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50'
      }
    >
      {confirmLabel}
    </button>
  );

  const tableBlock = (
    <div
      className={
        isGlass
          ? 'rumination-beautiful-table-scroll rumination-beautiful-table-widget overflow-x-auto overflow-y-auto max-h-[min(52vh,520px)] rounded-xl border border-neutral-200/80 bg-white/40'
          : 'overflow-x-auto overflow-y-auto max-h-[320px] rounded-lg border border-neutral-100'
      }
    >
      <table className="min-w-full text-sm border-collapse">
        <thead>
          <tr className={isGlass ? 'bg-white/50' : 'bg-neutral-50'}>
            {payload.columns.map((col) => (
              <th
                key={col.key}
                className={
                  isGlass
                    ? 'px-3 py-3 text-left font-medium text-neutral-500 whitespace-nowrap border-b border-neutral-200/90 text-[0.65rem] uppercase tracking-wide'
                    : 'px-3 py-2 text-left font-medium text-neutral-700 whitespace-nowrap border-b border-neutral-200'
                }
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className={
                isGlass
                  ? 'border-b border-neutral-100/90 last:border-b-0 hover:bg-white/35'
                  : 'border-b border-neutral-100 hover:bg-neutral-50/50'
              }
            >
              {payload.columns.map((col) => {
                const isEditable = editableSet.has(col.key);
                const val = row[col.key];
                const strVal = val != null ? String(val) : '';

                return (
                  <td key={col.key} className={isGlass ? 'px-3 py-3 text-neutral-700' : 'px-3 py-2'}>
                    {isEditable && col.options?.length ? (
                      <select
                        value={strVal}
                        onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                        disabled={disabled}
                        className={
                          isGlass
                            ? 'w-full min-w-[120px] px-2 py-1.5 text-sm border border-neutral-200/90 rounded-lg bg-white/80 focus:ring-2 focus:ring-neutral-300 focus:border-neutral-400'
                            : 'w-full min-w-[120px] px-2 py-1 text-sm border border-neutral-200 rounded-md bg-white focus:ring-2 focus:ring-violet-300 focus:border-violet-400'
                        }
                      >
                        <option value="">请选择</option>
                        {col.options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : isEditable ? (
                      <input
                        type="text"
                        value={strVal}
                        onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                        disabled={disabled}
                        placeholder="填写"
                        className={
                          isGlass
                            ? 'w-full min-w-[100px] px-2 py-1.5 text-sm border border-neutral-200/90 rounded-lg bg-white/80 focus:ring-2 focus:ring-neutral-300'
                            : 'w-full min-w-[100px] px-2 py-1 text-sm border border-neutral-200 rounded-md focus:ring-2 focus:ring-violet-300 focus:border-violet-400'
                        }
                      />
                    ) : (
                      <span className="text-neutral-700">{strVal || '—'}</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  if (isGlass) {
    return (
      <div className={`flex flex-1 flex-col min-h-0 ${className}`}>
        <div className="mb-4 flex shrink-0 items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-bd-fg truncate">
            {cardTitle ?? '表格'}
          </h2>
          {primaryBtn}
        </div>
        {payload.guideText && (
          <p className="mb-3 shrink-0 text-sm leading-relaxed text-neutral-600">{payload.guideText}</p>
        )}
        <div className="min-h-0 flex-1">{tableBlock}</div>
      </div>
    );
  }

  return (
    <div
      className={`rumination-table-widget rounded-xl border border-neutral-200 bg-white/90 p-4 ${className}`}
    >
      {payload.guideText && (
        <p className="text-sm text-neutral-600 mb-3">{payload.guideText}</p>
      )}
      {tableBlock}
      <div className="mt-3 flex justify-end">{primaryBtn}</div>
    </div>
  );
}
