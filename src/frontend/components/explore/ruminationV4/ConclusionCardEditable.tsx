'use client';

/**
 * v4 结论卡（2026-08-06 版，ADR-0015：用户主导填写 + 独立后台平衡点判定）
 *
 * 状态机：
 * - 草稿（无卡/未确认）：textarea 可直接编辑，[确认]（≥5 字）触发后台判定；[跳过]（有内容时）
 * - 分析中（balance_analysis.status=analyzing）：整卡锁定，显示「正在分析中…」
 * - 分析失败（failed）：错误提示 + [点击重试]
 * - 已判定（done）：判定灯（推荐=绿 / 不推荐=琥珀+理由 / 证据不足=灰），[重新编辑][再聊聊]
 * - 已跳过（user_skipped）：删除线 + 灰色，[确认（恢复）] 走正常确认+判定流程
 *
 * 聊/改即作废：重新编辑后再确认 = 新一轮判定；再聊聊 = 回对话继续打磨（旧判定作废）。
 */

import { useEffect, useState } from 'react';
import { Briefcase, Loader2 } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { BalanceAnalysis, ConclusionCard } from '@/lib/explore/ruminationV4Api';

interface Props {
  comboId: string;
  /** null = 空卡槽(结论卡常驻左栏,一开始就是空的) */
  card: ConclusionCard | null;
  /** 平衡点判定状态(null = 未判定) */
  analysis: BalanceAnalysis | null;
  strengths: string[];
  /** 用户已跳过(status=abandoned / user_skipped),卡保留、可逆 */
  userSkipped?: boolean;
}

/** 防御:旧 dict 形态已废弃,统一转纯字符串 */
function hypToString(h: ConclusionCard['hypothesis'] | undefined): string {
  if (!h) return '';
  if (typeof h === 'string') return h;
  return Object.values(h).filter(Boolean).join('\n');
}

function getToken(): string | undefined {
  return typeof window !== 'undefined' ? localStorage.getItem('token') || undefined : undefined;
}

export default function ConclusionCardEditable({ comboId, card, analysis, strengths, userSkipped }: Props) {
  const { patchCard, confirmCard, setStatus } = useRuminationV4Store();
  const [localHypothesis, setLocalHypothesis] = useState<string>(hypToString(card?.hypothesis));
  const [saving, setSaving] = useState(false);
  /** 已判定态下点「重新编辑」进入的编辑模式 */
  const [reediting, setReediting] = useState(false);

  useEffect(() => {
    setLocalHypothesis(hypToString(card?.hypothesis));
  }, [card?.hypothesis, card?.updated_at]);

  const analysisStatus = analysis?.status || null;
  const isAnalyzing = analysisStatus === 'analyzing';
  const isFailed = analysisStatus === 'failed';
  const isJudged = analysisStatus === 'done';
  const canConfirm = localHypothesis.trim().length >= 5;

  const handleConfirm = async () => {
    if (!canConfirm || saving) return;
    setSaving(true);
    try {
      await confirmCard(comboId, localHypothesis.trim(), getToken());
      setReediting(false);
    } finally {
      setSaving(false);
    }
  };

  const handleRetry = async () => {
    setSaving(true);
    try {
      await confirmCard(comboId, undefined, getToken());
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

  const handleReopen = async () => {
    setSaving(true);
    try {
      await setStatus(comboId, 'discussing');
    } finally {
      setSaving(false);
    }
  };

  const handleReeditCancel = () => {
    setLocalHypothesis(hypToString(card?.hypothesis));
    setReediting(false);
  };

  // ── 判定灯(已判定态)────────────────────────────────────────────
  const renderJudgeLight = () => {
    if (!isJudged) return null;
    if (analysis?.balance_found === true) {
      return (
        <span
          className="inline-flex items-center gap-1.5 rounded-full bg-[#e8faf3] px-2.5 py-1 text-[12px] font-[700] text-[#02a475]"
          title="后台分析:该方向通过了平衡点把关"
        >
          <span className="inline-block h-[8px] w-[8px] rounded-full bg-[#02c98d] shadow-[0_0_6px_rgba(2,201,141,0.55)]" />
          推荐
        </span>
      );
    }
    if (analysis?.balance_found === false) {
      return (
        <span
          className="inline-flex items-center gap-1.5 rounded-full bg-[#fff6e5] px-2.5 py-1 text-[12px] font-[700] text-[#b57908]"
          title={analysis.balance_fail_reason || '后台分析:该方向暂未通过平衡点把关'}
        >
          <span className="inline-block h-[8px] w-[8px] rounded-full bg-[#f5a623] shadow-[0_0_6px_rgba(245,166,35,0.5)]" />
          不推荐
        </span>
      );
    }
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full bg-[#eef0f4] px-2.5 py-1 text-[12px] font-[700] text-[#8a93a6]"
        title="现有探讨还不足以判断,可以「再聊聊」补充后重新确认"
      >
        <span className="inline-block h-[8px] w-[8px] rounded-full bg-[#b6bdc9]" />
        证据不足
      </span>
    );
  };

  const editing = !isJudged || reediting; // 草稿/跳过/重新编辑 = textarea 可编辑
  const locked = isAnalyzing;

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
          {renderJudgeLight()}
          <span className="ml-auto text-[11px] font-[500] text-[#9ca3af]">
            {saving && !isAnalyzing ? '保存中…' : ''}
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
            placeholder="把你们聊出的职业方向写在这里（角色、服务对象、具体动作、目的/价值），填好后点「确认」"
            rows={4}
            disabled={locked || saving}
            className={`editor w-full resize-y rounded-[13px] border px-3.5 py-3 text-[13px] leading-[1.6] outline-none focus:border-[#7b68ff] focus:shadow-[0_0_0_3px_rgba(123,104,255,0.10)] disabled:opacity-60 ${
              userSkipped
                ? 'border-[rgba(109,121,176,0.10)] bg-[rgba(243,244,246,0.8)] text-[#9ca3af]'
                : 'border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] text-[#334163]'
            }`}
          />
        ) : (
          <div
            className={`block w-full rounded-[13px] border px-3.5 py-3 text-left text-[13px] leading-[1.6] whitespace-pre-wrap ${
              userSkipped
                ? 'border-[rgba(109,121,176,0.10)] bg-[rgba(243,244,246,0.8)] text-[#9ca3af] line-through'
                : 'border-[rgba(109,121,176,0.10)] bg-[rgba(250,251,255,0.65)] text-[#334163]'
            }`}
          >
            {hypToString(card?.hypothesis)}
          </div>
        )}

        {/* 分析中提示 */}
        {isAnalyzing && (
          <p className="mt-2 flex items-center gap-1.5 text-[12px] font-[600] text-[#b57908]" role="status">
            <Loader2 size={13} className="animate-spin" />
            正在分析中，请稍后…（可以先去探索其他组合）
          </p>
        )}
        {/* 分析失败提示 */}
        {isFailed && (
          <p className="mt-2 text-[12px] font-[600] text-red-500" role="alert">
            分析失败{analysis?.error ? `：${analysis.error}` : ''}，请点击重试
          </p>
        )}
        {/* 不推荐理由 */}
        {isJudged && analysis?.balance_found === false && analysis.balance_fail_reason && (
          <p className="mt-2 text-[12px] font-[500] leading-relaxed text-[#b57908]">
            ⚠ {analysis.balance_fail_reason}
          </p>
        )}
      </div>

      {/* 右侧占位（保持 grid 三列结构对齐） */}
      <div className="card-actions flex flex-shrink-0 flex-col items-end gap-4 text-[12px] text-[#77829f]" />

      {/* 底部操作区 */}
      <div
        className="col-span-full mt-1 flex items-center justify-between gap-2"
        style={{ gridColumn: '1 / 4' }}
      >
        {/* 左:状态标签 */}
        {userSkipped ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[#e5e7eb] px-2.5 py-1 text-[12px] font-[700] text-[#6b7280]">
            已跳过
          </span>
        ) : isAnalyzing ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[#fff6e5] px-2.5 py-1 text-[12px] font-[700] text-[#b57908]">
            分析中
          </span>
        ) : isFailed ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[#fee2e2] px-2.5 py-1 text-[12px] font-[700] text-red-600">
            分析失败
          </span>
        ) : isJudged ? (
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
          {isAnalyzing ? null : isFailed ? (
            <button
              type="button"
              onClick={handleRetry}
              disabled={saving}
              className="small-btn primary rounded-[10px] border-0 px-[18px] py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:opacity-40"
              style={{ background: 'linear-gradient(135deg,#7a64ff,#5d49ef)' }}
            >
              {saving ? '重试中…' : '点击重试'}
            </button>
          ) : isJudged && !reediting ? (
            <>
              <button
                type="button"
                onClick={() => setReediting(true)}
                disabled={saving}
                className="small-btn rounded-[10px] border border-[rgba(109,121,176,0.20)] bg-white px-[14px] py-2 text-[13px] font-[700] text-[#77829f] transition-transform hover:-translate-y-px disabled:opacity-50"
              >
                ✎ 重新编辑
              </button>
              <button
                type="button"
                onClick={handleReopen}
                disabled={saving}
                title="回到对话,和 AI 继续打磨这个方向(原判定作废)"
                className="small-btn rounded-[10px] border-0 px-[18px] py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg,#7a64ff,#5d49ef)' }}
              >
                {saving ? '解锁中…' : '再聊聊'}
              </button>
            </>
          ) : (
            <>
              {reediting && (
                <button
                  type="button"
                  onClick={handleReeditCancel}
                  disabled={saving}
                  className="small-btn rounded-[10px] border border-[rgba(109,121,176,0.20)] bg-white px-[18px] py-2 text-[13px] font-[700] text-[#77829f] transition-transform hover:-translate-y-px disabled:opacity-50"
                >
                  取消
                </button>
              )}
              {!userSkipped && !reediting && hypToString(card?.hypothesis) && (
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
                title="确认后系统会为这个方向做一次最终把关分析"
                className="small-btn primary rounded-[10px] border-0 px-[18px] py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
                style={{
                  background: canConfirm ? 'linear-gradient(135deg,#7a64ff,#5d49ef)' : undefined,
                }}
              >
                {saving ? '提交中…' : userSkipped ? '确认（恢复）' : reediting ? '重新确认' : '确认'}
              </button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}
