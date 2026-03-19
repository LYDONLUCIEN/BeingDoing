'use client';

import { useState, useCallback } from 'react';

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
}

interface RuminationTableWidgetProps {
  payload: RuminationTablePayload;
  onConfirm: (rows: Record<string, unknown>[]) => void;
  disabled?: boolean;
  className?: string;
}

export default function RuminationTableWidget({
  payload,
  onConfirm,
  disabled = false,
  className = '',
}: RuminationTableWidgetProps) {
  const [rows, setRows] = useState<Record<string, unknown>[]>(
    () => JSON.parse(JSON.stringify(payload.rows)) || []
  );
  const editableSet = new Set(payload.editableCols || []);
  const colMap = new Map(payload.columns.map((c) => [c.key, c]));

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

  return (
    <div
      className={`rumination-table-widget rounded-xl border border-neutral-200 bg-white/90 p-4 ${className}`}
    >
      {payload.guideText && (
        <p className="text-sm text-neutral-600 mb-3">{payload.guideText}</p>
      )}
      <div className="overflow-x-auto overflow-y-auto max-h-[320px] rounded-lg border border-neutral-100">
        <table className="min-w-full text-sm border-collapse">
          <thead>
            <tr className="bg-neutral-50">
              {payload.columns.map((col) => (
                <th
                  key={col.key}
                  className="px-3 py-2 text-left font-medium text-neutral-700 whitespace-nowrap border-b border-neutral-200"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => (
              <tr key={rowIdx} className="border-b border-neutral-100 hover:bg-neutral-50/50">
                {payload.columns.map((col) => {
                  const isEditable = editableSet.has(col.key);
                  const val = row[col.key];
                  const strVal = val != null ? String(val) : '';

                  return (
                    <td key={col.key} className="px-3 py-2">
                      {isEditable && col.options?.length ? (
                        <select
                          value={strVal}
                          onChange={(e) =>
                            handleCellChange(rowIdx, col.key, e.target.value)
                          }
                          disabled={disabled}
                          className="w-full min-w-[120px] px-2 py-1 text-sm border border-neutral-200 rounded-md bg-white focus:ring-2 focus:ring-violet-300 focus:border-violet-400"
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
                          onChange={(e) =>
                            handleCellChange(rowIdx, col.key, e.target.value)
                          }
                          disabled={disabled}
                          placeholder="填写"
                          className="w-full min-w-[100px] px-2 py-1 text-sm border border-neutral-200 rounded-md focus:ring-2 focus:ring-violet-300 focus:border-violet-400"
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
      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={disabled}
          className="px-4 py-2 text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors"
        >
          确认
        </button>
      </div>
    </div>
  );
}
