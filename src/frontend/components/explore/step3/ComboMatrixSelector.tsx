'use client';

import { useMemo } from 'react';
import { Check, SkipForward } from 'lucide-react';
import type { ComboItem } from '@/lib/api/rumination';

interface ComboMatrixSelectorProps {
  matrix: ComboItem[];
  conclusions: Record<string, { text: string; state: string }> | undefined;
  selectedComboId: string | null;
  onSelectCombo: (comboId: string) => void;
}

/** Flow diagram showing passion × strength combos with relationship visualization */
export default function ComboMatrixFlowDiagram({
  matrix,
  conclusions,
  selectedComboId,
  onSelectCombo,
}: ComboMatrixSelectorProps) {
  const completedCount = useMemo(() => {
    let c = 0;
    for (const item of matrix) {
      const state = conclusions?.[item.combo_id]?.state;
      if (state === 'confirmed' || state === 'skipped') c++;
    }
    return c;
  }, [matrix, conclusions]);

  // Group by passion
  const passionGroups = useMemo(() => {
    const groups: Map<number, ComboItem[]> = new Map();
    for (const item of matrix) {
      const list = groups.get(item.passion_idx) || [];
      list.push(item);
      groups.set(item.passion_idx, list);
    }
    return Array.from(groups.entries()).sort(([a], [b]) => a - b);
  }, [matrix]);

  return (
    <div className="flex flex-col gap-3">
      {/* Per-passion group */}
      {passionGroups.map(([pIdx, combos]) => {
        const passionName = combos[0]?.passion_name || `热爱${pIdx + 1}`;
        return (
          <div key={pIdx} className="flex flex-col gap-1.5">
            {/* Passion section header */}
            <div className="text-xs font-medium text-gray-400 px-0.5">
              {passionName}
            </div>

            {/* Combo cards under this passion */}
            {combos.map((combo) => {
              const state = conclusions?.[combo.combo_id]?.state || 'empty';
              const isSelected = combo.combo_id === selectedComboId;

              return (
                <button
                  key={combo.combo_id}
                  onClick={() => onSelectCombo(combo.combo_id)}
                  className={`
                    flex items-center gap-2 px-3 py-2 rounded-xl border transition-all text-left
                    ${isSelected
                      ? 'border-teal-400 bg-teal-50/60 shadow-sm ring-1 ring-teal-200/80'
                      : 'border-gray-200/60 bg-white/60 hover:border-teal-200 hover:bg-teal-50/30'}
                  `}
                >
                  {/* Passion label */}
                  <span className="text-xs font-medium text-teal-700 bg-teal-100/80 px-2 py-0.5 rounded-full whitespace-nowrap">
                    {combo.passion_name}
                  </span>

                  {/* Cross symbol */}
                  <span className="text-gray-300 font-light text-sm leading-none">×</span>

                  {/* Strength label */}
                  <span className="text-xs font-medium text-teal-700 bg-teal-100/80 px-2 py-0.5 rounded-full whitespace-nowrap">
                    {combo.strength_name}
                  </span>

                  {/* Spacer */}
                  <div className="flex-1 min-w-0" />

                  {/* Status icon */}
                  {state === 'confirmed' && (
                    <div className="flex items-center gap-0.5">
                      <span className="text-xs text-teal-600 truncate max-w-[80px]">
                        {conclusions?.[combo.combo_id]?.text.slice(0, 8)}
                        {(conclusions?.[combo.combo_id]?.text.length ?? 0) > 8 ? '...' : ''}
                      </span>
                      <Check size={14} className="text-teal-500 shrink-0" />
                    </div>
                  )}
                  {state === 'skipped' && (
                    <SkipForward size={14} className="text-gray-400 shrink-0" />
                  )}
                  {state === 'empty' && (
                    <div className="w-3.5 h-3.5 rounded-full border border-gray-300/80 shrink-0" />
                  )}
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

/** Compact combo grid (kept for backward compat, unused in matrix mode) */
export function ComboGrid({
  matrix,
  conclusions,
  selectedComboId,
  onSelectCombo,
}: ComboMatrixSelectorProps) {
  const completedCount = useMemo(() => {
    let c = 0;
    for (const item of matrix) {
      const state = conclusions?.[item.combo_id]?.state;
      if (state === 'confirmed' || state === 'skipped') c++;
    }
    return c;
  }, [matrix, conclusions]);

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-gray-500">
        已完成 {completedCount}/{matrix.length} 个组合
      </div>

      <div className="grid gap-1.5" style={{ gridTemplateColumns: '80px repeat(5, 1fr)' }}>
        <div />
        {matrix
          .filter((m) => m.passion_idx === 0)
          .map((m) => (
            <div key={m.strength_idx} className="text-xs text-center text-gray-400 truncate px-0.5">
              {m.strength_name.slice(0, 4)}
            </div>
          ))}

        {Array.from(new Set(matrix.map((m) => m.passion_idx)))
          .sort((a, b) => a - b)
          .map((pIdx) => {
            const passionItem = matrix.find((m) => m.passion_idx === pIdx);
            return (
              <div key={pIdx}>
                <div className="flex items-center text-xs text-gray-600 truncate pr-1">
                  {passionItem?.passion_name.slice(0, 4)}
                </div>

                {Array.from(new Set(matrix.map((m) => m.strength_idx)))
                  .sort((a, b) => a - b)
                  .map((sIdx) => {
                    const item = matrix.find((m) => m.passion_idx === pIdx && m.strength_idx === sIdx);
                    if (!item) return <div key={sIdx} />;
                    const state = conclusions?.[item.combo_id]?.state || 'empty';
                    const isSelected = item.combo_id === selectedComboId;
                    const statusStyles: Record<string, string> = {
                      empty: 'border-gray-300 bg-white hover:border-teal-300 hover:bg-teal-50',
                      confirmed: 'border-teal-400 bg-teal-50 text-teal-800',
                      skipped: 'border-gray-300 bg-gray-100 text-gray-400 line-through',
                    };
                    return (
                      <button
                        key={item.combo_id}
                        onClick={() => onSelectCombo(item.combo_id)}
                        className={`relative flex items-center justify-center rounded-md px-1 py-1.5 text-xs border transition-all ${
                          isSelected
                            ? 'border-teal-500 bg-teal-100 shadow-sm ring-1 ring-teal-300'
                            : statusStyles[state]
                        } ${state === 'skipped' ? 'cursor-default' : 'cursor-pointer hover:shadow-sm'}`}
                      >
                        {state === 'confirmed' && (
                          <Check size={10} className="absolute top-0 right-0 text-teal-500" />
                        )}
                        {state === 'skipped' && (
                          <SkipForward size={10} className="absolute top-0 right-0 text-gray-400" />
                        )}
                        <span className={state === 'skipped' ? 'line-through' : ''}>
                          {pIdx}
                          {sIdx}
                        </span>
                      </button>
                    );
                  })}
              </div>
            );
          })}
      </div>
    </div>
  );
}
