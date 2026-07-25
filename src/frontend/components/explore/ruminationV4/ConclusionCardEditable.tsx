'use client';

/**
 * v4 可编辑结论卡（极简版）
 *
 * 卡面 = hypothesis（textarea 可编辑）+「确认」/「跳过」
 * - PATCH 只传 hypothesis
 * - 跳过态：卡内容保留，删除线 + 灰色 + 「已跳过」标记；
 *   灰色卡上保留「确认」按钮（点击恢复 concluded，可逆）
 * - 不渲染/不提交 motivation/work_purposes/passion_mark/timing_mark/balance 等后台字段
 *
 * 见 wiki/开发文档/7-25-rumination-v4-实施口径.md §3.2
 */

import { useEffect, useState } from 'react';
import { Briefcase } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { ConclusionCard } from '@/lib/explore/ruminationV4Api';

interface Props {
  comboId: string;
  card: ConclusionCard;
  strengths: string[];
  /** 用户已跳过（status=abandoned / user_skipped），卡保留、可逆 */
  userSkipped?: boolean;
}

/** 防御：dict 形态已废弃，统一转纯字符串 */
function hypToString(h: ConclusionCard['hypothesis']): string {
  if (!h) return '';
  if (typeof h === 'string') return h;
  return Object.values(h).filter(Boolean).join('\n');
}

export default function ConclusionCardEditable({ comboId, card, strengths, userSkipped }: Props) {
  const { patchCard, setStatus } = useRuminationV4Store();
  const [localHypothesis, setLocalHypothesis] = useState<string>(hypToString(card.hypothesis));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLocalHypothesis(hypToString(card.hypothesis));
  }, [card.hypothesis, card.updated_at]);

  const handleConfirm = async () => {
    const text = localHypothesis.trim();
    if (text.length < 5) return;
    setSaving(true);
    try {
      // hypothesis 有变更才 PATCH（避免无谓触发后端平衡再评估闸）
      if (text !== hypToString(card.hypothesis).trim()) {
        await patchCard(comboId, { hypothesis: text });
      }
      await setStatus(comboId, 'concluded');
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async () => {
    setSaving(true);
    try {
      await setStatus(comboId, 'abandoned');
    } finally {
      setSaving(false);
    }
  };

  const canConfirm = localHypothesis.trim().length >= 5;

  return (
    <article
      className="conclusion-card-v4"
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto 1fr auto',
        gap: '14px',
        padding: '14px',
        borderRadius: '17px',
        border: '1px solid rgba(106,121,174,0.11)',
        background: userSkipped ? 'rgba(243,244,246,0.7)' : 'rgba(255,255,255,0.65)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.7)',
        opacity: userSkipped ? 0.75 : 1,
      }}
    >
      {/* 左侧 icon */}
      <div
        className={`bag-icon flex h-[56px] w-[56px] flex-shrink-0 items-center justify-center rounded-full ${
          userSkipped ? 'text-[#9ca3af]' : 'text-[#6656f7]'
        }`}
        style={{
          background: userSkipped
            ? 'linear-gradient(160deg,#f3f4f6,#e5e7eb)'
            : 'linear-gradient(160deg,#f4f0ff,#eef2ff)',
        }}
        aria-hidden
      >
        <Briefcase size={28} strokeWidth={1.6} />
      </div>

      {/* 中间内容 */}
      <div className="min-w-0">
        <div className="conclusion-title mb-1.5 flex flex-wrap items-center gap-2 text-[14px] font-[800] text-[#1f2937]">
          <span
            className="combo-badge inline-flex rounded-full px-2 py-0.5 text-[11px] font-[700]"
            style={
              userSkipped
                ? { background: '#e5e7eb', color: '#6b7280' }
                : { background: '#efedff', color: '#6756ee' }
            }
          >
            {strengths.slice(0, 2).join('、') || '组合'}
          </span>
          {userSkipped && (
            <span
              className="inline-flex rounded-full bg-[#e5e7eb] px-2 py-0.5 text-[11px] font-[700] text-[#6b7280]"
            >
              已跳过
            </span>
          )}
          <span className="ml-auto text-[11px] font-[500] text-[#9ca3af]">
            {saving ? '保存中…' : ''}
          </span>
        </div>

        <label
          className={`mb-1 block text-[12px] font-[700] ${userSkipped ? 'text-[#9ca3af]' : 'text-[#6b7280]'}`}
        >
          假设方向
        </label>
        <textarea
          value={localHypothesis}
          onChange={(e) => setLocalHypothesis(e.target.value)}
          placeholder="我假设这个方向能带给我什么…"
          rows={4}
          className={`editor w-full resize-y rounded-[13px] border px-3.5 py-3 text-[13px] leading-[1.6] outline-none focus:border-[#7b68ff] focus:shadow-[0_0_0_3px_rgba(123,104,255,0.10)] ${
            userSkipped
              ? 'border-[rgba(109,121,176,0.10)] bg-[rgba(243,244,246,0.8)] text-[#9ca3af] line-through'
              : 'border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] text-[#334163]'
          }`}
        />
      </div>

      {/* 右侧占位（保持 grid 三列结构对齐） */}
      <div className="card-actions flex flex-shrink-0 flex-col items-end gap-4 text-[12px] text-[#77829f]" />

      {/* 底部操作按钮 */}
      <div
        className="col-span-full mt-1 flex items-center justify-end gap-2"
        style={{ gridColumn: '1 / 4' }}
      >
        {!userSkipped && (
          <button
            type="button"
            onClick={handleSkip}
            disabled={saving}
            className="small-btn rounded-[10px] border border-[rgba(101,86,239,0.24)] bg-white px-[18px] py-2 text-[13px] font-[700] text-[#6254eb] transition-transform hover:-translate-y-px disabled:opacity-50"
          >
            跳过
          </button>
        )}
        <button
          type="button"
          disabled={!canConfirm || saving}
          onClick={handleConfirm}
          className="small-btn primary rounded-[10px] border-0 px-[18px] py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
          style={{
            background: canConfirm ? 'linear-gradient(135deg,#7a64ff,#5d49ef)' : undefined,
          }}
        >
          {saving ? '保存中…' : userSkipped ? '确认（恢复）' : '确认'}
        </button>
      </div>
    </article>
  );
}
