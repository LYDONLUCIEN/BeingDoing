'use client';

/**
 * v4 可编辑结论卡（极简版）
 *
 * 交互（2026-07-27 口径）：出卡 = 草案，不锁定对话；用户确认才锁定进终选池。
 * - 草案卡：展示态常显「跳过」「确认」；点击文本进编辑态（+「取消」）
 * - 已确认卡：展示态显示「✓ 已确认」+「再聊聊」；点「再聊聊」解锁继续聊
 *   （AI 上下文中会注入"用户对当前结论不满意"，卡保留待 AI 迭代覆盖）
 * - 跳过卡：删除线 + 灰色 + 「已跳过」标记；点文本进编辑态「确认（恢复）」
 * - PATCH 只传 hypothesis；不渲染/不提交 motivation/work_purposes 等后台字段
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
  /** 已确认（status=concluded 且未跳过）：对话锁定，展示「再聊聊」入口 */
  confirmed?: boolean;
}

/** 防御：dict 形态已废弃，统一转纯字符串 */
function hypToString(h: ConclusionCard['hypothesis']): string {
  if (!h) return '';
  if (typeof h === 'string') return h;
  return Object.values(h).filter(Boolean).join('\n');
}

export default function ConclusionCardEditable({ comboId, card, strengths, userSkipped, confirmed }: Props) {
  const { patchCard, setStatus } = useRuminationV4Store();
  const [localHypothesis, setLocalHypothesis] = useState<string>(hypToString(card.hypothesis));
  const [saving, setSaving] = useState(false);
  /** 默认展示态；点击文本进入编辑态 */
  const [editing, setEditing] = useState(false);

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
      setEditing(false); // 确认后消失编辑框，回到展示框
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async () => {
    setSaving(true);
    try {
      await setStatus(comboId, 'abandoned');
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setLocalHypothesis(hypToString(card.hypothesis));
    setEditing(false);
  };

  /** 「再聊聊」：解锁回 discussing，继续打磨草案（后端会注入不满意反馈给 AI） */
  const handleReopen = async () => {
    setSaving(true);
    try {
      await setStatus(comboId, 'discussing');
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
          <span className="ml-auto text-[11px] font-[500] text-[#9ca3af]">
            {saving ? '保存中…' : ''}
          </span>
        </div>

        <label
          className={`mb-1 block text-[12px] font-[700] ${userSkipped ? 'text-[#9ca3af]' : 'text-[#6b7280]'}`}
        >
          假设方向
        </label>
        {editing ? (
          <textarea
            value={localHypothesis}
            onChange={(e) => setLocalHypothesis(e.target.value)}
            placeholder="我假设这个方向能带给我什么…"
            rows={4}
            autoFocus
            className={`editor w-full resize-y rounded-[13px] border px-3.5 py-3 text-[13px] leading-[1.6] outline-none focus:border-[#7b68ff] focus:shadow-[0_0_0_3px_rgba(123,104,255,0.10)] ${
              userSkipped
                ? 'border-[rgba(109,121,176,0.10)] bg-[rgba(243,244,246,0.8)] text-[#9ca3af]'
                : 'border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] text-[#334163]'
            }`}
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            title="点击编辑"
            className={`group block w-full rounded-[13px] border px-3.5 py-3 text-left text-[13px] leading-[1.6] whitespace-pre-wrap transition-colors ${
              userSkipped
                ? 'border-[rgba(109,121,176,0.10)] bg-[rgba(243,244,246,0.8)] text-[#9ca3af] line-through'
                : 'border-[rgba(109,121,176,0.10)] bg-[rgba(250,251,255,0.65)] text-[#334163] hover:border-[#7b68ff] hover:bg-[rgba(250,251,255,0.95)]'
            }`}
          >
            {hypToString(card.hypothesis)}
            <span className="mt-1.5 block text-[11px] font-[500] text-[#9ca3af]">
              ✎ 点击文字可直接编辑
            </span>
          </button>
        )}
      </div>

      {/* 右侧占位（保持 grid 三列结构对齐） */}
      <div className="card-actions flex flex-shrink-0 flex-col items-end gap-4 text-[12px] text-[#77829f]" />

      {/* 底部操作区(2026-07-27 统一口径):
          左侧状态标签恒在(待确认/已确认/已跳过),编辑态也不消失;
          右侧:展示态 = 编辑 + 状态动作(草案:跳过+确认 / 已确认:再聊聊 / 已跳过:仅编辑);
               编辑态 = 只管编辑(取消 + 确认),状态动作请先退出编辑 */}
      <div
        className="col-span-full mt-1 flex items-center justify-between gap-2"
        style={{ gridColumn: '1 / 4' }}
      >
        {/* 左:状态标签 */}
        {userSkipped ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[#e5e7eb] px-2.5 py-1 text-[12px] font-[700] text-[#6b7280]">
            已跳过
          </span>
        ) : confirmed ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[#e8faf3] px-2.5 py-1 text-[12px] font-[700] text-[#02a475]">
            ✓ 已确认
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full bg-[#fff6e5] px-2.5 py-1 text-[12px] font-[700] text-[#b57908]">
            待确认
          </span>
        )}

        {/* 右:动作按钮 */}
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button
                type="button"
                onClick={handleCancel}
                disabled={saving}
                className="small-btn rounded-[10px] border border-[rgba(109,121,176,0.20)] bg-white px-[18px] py-2 text-[13px] font-[700] text-[#77829f] transition-transform hover:-translate-y-px disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="button"
                disabled={!canConfirm || saving}
                onClick={handleConfirm}
                className="small-btn primary rounded-[10px] border-0 px-[18px] py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
                style={{
                  background: canConfirm ? 'linear-gradient(135deg,#7a64ff,#5d49ef)' : undefined,
                }}
              >
                {saving ? '保存中…' : userSkipped ? '确认（恢复）' : confirmed ? '保存修改' : '确认'}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setEditing(true)}
                disabled={saving}
                className="small-btn rounded-[10px] border border-[rgba(109,121,176,0.20)] bg-white px-[14px] py-2 text-[13px] font-[700] text-[#77829f] transition-transform hover:-translate-y-px disabled:opacity-50"
              >
                ✎ 编辑
              </button>
              {!userSkipped && !confirmed && (
                <>
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
                      background: canConfirm ? 'linear-gradient(135deg,#7a64ff,#5d49ef)' : undefined,
                    }}
                  >
                    {saving ? '保存中…' : '确认'}
                  </button>
                </>
              )}
              {confirmed && !userSkipped && (
                <button
                  type="button"
                  onClick={handleReopen}
                  disabled={saving}
                  title="解锁对话,和 AI 继续打磨这张卡"
                  className="small-btn rounded-[10px] border-0 px-[18px] py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:opacity-50"
                  style={{ background: 'linear-gradient(135deg,#7a64ff,#5d49ef)' }}
                >
                  {saving ? '解锁中…' : '再聊聊'}
                </button>
              )}
            </>
          )}
        </div>
      </div>

    </article>
  );
}
