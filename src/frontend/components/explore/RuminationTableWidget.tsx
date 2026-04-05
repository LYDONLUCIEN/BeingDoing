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
  selectPlaceholder?: string;
  inputPlaceholder?: string;
  /** 提交表格时遮罩文案 */
  loadingLabel?: string;
  submitting?: boolean;
  /** 选中行摘要，用于输入框上下文 */
  onRowContextChange?: (ctx: { rowIndex: number; label: string } | null) => void;
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
  selectPlaceholder = '请选择',
  inputPlaceholder = '填写',
  loadingLabel = '…',
  submitting = false,
  onRowContextChange,
}: RuminationTableWidgetProps) {
  const [rows, setRows] = useState<Record<string, unknown>[]>(
    () => JSON.parse(JSON.stringify(payload.rows)) || []
  );
  /** glass：当前高亮行；null 表示未选中（再点同一行可取消） */
  const [selectedRowIdx, setSelectedRowIdx] = useState<number | null>(0);

  const rowsPayloadSig = JSON.stringify(payload.rows ?? []);
  useEffect(() => {
    try {
      setRows(JSON.parse(rowsPayloadSig) || []);
    } catch {
      setRows([]);
    }
  }, [rowsPayloadSig]);

  // 仅随子步、游标、行数变化重置选中；不依赖 payload.rows 引用以免编辑单元格时误重置高亮
  useEffect(() => {
    const n = (payload.rows ?? []).length;
    const c = payload.rowCursor ?? 0;
    if (n <= 0) {
      setSelectedRowIdx(null);
      return;
    }
    setSelectedRowIdx(Math.min(Math.max(0, c), n - 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 故意不依赖 payload.rows 全文
  }, [payload.step, payload.rowCursor, payload.totalRows, payload.rows?.length]);

  const handleGlassRowActivate = useCallback((rowIdx: number) => {
    setSelectedRowIdx((prev) => (prev === rowIdx ? null : rowIdx));
  }, []);

  useEffect(() => {
    if (!onRowContextChange) return;
    if (selectedRowIdx == null || selectedRowIdx < 0) {
      onRowContextChange(null);
      return;
    }
    const row = rows[selectedRowIdx];
    if (!row || !payload.columns?.length) {
      onRowContextChange(null);
      return;
    }
    const bits = payload.columns
      .slice(0, 3)
      .map((c) => String(row[c.key] ?? '').trim())
      .filter(Boolean);
    const label = bits.join(' · ') || `${selectedRowIdx + 1}`;
    onRowContextChange({ rowIndex: selectedRowIdx, label });
  }, [selectedRowIdx, rows, payload.columns, onRowContextChange]);

  const editableSet = new Set(payload.editableCols || []);

  const colMinWidth = (col: RuminationTableColumn) =>
    Math.min(320, Math.max(112, 12 + (col.label?.length ?? 0) * 14));

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

  const selectArrowSvg =
    'url("data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2220%22 height=%2220%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%236b7280%22 stroke-width=%222%22%3E%3Cpolyline points=%226 9 12 15 18 9%22/%3E%3C/svg%3E")';

  const tableBlock = (
    <div
      className={
        isGlass
          ? 'rumination-beautiful-table-scroll rumination-beautiful-table-widget relative overflow-x-auto overflow-y-auto max-h-[min(52vh,520px)] rounded-xl border border-neutral-300/50 bg-white/25 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]'
          : 'relative overflow-x-auto overflow-y-auto max-h-[320px] rounded-lg border border-neutral-100'
      }
    >
      {isGlass && submitting && (
        <div
          className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-xl bg-white/35 backdrop-blur-[24px]"
          aria-live="polite"
          aria-busy="true"
        >
          <span className="rounded-full bg-white/80 px-4 py-2 text-sm font-medium text-neutral-700 shadow-sm">
            {loadingLabel}
          </span>
        </div>
      )}
      <table className="w-max min-w-full text-sm border-separate border-spacing-0 table-auto">
        <thead className={isGlass ? 'sticky top-0 z-10' : ''}>
          <tr className={isGlass ? 'bg-white/55 backdrop-blur-md' : 'bg-neutral-50'}>
            {payload.columns.map((col) => (
              <th
                key={col.key}
                style={{ minWidth: colMinWidth(col) }}
                className={
                  isGlass
                    ? 'px-3 py-3 text-left font-medium text-neutral-600 whitespace-nowrap border-b border-neutral-300/70 text-[0.65rem] uppercase tracking-[0.06em] align-top'
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
              role={isGlass ? 'button' : undefined}
              tabIndex={isGlass ? 0 : undefined}
              onClick={() => isGlass && handleGlassRowActivate(rowIdx)}
              onKeyDown={(e) => {
                if (!isGlass) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleGlassRowActivate(rowIdx);
                }
              }}
              className={
                isGlass
                  ? `border-b border-neutral-200/80 transition-colors last:border-b-0 outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 focus-visible:ring-inset ${
                      selectedRowIdx === rowIdx
                        ? 'bg-[#E8DFFE]/90 text-[#5b21b6] shadow-[inset_3px_0_0_0_#7c3aed]'
                        : 'hover:bg-white/30'
                    } cursor-pointer`
                  : 'border-b border-neutral-100 hover:bg-neutral-50/50'
              }
            >
              {payload.columns.map((col) => {
                const isEditable = editableSet.has(col.key);
                const val = row[col.key];
                const strVal = val != null ? String(val) : '';

                return (
                  <td
                    key={col.key}
                    style={{ minWidth: colMinWidth(col) }}
                    className={
                      isGlass
                        ? 'px-3 py-3 align-top text-neutral-700 break-words whitespace-normal'
                        : 'px-3 py-2'
                    }
                  >
                    {isEditable && col.options?.length ? (
                      <select
                        value={strVal}
                        onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                        onMouseDown={(e) => isGlass && e.stopPropagation()}
                        onClick={(e) => isGlass && e.stopPropagation()}
                        disabled={disabled}
                        className={
                          isGlass
                            ? 'rumination-glass-select w-full min-w-[120px] appearance-none px-2 py-1.5 pr-8 text-sm border border-neutral-200/90 rounded-lg bg-white/80 focus:ring-2 focus:ring-violet-300/40 focus:border-violet-400/60'
                            : 'w-full min-w-[120px] px-2 py-1 text-sm border border-neutral-200 rounded-md bg-white focus:ring-2 focus:ring-violet-300 focus:border-violet-400'
                        }
                        style={
                          isGlass
                            ? {
                                backgroundImage: selectArrowSvg,
                                backgroundRepeat: 'no-repeat',
                                backgroundPosition: 'right 0.45rem center',
                                backgroundSize: '14px',
                              }
                            : undefined
                        }
                      >
                        <option value="">{selectPlaceholder}</option>
                        {col.options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : isEditable ? (
                      isGlass ? (
                        <textarea
                          value={strVal}
                          onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                          onMouseDown={(e) => isGlass && e.stopPropagation()}
                          onClick={(e) => isGlass && e.stopPropagation()}
                          disabled={disabled}
                          placeholder={inputPlaceholder}
                          rows={2}
                          className="w-full min-h-[2.75rem] min-w-[100px] resize-y px-2 py-1.5 text-sm leading-snug border border-neutral-200/90 rounded-lg bg-white/80 focus:ring-2 focus:ring-violet-300/40 break-words whitespace-pre-wrap"
                        />
                      ) : (
                        <input
                          type="text"
                          value={strVal}
                          onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                          onMouseDown={(e) => isGlass && e.stopPropagation()}
                          onClick={(e) => isGlass && e.stopPropagation()}
                          disabled={disabled}
                          placeholder={inputPlaceholder}
                          className="w-full min-w-[100px] px-2 py-1 text-sm border border-neutral-200 rounded-md focus:ring-2 focus:ring-violet-300 focus:border-violet-400"
                        />
                      )
                    ) : (
                      <span className="text-neutral-700 break-words whitespace-pre-wrap">
                        {strVal || '—'}
                      </span>
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
