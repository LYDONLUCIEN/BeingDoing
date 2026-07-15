'use client';

/**
 * v4 可编辑结论卡
 *
 * 视觉对齐 new-rumination-v4.html：
 * - 左侧公文包 icon
 * - 中间：标题（含 combo badge）+ 描述 copy + 「查看全文」
 * - 右侧：时间 + 更多操作
 * - 展开后：下方 textarea + 跳过/确认修改
 *
 * 默认折叠时只展示核心假设 textarea + 跳过/确认结论；
 * 点击「查看全文」后展开更多字段编辑。
 */

import { useEffect, useMemo, useState } from 'react';
import { Briefcase, MoreHorizontal } from 'lucide-react';
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

  const displayCopy = useMemo(() => {
    const parts: string[] = [];
    if (localMotivation.trim()) parts.push(`动机：${localMotivation.trim()}`);
    if (localWorkPurposes.trim()) parts.push(`工作目的：${localWorkPurposes.trim()}`);
    if (localPassionMark) parts.push(`激情感受：${localPassionMark}`);
    if (localTimingMark) parts.push(`时机：${localTimingMark}`);
    if (!parts.length) return '这个方向还在探索中，和 AI 聊聊后完善你的假设结论。';
    return parts.join(' · ');
  }, [localMotivation, localWorkPurposes, localPassionMark, localTimingMark]);

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
    <article
      className={`conclusion-card-v4 ${isExpanded ? 'open' : ''}`}
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto 1fr auto',
        gap: '14px',
        padding: '14px',
        borderRadius: '17px',
        border: '1px solid rgba(106,121,174,0.11)',
        background: 'rgba(255,255,255,0.65)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.7)',
      }}
    >
      {/* 左侧 icon */}
      <div
        className="bag-icon flex h-[56px] w-[56px] flex-shrink-0 items-center justify-center rounded-full text-[#6656f7]"
        style={{
          background: 'linear-gradient(160deg,#f4f0ff,#eef2ff)',
        }}
        aria-hidden
      >
        <Briefcase size={28} strokeWidth={1.6} />
      </div>

      {/* 中间内容 */}
      <div className="min-w-0">
        <div className="conclusion-title mb-1.5 text-[16px] font-[800] text-[#1f2937]">
          <span className="break-words">
            {localHypothesis.trim() || '你的假设方向'}
          </span>
          <span
            className="combo-badge ml-2 inline-flex align-middle rounded-full px-2 py-0.5 text-[11px] font-[700]"
            style={{ background: '#efedff', color: '#6756ee' }}
          >
            {strengths.slice(0, 2).join('、') || '组合'}
          </span>
        </div>

        <p className="conclusion-copy m-0 text-[13px] leading-[1.58] text-[#516082]">
          {displayCopy}
        </p>

        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="full-link mt-1.5 inline-block text-[13px] font-[700] text-[#6656f6] hover:underline"
        >
          {isExpanded ? '收起全文' : '查看全文'}
        </button>

        {/* 展开编辑器 */}
        {isExpanded && (
          <div
            className="expanded-editor mt-3"
            style={{ gridColumn: '2 / 4' }}
          >
            <label className="mb-1.5 block text-[12px] font-[700] text-[#6b7280]">
              假设（核心）
            </label>
            <textarea
              value={localHypothesis}
              onChange={(e) => setLocalHypothesis(e.target.value)}
              placeholder="我假设这个方向能带给我什么…"
              className="editor mb-3 w-full resize-y rounded-[13px] border border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] px-3.5 py-3 text-[13px] leading-[1.6] text-[#334163] outline-none focus:border-[#7b68ff] focus:shadow-[0_0_0_3px_rgba(123,104,255,0.10)]"
              rows={4}
            />

            <div className="mb-3 grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block text-[12px] font-[700] text-[#6b7280]">激情感受</label>
                <select
                  value={localPassionMark}
                  onChange={(e) => {
                    setLocalPassionMark(e.target.value);
                    handleSaveFields({
                      passion_mark: e.target.value ? (e.target.value as any) : null,
                    });
                  }}
                  className="w-full rounded-xl border border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] px-3 py-2 text-[13px] text-[#334163] outline-none"
                >
                  <option value="">未选择</option>
                  <option value="忍不住想做">忍不住想做</option>
                  <option value="应该做">应该做</option>
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-[12px] font-[700] text-[#6b7280]">时机</label>
                <select
                  value={localTimingMark}
                  onChange={(e) => {
                    setLocalTimingMark(e.target.value);
                    handleSaveFields({
                      timing_mark: e.target.value ? (e.target.value as any) : null,
                    });
                  }}
                  className="w-full rounded-xl border border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] px-3 py-2 text-[13px] text-[#334163] outline-none"
                >
                  <option value="">未选择</option>
                  <option value="现在">现在</option>
                  <option value="未来">未来</option>
                </select>
              </div>
            </div>

            <label className="mb-1.5 block text-[12px] font-[700] text-[#6b7280]">动机</label>
            <input
              value={localMotivation}
              onChange={(e) => setLocalMotivation(e.target.value)}
              onBlur={() => handleSaveFields({ motivation: localMotivation.trim() || null })}
              className="mb-3 w-full rounded-xl border border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] px-3 py-2 text-[13px] text-[#334163] outline-none focus:border-[#7b68ff]"
              placeholder="驱动我选择这个方向的内在动力…"
            />

            <label className="mb-1.5 block text-[12px] font-[700] text-[#6b7280]">
              工作目的（用顿号分隔）
            </label>
            <input
              value={localWorkPurposes}
              onChange={(e) => setLocalWorkPurposes(e.target.value)}
              onBlur={() => handleSaveFields({ work_purposes: splitPurposes(localWorkPurposes) })}
              className="mb-4 w-full rounded-xl border border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] px-3 py-2 text-[13px] text-[#334163] outline-none focus:border-[#7b68ff]"
              placeholder="例如：帮助他人、创造作品、获得稳定收入…"
            />
          </div>
        )}
      </div>

      {/* 右侧操作 */}
      <div className="card-actions flex flex-shrink-0 flex-col items-end gap-4 text-[12px] text-[#77829f]">
        <span className="whitespace-nowrap">
          {saving ? '保存中…' : '刚刚'}
        </span>
        <button
          type="button"
          className="rounded-full p-1 text-[#1f2d67] transition-colors hover:bg-black/5"
          title="更多"
        >
          <MoreHorizontal size={22} />
        </button>
      </div>

      {/* 底部操作按钮：折叠/展开均显示 */}
      <div
        className="col-span-full mt-1 flex items-center justify-end gap-2"
        style={{ gridColumn: '1 / 4' }}
      >
        <button
          type="button"
          onClick={handleSkip}
          disabled={saving}
          className="small-btn rounded-[10px] border border-[rgba(101,86,239,0.24)] bg-white px-[18px] py-2 text-[13px] font-[700] text-[#6254eb] transition-transform hover:-translate-y-px disabled:opacity-50"
        >
          跳过
        </button>
        <button
          type="button"
          disabled={!canConfirm || saving}
          onClick={handleConfirm}
          className="small-btn primary rounded-[10px] border-0 px-[18px] py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
          style={{
            background: canConfirm
              ? 'linear-gradient(135deg,#7a64ff,#5d49ef)'
              : undefined,
          }}
        >
          {saving ? '保存中…' : '确认结论'}
        </button>
      </div>
    </article>
  );
}

function splitPurposes(text: string): string[] {
  return text
    .split(/[、,，;；]/)
    .map((s) => s.trim())
    .filter(Boolean);
}
