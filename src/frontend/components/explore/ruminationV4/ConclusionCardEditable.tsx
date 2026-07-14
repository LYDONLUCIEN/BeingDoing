'use client';

/**
 * v4 可编辑结论卡
 *
 * 默认展示核心假设 + 跳过/确认结论；
 * 可展开编辑 motivation、work_purposes、passion_mark、timing_mark 等更多字段。
 */

import { useEffect, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { ConclusionCard } from '@/lib/explore/ruminationV4Api';

interface Props {
  comboId: string;
  card: ConclusionCard;
  strengths: string[];
}

export default function ConclusionCardEditable({ comboId, card, strengths }: Props) {
  const { patchCard, setStatus } = useRuminationV4Store();
  const [localHypothesis, setLocalHypothesis] = useState<string>(
    typeof card.hypothesis === 'string' ? card.hypothesis || '' : ''
  );
  const [localMotivation, setLocalMotivation] = useState(card.motivation || '');
  const [localWorkPurposes, setLocalWorkPurposes] = useState<string>(
    (card.work_purposes || []).join('、')
  );
  const [localPassionMark, setLocalPassionMark] = useState(card.passion_mark || '');
  const [localTimingMark, setLocalTimingMark] = useState(card.timing_mark || '');
  const [saving, setSaving] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    setLocalHypothesis(typeof card.hypothesis === 'string' ? card.hypothesis || '' : '');
    setLocalMotivation(card.motivation || '');
    setLocalWorkPurposes((card.work_purposes || []).join('、'));
    setLocalPassionMark(card.passion_mark || '');
    setLocalTimingMark(card.timing_mark || '');
  }, [card.hypothesis, card.motivation, card.work_purposes, card.passion_mark, card.timing_mark, card.updated_at]);

  const handleSaveFields = async (fields: Partial<ConclusionCard>) => {
    setSaving(true);
    try {
      await patchCard(comboId, fields);
    } finally {
      setSaving(false);
    }
  };

  const handleConfirm = async () => {
    if (localHypothesis.trim().length < 5) return;
    await handleSaveFields({
      hypothesis: localHypothesis.trim(),
      motivation: localMotivation.trim() || null,
      work_purposes: splitPurposes(localWorkPurposes),
      passion_mark: (localPassionMark as any) || null,
      timing_mark: (localTimingMark as any) || null,
    });
    await setStatus(comboId, 'concluded');
  };

  const handleSkip = async () => {
    await setStatus(comboId, 'abandoned');
  };

  const canConfirm = localHypothesis.trim().length >= 5;

  return (
    <div
      className="relative flex flex-col rounded-[20px] px-5 pt-5 pb-4 backdrop-blur-[16px] transition-all duration-[0.22s]"
      style={{
        border: '1px solid rgba(255,255,255,0.44)',
        boxShadow: '0 12px 24px rgba(155,135,234,0.10)',
        background:
          'radial-gradient(circle at 10% 15%, rgba(255,255,255,0.32), transparent 20%), ' +
          'linear-gradient(135deg, rgba(208,188,255,0.34) 0%, rgba(184,160,255,0.26) 30%, rgba(244,222,255,0.24) 65%, rgba(255,214,232,0.22) 100%)',
      }}
    >
      {/* Header */}
      <div className="mb-3 flex w-full items-center gap-4">
        <div
          className="flex h-[52px] w-[52px] flex-shrink-0 items-center justify-center rounded-full text-white text-[18px]"
          style={{
            background: 'linear-gradient(135deg, #77dbff 0%, #c09cff 54%, #ffb9c7 100%)',
            boxShadow: '0 12px 24px rgba(147,172,255,0.20)',
          }}
        >
          ✦
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="m-0 text-[13px] font-bold text-[#7b8794]">
              假设结论
              {saving && <span className="ml-2 text-[11px] font-medium text-[#b0b8c4]">保存中…</span>}
            </p>
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-white/54 bg-white/38 text-[#6d5cc9] text-[14px] font-black shadow-sm transition-all hover:-translate-y-[1px] hover:bg-white/52"
              title={isExpanded ? '收起更多字段' : '展开更多字段'}
            >
              <ChevronDown
                size={16}
                className={`transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* 核心假设（始终可见） */}
      <div>
        <label className="mb-1.5 block text-[12px] font-bold text-[#8b7cb8]">
          假设（核心）
        </label>
        <textarea
          value={localHypothesis}
          onChange={(e) => setLocalHypothesis(e.target.value)}
          placeholder="我假设这个方向能带给我什么…"
          rows={4}
          className="w-full resize-none rounded-[12px] border border-white/42 bg-white/40 p-2.5 text-[13px] leading-[1.7] text-[#4b5563] outline-none transition-all focus:border-[rgba(180,153,255,0.52)] focus:bg-white/56"
        />
      </div>

      {/* 展开区域：更多字段 */}
      <div
        className={`grid overflow-hidden transition-[grid-template-rows,opacity,margin-top] duration-[0.24s] ease ${
          isExpanded ? 'mt-4 grid-rows-[1fr] opacity-100' : 'mt-0 grid-rows-[0fr] opacity-0'
        }`}
      >
        <div className="flex flex-col gap-3 overflow-hidden">
          {/* 动机 */}
          <div>
            <label className="mb-1.5 block text-[12px] font-bold text-[#8b7cb8]">动机</label>
            <input
              value={localMotivation}
              onChange={(e) => setLocalMotivation(e.target.value)}
              onBlur={() => handleSaveFields({ motivation: localMotivation.trim() || null })}
              className="w-full rounded-[12px] border border-white/42 bg-white/40 px-2.5 py-2 text-[13px] text-[#4b5563] outline-none transition-all focus:border-[rgba(180,153,255,0.52)] focus:bg-white/56"
              placeholder="驱动我选择这个方向的内在动力…"
            />
          </div>

          {/* 工作目的 */}
          <div>
            <label className="mb-1.5 block text-[12px] font-bold text-[#8b7cb8]">
              工作目的（用顿号分隔）
            </label>
            <input
              value={localWorkPurposes}
              onChange={(e) => setLocalWorkPurposes(e.target.value)}
              onBlur={() =>
                handleSaveFields({ work_purposes: splitPurposes(localWorkPurposes) })
              }
              className="w-full rounded-[12px] border border-white/42 bg-white/40 px-2.5 py-2 text-[13px] text-[#4b5563] outline-none transition-all focus:border-[rgba(180,153,255,0.52)] focus:bg-white/56"
              placeholder="例如：帮助他人、创造作品、获得稳定收入…"
            />
          </div>

          {/* 激情标记 / 时机标记 */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-[12px] font-bold text-[#8b7cb8]">
                激情感受
              </label>
              <select
                value={localPassionMark}
                onChange={(e) => {
                  setLocalPassionMark(e.target.value);
                  handleSaveFields({
                    passion_mark: e.target.value ? (e.target.value as any) : null,
                  });
                }}
                className="w-full rounded-[12px] border border-white/42 bg-white/40 px-2.5 py-2 text-[13px] text-[#4b5563] outline-none"
              >
                <option value="">未选择</option>
                <option value="忍不住想做">忍不住想做</option>
                <option value="应该做">应该做</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-[12px] font-bold text-[#8b7cb8]">时机</label>
              <select
                value={localTimingMark}
                onChange={(e) => {
                  setLocalTimingMark(e.target.value);
                  handleSaveFields({
                    timing_mark: e.target.value ? (e.target.value as any) : null,
                  });
                }}
                className="w-full rounded-[12px] border border-white/42 bg-white/40 px-2.5 py-2 text-[13px] text-[#4b5563] outline-none"
              >
                <option value="">未选择</option>
                <option value="现在">现在</option>
                <option value="未来">未来</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="mt-4 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={handleSkip}
          className="mini-btn h-[38px] rounded-full border border-white/48 bg-white/42 px-4 text-[13px] font-extrabold text-[#6b7280] shadow-sm transition-transform hover:-translate-y-[1px]"
        >
          跳过
        </button>
        <button
          type="button"
          disabled={!canConfirm || saving}
          onClick={handleConfirm}
          className="mini-btn primary h-[38px] rounded-full border-0 px-4 text-[13px] font-extrabold text-white transition-transform hover:-translate-y-[1px] disabled:cursor-not-allowed disabled:opacity-40"
          style={{
            background: canConfirm
              ? 'linear-gradient(90deg, #3272ff, #1fc5a2)'
              : undefined,
          }}
        >
          {saving ? '保存中…' : '确认结论'}
        </button>
      </div>
    </div>
  );
}

function splitPurposes(text: string): string[] {
  return text
    .split(/[、,，;；]/)
    .map((s) => s.trim())
    .filter(Boolean);
}
