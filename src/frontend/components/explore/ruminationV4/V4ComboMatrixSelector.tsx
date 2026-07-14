'use client';

/**
 * v4 选择器 — 块状网格：热爱一行三列 / 优势一行五列
 * 视觉：v3 橙热爱 / 绿优势；「开始探索」保留紫 CTA
 */

import { useEffect, useState, type CSSProperties } from 'react';

export interface DimensionOption {
  name: string;
  /** 语义化维度图标；未提供时用类型默认值 */
  glyph?: string;
}

interface V4ComboMatrixSelectorProps {
  passions: Array<string | DimensionOption>;
  strengths: Array<string | DimensionOption>;
  /** 返回 true 表示创建成功（成功后才清空本地选点） */
  onCreateCombo: (passion: string, strengths: string[]) => void | Promise<boolean | void>;
  creating?: boolean;
  locked?: boolean;
  lockedPassion?: string | null;
  lockedStrengths?: string[];
}

function normalizeOptions(items: Array<string | DimensionOption>): DimensionOption[] {
  return items.map((item) => (typeof item === 'string' ? { name: item } : item));
}

const glassPanelStyle: CSSProperties = {
  borderRadius: '18px',
  border: '1px solid rgba(255,255,255,0.38)',
  background:
    'linear-gradient(135deg, rgba(255,245,248,0.22) 0%, rgba(255,250,241,0.18) 20%, rgba(245,239,255,0.16) 54%, rgba(237,255,247,0.18) 100%)',
  backdropFilter: 'blur(18px)',
  padding: '14px 14px 12px',
};

export default function V4ComboMatrixSelector({
  passions,
  strengths,
  onCreateCombo,
  creating = false,
  locked = false,
  lockedPassion = null,
  lockedStrengths = [],
}: V4ComboMatrixSelectorProps) {
  const passionOpts = normalizeOptions(passions);
  const strengthOpts = normalizeOptions(strengths);

  const [selPassion, setSelPassion] = useState<string | null>(null);
  const [selStrengths, setSelStrengths] = useState<string[]>([]);

  useEffect(() => {
    if (!locked) {
      setSelPassion(null);
      setSelStrengths([]);
    }
  }, [locked]);

  const activePassion = locked ? lockedPassion : selPassion;
  const activeStrengths = locked ? lockedStrengths : selStrengths;

  const toggleStrength = (s: string) => {
    if (locked) return;
    setSelStrengths((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    );
  };

  const canCreate = !!activePassion && activeStrengths.length > 0 && !creating && !locked;

  const handleCreate = async () => {
    if (!canCreate || !activePassion) return;
    const ok = await onCreateCombo(activePassion, activeStrengths);
    if (ok) {
      setSelPassion(null);
      setSelStrengths([]);
    }
  };

  return (
    <div style={glassPanelStyle}>
      {/* ① 热爱 — 一行三列 */}
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[14px] font-[800] text-[#f07d43]">① 选择 1 项热爱</span>
        <span className="text-[12px] font-[500] text-[#9ca3af]">（单选）</span>
      </div>
      <div className="mb-3.5 grid grid-cols-3 gap-2.5">
        {passionOpts.map((p) => {
          const isActive = p.name === activePassion;
          const glyph = p.glyph || '♥';
          return (
            <button
              key={p.name}
              type="button"
              disabled={locked}
              onClick={() => !locked && setSelPassion(p.name)}
              className={`
                relative flex min-h-[96px] flex-col items-center justify-center gap-2
                rounded-[16px] px-2 py-3 text-center
                font-[700] transition-all duration-[0.18s] ease
                backdrop-blur-[12px]
                ${locked ? 'cursor-default' : 'cursor-pointer'}
                ${
                  isActive
                    ? 'border border-white/58 text-white shadow-[0_12px_24px_rgba(255,137,95,0.26),inset_0_1px_0_rgba(255,255,255,0.4)]'
                    : 'border border-white/46 bg-white/55 text-[#5d6c80] shadow-[inset_0_1px_0_rgba(255,255,255,0.55),0_6px_16px_rgba(33,48,79,0.04)] hover:-translate-y-[1px] hover:bg-white/70'
                }
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
              {isActive && (
                <span className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-white/22 text-[11px] text-white">
                  ✓
                </span>
              )}
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-full text-[16px] ${
                  isActive ? 'bg-white/28' : 'bg-[rgba(255,122,89,0.12)] text-[#f07d43]'
                }`}
              >
                {glyph}
              </span>
              <span className="line-clamp-2 px-1 text-[13px] leading-snug">{p.name}</span>
            </button>
          );
        })}
        {passionOpts.length === 0 && (
          <div className="col-span-3 py-3 text-center text-[12px] text-[#9ca3af]">
            暂无可选热爱
          </div>
        )}
      </div>

      {/* ② 优势 — 一行五列 */}
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[14px] font-[800] text-[#3ca56c]">② 选择你的优势</span>
        <span className="text-[12px] font-[500] text-[#9ca3af]">
          （可多选 · {activeStrengths.length}）
        </span>
      </div>
      <div className="mb-3.5 grid grid-cols-5 gap-2">
        {strengthOpts.map((s) => {
          const isActive = activeStrengths.includes(s.name);
          const glyph = s.glyph || '✦';
          return (
            <button
              key={s.name}
              type="button"
              disabled={locked}
              onClick={() => toggleStrength(s.name)}
              className={`
                relative flex min-h-[88px] flex-col items-center justify-center gap-1.5
                rounded-[14px] px-1.5 py-2.5 text-center
                font-[700] transition-all duration-[0.18s] ease
                backdrop-blur-[12px]
                ${locked ? 'cursor-default' : 'cursor-pointer'}
                ${
                  isActive
                    ? 'border border-white/58 text-white shadow-[0_8px_16px_rgba(101,208,150,0.22),inset_0_1px_0_rgba(255,255,255,0.4)]'
                    : 'border border-white/46 bg-white/55 text-[#5d6c80] shadow-[inset_0_1px_0_rgba(255,255,255,0.55),0_4px_12px_rgba(33,48,79,0.04)] hover:-translate-y-[1px] hover:bg-white/70'
                }
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
              {isActive && (
                <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-white/22 text-[10px] text-white">
                  ✓
                </span>
              )}
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full text-[13px] ${
                  isActive ? 'bg-white/28' : 'bg-[rgba(60,165,108,0.12)] text-[#3ca56c]'
                }`}
              >
                {glyph}
              </span>
              <span className="line-clamp-2 px-0.5 text-[12px] leading-snug">{s.name}</span>
            </button>
          );
        })}
        {strengthOpts.length === 0 && (
          <div className="col-span-5 py-3 text-center text-[12px] text-[#9ca3af]">
            暂无可选优势
          </div>
        )}
      </div>

      {!locked && (
        <>
          <button
            type="button"
            disabled={!canCreate}
            onClick={handleCreate}
            className="flex w-full min-h-[52px] items-center justify-center gap-3 rounded-[15px] border-0 transition-all duration-200 ease-out"
            style={
              canCreate
                ? {
                    background: 'linear-gradient(110deg,#826aff,#553df2 80%,#6a51ff)',
                    boxShadow: '0 14px 25px rgba(91,65,240,.22)',
                    cursor: 'pointer',
                  }
                : {
                    background: 'rgba(200,200,220,.35)',
                    cursor: 'not-allowed',
                  }
            }
          >
            <span className="text-[26px] leading-none text-white">✦</span>
            <span className="flex flex-col items-start">
              <span className="text-[16px] font-[760] leading-tight text-white">
                {creating ? '创建中…' : '开始探索'}
              </span>
              <span className="mt-0.5 text-[12px] text-white/86">解锁你的组合洞察</span>
            </span>
          </button>
          {!canCreate && !creating && (
            <p className="mt-2 text-center text-[12px] font-[600] text-[#9ca3af]">
              {!activePassion && activeStrengths.length === 0
                ? '请先选择 1 项热爱，再勾选至少一个优势'
                : !activePassion
                  ? '请先选择 1 项热爱'
                  : '请至少勾选一个优势'}
            </p>
          )}
        </>
      )}

      {locked && (
        <div className="flex items-center justify-center gap-1.5 py-1 text-[12px] text-[#9ca3af]">
          <span className="text-[#3ca56c]">✓</span>
          组合已固定；改方向请点「新建组合」
        </div>
      )}
    </div>
  );
}
