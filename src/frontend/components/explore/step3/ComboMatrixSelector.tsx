'use client';

import { useMemo, useState, useEffect } from 'react';
import { Check, SkipForward } from 'lucide-react';
import type { ComboItem } from '@/lib/api/rumination';

interface ComboMatrixSelectorProps {
  matrix: ComboItem[];
  conclusions: Record<string, { text: string; state: string }> | undefined;
  selectedComboId: string | null;
  onSelectCombo: (comboId: string) => void;
}

/**
 * Button selector matching the reference HTML design:
 * Left column = 3 passion buttons (orange theme), right column = 5 strength buttons (green theme).
 * Selecting one of each forms a combo_id and fires onSelectCombo.
 * Bottom shows two summary cards (one per selection).
 */
export default function ComboMatrixFlowDiagram({
  matrix,
  conclusions,
  selectedComboId,
  onSelectCombo,
}: ComboMatrixSelectorProps) {
  // Unique passions and strengths (preserving order)
  const passions = useMemo(() => {
    const seen = new Map<number, string>();
    for (const m of matrix) {
      if (!seen.has(m.passion_idx)) seen.set(m.passion_idx, m.passion_name);
    }
    return Array.from(seen.entries())
      .sort(([a], [b]) => a - b)
      .map(([, name]) => name);
  }, [matrix]);

  const strengths = useMemo(() => {
    const seen = new Map<number, string>();
    for (const m of matrix) {
      if (!seen.has(m.strength_idx)) seen.set(m.strength_idx, m.strength_name);
    }
    return Array.from(seen.entries())
      .sort(([a], [b]) => a - b)
      .map(([, name]) => name);
  }, [matrix]);

  // Internal state: which passion / strength is selected
  const [selPassionName, setSelPassionName] = useState<string | null>(null);
  const [selStrengthName, setSelStrengthName] = useState<string | null>(null);

  // Sync from parent selectedComboId → derive passion/strength names
  useEffect(() => {
    if (selectedComboId) {
      const combo = matrix.find((m) => m.combo_id === selectedComboId);
      if (combo) {
        setSelPassionName(combo.passion_name);
        setSelStrengthName(combo.strength_name);
      }
    }
  }, [selectedComboId, matrix]);

  // When both selected, fire onSelectCombo
  useEffect(() => {
    if (selPassionName && selStrengthName) {
      const combo = matrix.find(
        (m) => m.passion_name === selPassionName && m.strength_name === selStrengthName,
      );
      if (combo && combo.combo_id !== selectedComboId) {
        onSelectCombo(combo.combo_id);
      }
    }
  }, [selPassionName, selStrengthName, matrix, onSelectCombo, selectedComboId]);

  // For each passion, check if ALL combos under it are confirmed/skipped
  const passionDone = useMemo(() => {
    const map = new Map<string, boolean>();
    for (const p of passions) {
      const combos = matrix.filter((m) => m.passion_name === p);
      map.set(
        p,
        combos.every(
          (c) =>
            conclusions?.[c.combo_id]?.state === 'confirmed' ||
            conclusions?.[c.combo_id]?.state === 'skipped',
        ),
      );
    }
    return map;
  }, [passions, matrix, conclusions]);

  // For each strength, same check
  const strengthDone = useMemo(() => {
    const map = new Map<string, boolean>();
    for (const s of strengths) {
      const combos = matrix.filter((m) => m.strength_name === s);
      map.set(
        s,
        combos.every(
          (c) =>
            conclusions?.[c.combo_id]?.state === 'confirmed' ||
            conclusions?.[c.combo_id]?.state === 'skipped',
        ),
      );
    }
    return map;
  }, [strengths, matrix, conclusions]);

  return (
    <>
      {/* Two-column button grid: equal width, different button heights */}
      <div className="grid grid-cols-2 gap-5">
        {/* Left: Passion buttons */}
        <div>
          <div
            className="mb-2.5 text-center text-[16px] font-[800] text-[#f07d43]"
            style={{ textShadow: '0 1px 0 rgba(255,255,255,0.35)' }}
          >
            热爱
          </div>
          <div className="grid gap-2">
            {passions.map((pName) => {
              const isActive = pName === selPassionName;
              const isDone = passionDone.get(pName);
              return (
                <button
                  key={pName}
                  onClick={() => setSelPassionName(pName)}
                  className={`
                    flex w-full items-center gap-3 min-h-[52px] rounded-[16px] px-4
                    font-[700] text-[16px] cursor-pointer
                    transition-all duration-[0.18s] ease
                    backdrop-blur-[12px]
                    ${isActive
                      ? 'text-white border border-white/58 shadow-[0_12px_24px_rgba(255,137,95,0.26),inset_0_1px_0_rgba(255,255,255,0.4)]'
                      : 'text-[#5d6c80] border border-white/46 bg-white/50 shadow-[inset_0_1px_0_rgba(255,255,255,0.55),0_6px_16px_rgba(33,48,79,0.04)] hover:-translate-y-[1px] hover:bg-white/62'}
                  `}
                  style={
                    isActive
                      ? {
                          background:
                            'linear-gradient(135deg, #ffb05c 0%, #ff7a59 60%, #ff6a7c 100%)',
                        }
                      : undefined
                  }
                >
                  <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-white/36 text-[14px]">
                    ♥
                  </span>
                  <span className="flex-1 text-left truncate">{pName}</span>
                  {isDone && (
                    <span
                      className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[13px] ${
                        isActive ? 'bg-white/18 text-white' : 'bg-white/22 text-[#f07d43]'
                      }`}
                    >
                      ✓
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Strength buttons */}
        <div>
          <div
            className="mb-2.5 text-center text-[16px] font-[800] text-[#3ca56c]"
            style={{ textShadow: '0 1px 0 rgba(255,255,255,0.35)' }}
          >
            优势
          </div>
          <div className="grid gap-[5px]">
            {strengths.map((sName) => {
              const isActive = sName === selStrengthName;
              const isDone = strengthDone.get(sName);
              return (
                <button
                  key={sName}
                  onClick={() => setSelStrengthName(sName)}
                  className={`
                    flex w-full items-center gap-2 min-h-[38px] rounded-[12px] px-3
                    font-[700] text-[14px] cursor-pointer
                    transition-all duration-[0.18s] ease
                    backdrop-blur-[12px]
                    ${isActive
                      ? 'text-white border border-white/58 shadow-[0_8px_16px_rgba(101,208,150,0.22),inset_0_1px_0_rgba(255,255,255,0.4)]'
                      : 'text-[#5d6c80] border border-white/46 bg-white/50 shadow-[inset_0_1px_0_rgba(255,255,255,0.55),0_4px_12px_rgba(33,48,79,0.04)] hover:-translate-y-[1px] hover:bg-white/62'}
                  `}
                  style={
                    isActive
                      ? {
                          background:
                            'linear-gradient(135deg, #57deb0 0%, #72ddb8 56%, #79cfa5 100%)',
                        }
                      : undefined
                  }
                >
                  <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-white/36 text-[12px]">
                    ✦
                  </span>
                  <span className="flex-1 text-left truncate">{sName}</span>
                  {isDone && (
                    <span
                      className={`flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full text-[10px] ${
                        isActive ? 'bg-white/18 text-white' : 'bg-white/22 text-[#3ca56c]'
                      }`}
                    >
                      ✓
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Summary cards */}
      <div className="mt-2.5 grid grid-cols-2 gap-3">
        {selPassionName ? (
          <div
            className="flex min-h-[38px] items-center gap-2.5 rounded-[14px] px-3.5
              font-[700] text-[14px] text-[#4b5563] backdrop-blur-[12px]
              border border-white/44"
            style={{
              background:
                'linear-gradient(135deg, rgba(255,184,134,0.22), rgba(255,117,104,0.16), rgba(255,255,255,0.30))',
            }}
          >
            <span
              className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-full text-[13px]"
              style={{
                background:
                  'linear-gradient(135deg, rgba(255,176,92,0.28), rgba(255,122,89,0.24))',
                color: '#ef7746',
              }}
            >
              ♥
            </span>
            <span className="truncate">已选择：{selPassionName}</span>
          </div>
        ) : (
          <div
            className="flex min-h-[40px] items-center gap-2.5 rounded-[14px] px-3.5
              font-[700] text-[14px] text-[#9ca3af] backdrop-blur-[12px]
              border border-white/44 bg-white/30"
          >
            <span className="flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center rounded-full bg-gray-200/40 text-[12px]">
              ♥
            </span>
            <span>请选择热爱</span>
          </div>
        )}

        {selStrengthName ? (
          <div
            className="flex min-h-[38px] items-center gap-2.5 rounded-[14px] px-3.5
              font-[700] text-[14px] text-[#4b5563] backdrop-blur-[12px]
              border border-white/44"
            style={{
              background:
                'linear-gradient(135deg, rgba(102,229,173,0.20), rgba(120,214,177,0.16), rgba(255,255,255,0.30))',
            }}
          >
            <span
              className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-full text-[13px]"
              style={{
                background:
                  'linear-gradient(135deg, rgba(87,222,176,0.24), rgba(114,221,184,0.22))',
                color: '#34a76d',
              }}
            >
              ✦
            </span>
            <span className="truncate">已选择：{selStrengthName}</span>
          </div>
        ) : (
          <div
            className="flex min-h-[40px] items-center gap-2.5 rounded-[14px] px-3.5
              font-[700] text-[14px] text-[#9ca3af] backdrop-blur-[12px]
              border border-white/44 bg-white/30"
          >
            <span className="flex h-[22px] w-[22px] flex-shrink-0 items-center justify-center rounded-full bg-gray-200/40 text-[12px]">
              ✦
            </span>
            <span>请选择优势</span>
          </div>
        )}
      </div>
    </>
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
