'use client';

/**
 * v4 可编辑结论卡 — v3 视觉风格
 *
 * 视觉继承 v3 ConclusionResultCard：渐变背景、✦ 图标、展开/收起
 * 功能保留 v4：hypothesis（核心）+ motivation + 其他字段
 */

import { useEffect, useState } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { ConclusionCard } from '@/lib/explore/ruminationV4Api';

interface Props {
  comboId: string;
  card: ConclusionCard;
  strengths: string[];
}

export default function ConclusionCardEditable({ comboId, card, strengths }: Props) {
  const { patchCard, setStatus } = useRuminationV4Store();
  const [localHypothesis, setLocalHypothesis] = useState<string | Record<string, string>>(
    card.hypothesis || ''
  );
  const [localMotivation, setLocalMotivation] = useState(card.motivation || '');
  const [saving, setSaving] = useState(false);
  const [isExpanded, setIsExpanded] = useState(true);

  useEffect(() => {
    setLocalHypothesis(card.hypothesis || '');
    setLocalMotivation(card.motivation || '');
  }, [card.hypothesis, card.motivation, card.updated_at]);

  const isDict = typeof localHypothesis === 'object' && localHypothesis !== null;

  const handleSave = async () => {
    setSaving(true);
    try {
      await patchCard(comboId, { hypothesis: localHypothesis, motivation: localMotivation });
    } finally {
      setSaving(false);
    }
  };

  const canConfirm = (() => {
    if (isDict) return Object.values(localHypothesis).some((v) => v.length >= 5);
    return (localHypothesis as string).length >= 5;
  })();

  return (
    <div
      className="relative flex flex-col rounded-[20px] backdrop-blur-[16px] transition-all duration-[0.22s] ease px-5 pt-5 pb-4"
      style={{
        border: '1px solid rgba(255,255,255,0.44)',
        boxShadow: '0 12px 24px rgba(155,135,234,0.10)',
        background:
          'radial-gradient(circle at 10% 15%, rgba(255,255,255,0.32), transparent 20%), ' +
          'linear-gradient(135deg, rgba(208,188,255,0.34) 0%, rgba(184,160,255,0.26) 30%, rgba(244,222,255,0.24) 65%, rgba(255,214,232,0.22) 100%)',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-4 w-full mb-3">
        <div
          className="flex h-[52px] w-[52px] flex-shrink-0 items-center justify-center rounded-full text-white text-[18px]"
          style={{
            background: 'linear-gradient(135deg, #77dbff 0%, #c09cff 54%, #ffb9c7 100%)',
            boxShadow: '0 12px 24px rgba(147,172,255,0.20)',
          }}
        >
          ✦
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="m-0 text-[13px] font-[700] text-[#7b8794]">假设结果</p>
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className={`flex h-[28px] w-[28px] flex-shrink-0 items-center justify-center rounded-full border border-white/54 bg-white/38 text-[#6d5cc9] text-[14px] font-[900] shadow-[inset_0_1px_0_rgba(255,255,255,0.48),0_6px_14px_rgba(104,84,190,0.10)] transition-all duration-[0.18s] ease hover:-translate-y-[1px] hover:bg-white/52 ${isExpanded ? 'rotate-180' : ''}`}
            >
              ⌄
            </button>
          </div>
        </div>
      </div>

      {/* 展开内容 */}
      <div
        className={`grid overflow-hidden transition-[grid-template-rows,opacity] duration-[0.24s] ease ${
          isExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
        }`}
      >
        <div className="overflow-hidden flex flex-col gap-3">
          {/* hypothesis（核心） */}
          <div>
            <label className="text-[12px] font-[700] text-[#8b7cb8] block mb-1.5">
              假设（核心）
              {saving && <span className="text-[#b0b8c4] font-[500] ml-2">保存中…</span>}
            </label>
            {isDict ? (
              <div className="space-y-2">
                {Object.entries(localHypothesis as Record<string, string>).map(([k, v]) => (
                  <div key={k}>
                    <div className="text-[11px] text-[#7b8794] mb-1">{k}</div>
                    <textarea
                      className="w-full p-2.5 rounded-[12px] text-[13px] text-[#4b5563] leading-[1.7] bg-white/40 border border-white/42 resize-none focus:outline-none focus:bg-white/56 focus:border-[rgba(180,153,255,0.52)]"
                      rows={2}
                      value={v}
                      onChange={(e) =>
                        setLocalHypothesis({
                          ...(localHypothesis as Record<string, string>),
                          [k]: e.target.value,
                        })
                      }
                      onBlur={handleSave}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <textarea
                className="w-full p-2.5 rounded-[12px] text-[13px] text-[#4b5563] leading-[1.7] bg-white/40 border border-white/42 resize-none focus:outline-none focus:bg-white/56 focus:border-[rgba(180,153,255,0.52)]"
                rows={4}
                value={localHypothesis as string}
                onChange={(e) => setLocalHypothesis(e.target.value)}
                onBlur={handleSave}
                placeholder="我假设这个方向能带给我什么…"
              />
            )}
          </div>

          {/* motivation */}
          <div>
            <label className="text-[12px] font-[700] text-[#8b7cb8] block mb-1.5">动机</label>
            <input
              className="w-full px-2.5 py-2 rounded-[12px] text-[13px] text-[#4b5563] bg-white/40 border border-white/42 focus:outline-none focus:bg-white/56 focus:border-[rgba(180,153,255,0.52)]"
              value={localMotivation}
              onChange={(e) => setLocalMotivation(e.target.value)}
              onBlur={handleSave}
            />
          </div>

          {/* 其他字段（只读） */}
          <div className="grid grid-cols-3 gap-2 text-[11px]">
            <div className="rounded-[10px] bg-white/30 px-2.5 py-1.5 border border-white/30">
              <div className="text-[#7b8794] font-[600]">工作目的</div>
              <div className="text-[#4b5563] mt-0.5">{card.work_purposes?.join('、') || '—'}</div>
            </div>
            <div className="rounded-[10px] bg-white/30 px-2.5 py-1.5 border border-white/30">
              <div className="text-[#7b8794] font-[600]">激情感受</div>
              <div className="text-[#4b5563] mt-0.5">{card.passion_mark || '—'}</div>
            </div>
            <div className="rounded-[10px] bg-white/30 px-2.5 py-1.5 border border-white/30">
              <div className="text-[#7b8794] font-[600]">时机</div>
              <div className="text-[#4b5563] mt-0.5">{card.timing_mark || '—'}</div>
            </div>
          </div>

          {/* 操作按钮 */}
          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              className="h-[38px] rounded-full border border-white/48 bg-white/42 px-4 text-[13px] font-[800] text-[#6b7280] cursor-pointer shadow-[0_8px_24px_rgba(33,48,79,0.06)] transition-transform hover:-translate-y-[1px]"
              onClick={() => setStatus(comboId, 'discussing')}
            >
              继续讨论
            </button>
            <button
              type="button"
              disabled={!canConfirm}
              onClick={async () => {
                await handleSave();
                await setStatus(comboId, 'concluded');
              }}
              className="h-[38px] rounded-full border-0 px-4 text-[13px] font-[800] text-white cursor-pointer transition-transform hover:-translate-y-[1px] disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background: canConfirm ? 'linear-gradient(135deg, #b499ff, #f39ad5)' : undefined,
                boxShadow: canConfirm ? '0 10px 20px rgba(180,153,255,0.20)' : undefined,
              }}
            >
              确认结论
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
