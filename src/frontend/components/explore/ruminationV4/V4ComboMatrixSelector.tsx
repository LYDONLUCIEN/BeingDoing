'use client';

/**
 * v4 选择器 — 块状网格：热爱一行三列 / 优势一行五列
 * 视觉对齐 preview.html：橙热爱 / 绿优势、数字圆圈标题、已选计数
 */

import { useEffect, useState } from 'react';

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
        <div className="section-title mb-4 flex items-center gap-2.5 text-[16px] font-extrabold text-[#ff6426]">
          <span
            className="flex h-[25px] w-[25px] items-center justify-center rounded-full border-2 border-current text-[15px]"
          >
            1
          </span>
          <span>选择 1 项热爱</span>
          <small className="text-[13px] font-semibold text-[#78849a]">（单选）</small>
        </div>
        <div className="cards-row love-cards grid grid-cols-3 gap-[18px]">
          {passionOpts.map((p) => {
            const isActive = p.name === activePassion;
            const glyph = p.glyph || (isActive ? '♥' : '♡');
            return (
              <button
                key={p.name}
                type="button"
                disabled={locked}
                onClick={() => !locked && setSelPassion(p.name)}
                className={`
                  choice-card love-card relative flex min-h-[106px] flex-col items-center justify-center gap-2.5
                  rounded-[14px] border px-2 py-3 text-center font-semibold transition-all duration-200
                  ${locked ? 'cursor-default' : 'cursor-pointer hover:-translate-y-0.5'}
                  ${
                    isActive
                      ? 'selected border-[#ff6b36] text-white shadow-[0_12px_25px_rgba(255,90,51,0.23)]'
                      : 'border-[#dfe5ee] bg-white/70 text-[#334563] shadow-[0_4px_12px_rgba(18,40,75,0.04)] hover:border-[#c7d7ef] hover:shadow-[0_8px_20px_rgba(18,40,75,0.08)]'
                  }
                `}
                style={
                  isActive
                    ? {
                        background:
                          'linear-gradient(135deg, #ff9835 0%, #ff722e 52%, #ff3e4f 100%)',
                      }
                    : undefined
                }
              >
                {isActive && (
                  <span
                    className="selected-mark absolute right-2 top-2 grid h-5 w-5 place-items-center rounded-full text-[11px] text-white"
                    style={{ background: '#ff7041', border: '2px solid rgba(255,255,255,0.9)' }}
                  >
                    ✓
                  </span>
                )}
                <span
                  className={`round-icon flex h-[42px] w-[42px] items-center justify-center rounded-full border text-[24px] ${
                    isActive
                      ? 'border-0 bg-white text-[#ff6037]'
                      : 'border-[#dbe1eb] bg-white/82 text-[#ff6037]'
                  }`}
                >
                  {glyph}
                </span>
                <span className="label line-clamp-2 px-1 text-[15px] leading-snug">{p.name}</span>
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
        <div className="section-title mb-4 flex items-center gap-2.5 text-[16px] font-extrabold text-[#00a878]">
          <span
            className="flex h-[25px] w-[25px] items-center justify-center rounded-full border-2 border-current text-[15px]"
          >
            2
          </span>
          <span>选择你的优势</span>
          <small className="text-[13px] font-semibold text-[#78849a]">（可多选）</small>
        </div>
        <div className="cards-row strength-cards grid grid-cols-5 gap-4">
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
                  choice-card strength-card relative flex min-h-[110px] flex-col items-center justify-center gap-1.5
                  rounded-[14px] border px-1.5 py-2.5 text-center font-semibold transition-all duration-200
                  ${locked ? 'cursor-default' : 'cursor-pointer hover:-translate-y-0.5'}
                  ${
                    isActive
                      ? 'selected border-[#9ee4d0] text-[#008f6a] shadow-[0_9px_20px_rgba(11,179,132,0.09)]'
                      : 'border-[#dfe5ee] bg-white/70 text-[#354768] shadow-[0_4px_12px_rgba(18,40,75,0.04)] hover:border-[#c7d7ef] hover:shadow-[0_8px_20px_rgba(18,40,75,0.08)]'
                  }
                `}
                style={
                  isActive
                    ? {
                        background:
                          'linear-gradient(145deg, rgba(232,253,247,0.96), rgba(235,248,244,0.86))',
                      }
                    : undefined
                }
              >
                {isActive && (
                  <span
                    className="selected-mark absolute right-1.5 top-1.5 grid h-4 w-4 place-items-center rounded-full text-[10px] text-white"
                    style={{ background: '#08aa7e', border: '2px solid rgba(255,255,255,0.9)' }}
                  >
                    ✓
                  </span>
                )}
                <span
                  className={`round-icon flex h-[37px] w-[37px] items-center justify-center rounded-full bg-transparent text-[25px] ${
                    isActive ? 'text-[#00a979]' : 'text-[#39517b]'
                  }`}
                >
                  {glyph}
                </span>
                <span
                  className="label line-clamp-2 px-0.5 text-[12px] leading-snug"
                  dangerouslySetInnerHTML={{
                    __html: s.name.replace(/\n/g, '<br>'),
                  }}
                />
              </button>
            );
          })}
          {strengthOpts.length === 0 && (
            <div className="col-span-5 py-3 text-center text-[12px] text-[#9ca3af]">
              暂无可选优势
            </div>
          )}
        </div>
        <div className="selected-count mt-3.5 text-center text-[13px] text-[#7a8598]">
          <strong className="mr-1.5 text-[#03a878]">✓</strong>
          已选择 {activeStrengths.length} 项优势
        </div>
      </div>

      {!locked && (
        <>
          <button
            type="button"
            disabled={!canCreate}
            onClick={handleCreate}
            className="mt-4 flex w-full min-h-[52px] items-center justify-center gap-3 rounded-[15px] border-0 transition-all duration-200 ease-out"
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
        <div className="mt-3 flex items-center justify-center gap-1.5 text-[12px] text-[#9ca3af]">
          <span className="text-[#3ca56c]">✓</span>
          组合已固定；改方向请点「新建组合」
        </div>
      )}
    </div>
  );
}
