'use client';

/**
 * v4 选择器 — 块状网格：热爱一行三列 / 优势一行五列
 * 视觉对齐 openlife-journey (21).html guided 选择区：纯文字小卡（无 emoji/字符图标），
 * duo 柔色（热爱珊瑚 #e86f7e × 优势雾蓝 #5b84e6），选中态 = 浅底色 + 彩色描边。
 * 颜色全部经 --matrix-* CSS 变量驱动（openlife-chat-appearance.css），
 * 外观面板「选择矩阵样式 soft/outline/solid × 配色 duo/violet/multi」可整体切换。
 */

import { useEffect, useState } from 'react';

export interface DimensionOption {
  name: string;
  /** 已废弃：选择卡改为纯文字卡，不再渲染图标（保留字段仅为兼容旧调用方） */
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
    <div>
      {/* ① 热爱 — 一行三列 */}
      <div className="selection-block mb-4">
        <div
          className="section-title mb-2.5 flex items-center gap-2 text-[13px] font-semibold"
          style={{ color: 'var(--matrix-love-ink)' }}
        >
          <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full border-[1.5px] border-current text-[10.5px] font-semibold">
            1
          </span>
          <span>选择一项热爱</span>
          <small className="text-[11px] font-normal text-[#98a1ad]">单选</small>
        </div>
        <div className="cards-row love-cards grid grid-cols-3 gap-2.5">
          {passionOpts.map((p) => {
            const isActive = p.name === activePassion;
            return (
              <button
                key={p.name}
                type="button"
                disabled={locked}
                onClick={() => !locked && setSelPassion(p.name)}
                className={`
                  choice-card love-card relative flex min-h-[64px] flex-col items-center justify-center
                  rounded-[12px] border px-2 py-2.5 text-center transition-all duration-200
                  ${locked ? 'cursor-default' : 'cursor-pointer hover:-translate-y-0.5'}
                  ${
                    isActive
                      ? 'selected'
                      : 'border-[#e7ebef] bg-white/70 text-[#33415c] shadow-[0_4px_12px_rgba(18,40,75,0.04)] hover:border-[#c7d7ef] hover:shadow-[0_8px_20px_rgba(18,40,75,0.08)]'
                  }
                `}
              >
                {isActive && (
                  <span className="selected-mark absolute right-1 top-1 grid h-4 w-4 place-items-center rounded-full text-[9px] leading-none text-white">
                    ✓
                  </span>
                )}
                <span className="label line-clamp-2 px-2 text-[13px] font-medium leading-snug">
                  {p.name}
                </span>
              </button>
            );
          })}
          {passionOpts.length === 0 && (
            <div className="col-span-3 py-3 text-center text-[12px] text-[#9ca3af]">
              暂无可选热爱
            </div>
          )}
        </div>
      </div>

      {/* ② 优势 — 一行五列 */}
      <div className="selection-block">
        <div
          className="section-title mb-2.5 flex items-center gap-2 text-[13px] font-semibold"
          style={{ color: 'var(--matrix-strength-ink)' }}
        >
          <span className="flex h-[18px] w-[18px] items-center justify-center rounded-full border-[1.5px] border-current text-[10.5px] font-semibold">
            2
          </span>
          <span>选择你的优势</span>
          <small className="text-[11px] font-normal text-[#98a1ad]">多选</small>
        </div>
        <div
          className="cards-row strength-cards grid gap-2"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(92px, 1fr))' }}
        >
          {strengthOpts.map((s) => {
            const isActive = activeStrengths.includes(s.name);
            return (
              <button
                key={s.name}
                type="button"
                disabled={locked}
                onClick={() => toggleStrength(s.name)}
                className={`
                  choice-card strength-card relative flex min-h-[56px] flex-col items-center justify-center
                  rounded-[12px] border px-1.5 py-2 text-center transition-all duration-200
                  ${locked ? 'cursor-default' : 'cursor-pointer hover:-translate-y-0.5'}
                  ${
                    isActive
                      ? 'selected'
                      : 'border-[#e7ebef] bg-white/70 text-[#33415c] shadow-[0_4px_12px_rgba(18,40,75,0.04)] hover:border-[#c7d7ef] hover:shadow-[0_8px_20px_rgba(18,40,75,0.08)]'
                  }
                `}
              >
                {isActive && (
                  <span className="selected-mark absolute right-1 top-1 grid h-4 w-4 place-items-center rounded-full text-[9px] leading-none text-white">
                    ✓
                  </span>
                )}
                <span
                  className="label line-clamp-2 px-0.5 text-[12.5px] font-medium leading-snug"
                  dangerouslySetInnerHTML={{
                    __html: s.name.replace(/\n/g, '<br>'),
                  }}
                />
              </button>
            );
          })}
          {strengthOpts.length === 0 && (
            <div className="col-span-full py-3 text-center text-[12px] text-[#9ca3af]">
              暂无可选优势
            </div>
          )}
        </div>
        <div className="selected-count mt-2.5 text-center text-[12px] text-[#7a8598]">
          <strong
            className="mr-1"
            style={{ color: 'var(--matrix-strength)' }}
          >
            ✓
          </strong>
          已选择 {activeStrengths.length} 项优势
        </div>
      </div>

      {!locked && (
        <>
          <button
            type="button"
            disabled={!canCreate}
            onClick={handleCreate}
            className="mt-3.5 flex min-h-[46px] w-full items-center justify-center gap-2 rounded-[13px] border-0 transition-all duration-200 ease-out"
            style={
              canCreate
                ? {
                    background: 'linear-gradient(110deg,#826aff,#553df2 80%,#6a51ff)',
                    boxShadow: '0 10px 20px rgba(91,65,240,.2)',
                    cursor: 'pointer',
                  }
                : {
                    background: 'rgba(200,200,220,.35)',
                    cursor: 'not-allowed',
                  }
            }
          >
            <span className="text-[13px] leading-none text-white">✦</span>
            <span className="flex flex-col items-start">
              <span className="text-[14px] font-[700] leading-tight text-white">
                {creating ? '创建中…' : '开始探索'}
              </span>
              <span className="mt-0.5 text-[11px] text-white/85">解锁你的组合洞察</span>
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
        <div className="mt-3 flex items-center justify-center gap-1.5 text-[12px] text-[#9ca3af]">
          <span style={{ color: 'var(--matrix-strength)' }}>✓</span>
          组合已固定；改方向请点「新建组合」
        </div>
      )}
    </div>
  );
}
