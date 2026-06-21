'use client';

import { useState, useCallback, useMemo, useEffect } from 'react';
import { Check, SkipForward, ChevronDown, Ban } from 'lucide-react';
import ComboMatrixFlowDiagram from './ComboMatrixSelector';
import type { ComboItem, RuminationProgress } from '@/lib/api/rumination';
import type { ThreadMessage } from '@/lib/explore/threads';

interface Step3MatrixLeftPanelProps {
  progress: RuminationProgress;
  matrix: ComboItem[];
  activationCode: string;
  allMessages: ThreadMessage[];
  selectedComboId: string | null;
  onSelectComboId: (comboId: string | null) => void;
  onSubmitAll: () => void;
  onProgressUpdate: (progress: RuminationProgress) => void;
  /** 外部注入的 chip 文本（如右侧聊天区 chip 点击），自动填入结论卡片 */
  externalChipText: string | null;
  onExternalChipConsumed: () => void;
}

/** Modal: submit all confirmation */
function SubmitAllModal({
  open,
  emptyCount,
  textSkippedCount,
  confirmedCount,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  emptyCount: number;
  textSkippedCount: number;
  confirmedCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl p-6 max-w-md mx-4 shadow-xl">
        <h3 className="text-lg font-semibold text-gray-800 mb-3">确认提交</h3>
        <div className="space-y-2 text-sm text-gray-600 mb-5">
          <p>
            已确认 <span className="font-medium text-teal-700">{confirmedCount}</span> 个组合的假设。
          </p>
          {emptyCount > 0 && (
            <p className="text-amber-600">
              还有 <span className="font-medium">{emptyCount}</span> 个组合尚未填写，提交后将标记为跳过。
            </p>
          )}
          {textSkippedCount > 0 && (
            <p className="text-amber-600">
              <span className="font-medium">{textSkippedCount}</span> 个组合已输入内容但未确认，提交后将自动保存为已确认。
            </p>
          )}
          <p className="text-gray-500 text-xs">如果还有遗漏，可以继续进行探讨。</p>
        </div>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="h-11 rounded-full border border-gray-300 bg-white/56 px-5 text-[15px] font-[800] text-gray-600 shadow-[0_8px_24px_rgba(33,48,79,0.06)] transition-transform hover:-translate-y-[1px]"
          >
            我再看看
          </button>
          <button
            onClick={onConfirm}
            className="h-11 rounded-full border-0 px-5 text-[15px] font-[800] text-white shadow-[0_12px_24px_rgba(103,210,238,0.24)] transition-transform hover:-translate-y-[1px]"
            style={{ background: 'linear-gradient(135deg, #67dfda, #70c9ff)' }}
          >
            确认提交
          </button>
        </div>
      </div>
    </div>
  );
}

/** Modal: completion confirmation after confirm/skip */
function CompletionModal({
  open,
  comboIndex,
  totalCombos,
  onConfirm,
  onCancel,
  onDismissChange,
  dismissed,
}: {
  open: boolean;
  comboIndex: number;
  totalCombos: number;
  onConfirm: (dismissed: boolean) => void;
  onCancel: (dismissed: boolean) => void;
  onDismissChange: (dismissed: boolean) => void;
  dismissed: boolean;
}) {
  // 本地临时勾选状态，仅在用户点确认/取消时才提交到后端
  const [localDismissed, setLocalDismissed] = useState(dismissed);

  // 弹窗每次打开时，重置本地状态为后端当前值
  useEffect(() => {
    if (open) setLocalDismissed(dismissed);
  }, [open, dismissed]);

  if (!open || dismissed) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl p-6 max-w-md mx-4 shadow-xl">
        <h3 className="text-base font-semibold text-gray-800 mb-2">完成提示</h3>
        <p className="text-sm text-gray-600 mb-4">
          您已经完成了第 {comboIndex}/{totalCombos} 个优势组合的假设，我会按顺序为你展开下一条，你也可以自由切换查看。
        </p>
        <label className="flex items-center gap-2 text-sm text-gray-500 mb-4 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={localDismissed}
            onChange={(e) => setLocalDismissed(e.target.checked)}
            className="rounded border-gray-300"
          />
          不再提示
        </label>
        <div className="flex gap-3 justify-end">
          <button
            onClick={() => onCancel(localDismissed)}
            className="h-11 rounded-full border border-gray-300 bg-white/56 px-5 text-[15px] font-[800] text-gray-600 shadow-[0_8px_24px_rgba(33,48,79,0.06)] transition-transform hover:-translate-y-[1px]"
          >
            取消
          </button>
          <button
            onClick={() => onConfirm(localDismissed)}
            className="h-11 rounded-full border-0 px-5 text-[15px] font-[800] text-white shadow-[0_12px_24px_rgba(103,210,238,0.24)] transition-transform hover:-translate-y-[1px]"
            style={{ background: 'linear-gradient(135deg, #67dfda, #70c9ff)' }}
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}

/** Inline conclusion result card matching the reference HTML .result-card */
function ConclusionResultCard({
  combo,
  conclusion,
  pendingChipText,
  onPendingChipConsumed,
  onTextChange,
  onConfirm,
  onSkip,
  forceExpand,
  onForceExpandConsumed,
}: {
  combo: ComboItem;
  conclusion: { text: string; state: 'empty' | 'confirmed' | 'skipped' };
  pendingChipText: string | null;
  onPendingChipConsumed: () => void;
  onTextChange: (text: string) => void;
  onConfirm: (text: string) => void;
  onSkip: (text: string) => void;
  forceExpand?: boolean;
  onForceExpandConsumed?: () => void;
}) {
  const [localText, setLocalText] = useState(conclusion.text);
  const [isExpanded, setIsExpanded] = useState(false);

  const state = conclusion.state;
  const textLen = localText.length;
  const canConfirm = textLen >= 5;

  // forceExpand: 外部 chip 注入时自动展开
  useEffect(() => {
    if (forceExpand) {
      setIsExpanded(true);
      onForceExpandConsumed?.();
    }
  }, [forceExpand, onForceExpandConsumed]);

  // Auto-fill chip text
  // skipped 状态也允许 chip 注入：用户对已跳过的组合改主意时，可点 chip 快速填回。
  useEffect(() => {
    if (
      pendingChipText &&
      (state === 'empty' || state === 'skipped' || (state === 'confirmed' && isExpanded))
    ) {
      setLocalText(pendingChipText);
      onPendingChipConsumed();
    }
  }, [pendingChipText, state, isExpanded, onPendingChipConsumed]);

  // Sync external text when not actively editing
  useEffect(() => {
    if (conclusion.text !== localText && !isExpanded) {
      setLocalText(conclusion.text);
    }
  }, [conclusion.text, localText, isExpanded]);

  const handleConfirm = () => {
    if (canConfirm) onConfirm(localText);
  };

  const handleSkip = () => {
    onSkip(localText);
  };

  const isSkippedCollapsed = state === 'skipped' && !isExpanded;

  return (
    <div
      className={`
        relative flex flex-col rounded-[20px] backdrop-blur-[16px]
        transition-all duration-[0.22s] ease
        ${isExpanded ? 'px-5 pt-5 pb-4' : 'px-4 py-3.5'}
      `}
      style={{
        border: isSkippedCollapsed
          ? '1px solid rgba(200,200,200,0.35)'
          : '1px solid rgba(255,255,255,0.44)',
        boxShadow: isSkippedCollapsed
          ? '0 8px 16px rgba(150,150,150,0.08)'
          : '0 12px 24px rgba(155,135,234,0.10)',
        background: isSkippedCollapsed
          ? 'linear-gradient(135deg, rgba(220,220,220,0.26) 0%, rgba(230,230,230,0.18) 50%, rgba(225,225,225,0.14) 100%)'
          : 'radial-gradient(circle at 10% 15%, rgba(255,255,255,0.32), transparent 20%), ' +
            'linear-gradient(135deg, rgba(208,188,255,0.34) 0%, rgba(184,160,255,0.26) 30%, rgba(244,222,255,0.24) 65%, rgba(255,214,232,0.22) 100%)',
        opacity: isSkippedCollapsed ? 0.6 : 1,
      }}
    >
      {/* Main row: icon + copy */}
      <div className="flex items-center gap-4 w-full">
        <div
          className="flex h-[60px] w-[60px] flex-shrink-0 items-center justify-center rounded-full text-white text-[20px]"
          style={{
            background: isSkippedCollapsed
              ? 'linear-gradient(135deg, #c0c0c0 0%, #d0d0d0 54%, #e0e0e0 100%)'
              : 'linear-gradient(135deg, #77dbff 0%, #c09cff 54%, #ffb9c7 100%)',
            boxShadow: isSkippedCollapsed
              ? '0 8px 16px rgba(180,180,180,0.15)'
              : '0 12px 24px rgba(147,172,255,0.20)',
          }}
        >
          ✦
        </div>
        <div className="flex-1 min-w-0">
          {/* Header line: meta + toggle */}
          <div className="flex items-center justify-between gap-3 mb-1">
            <p className="m-0 text-[13px] font-[700] text-[#7b8794]">假设结果</p>
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className={`
                flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-full
                border border-white/54 bg-white/38 text-[#6d5cc9] text-[16px] font-[900]
                shadow-[inset_0_1px_0_rgba(255,255,255,0.48),0_6px_14px_rgba(104,84,190,0.10)]
                transition-all duration-[0.18s] ease hover:-translate-y-[1px] hover:bg-white/52
                ${isExpanded ? 'rotate-180' : ''}
              `}
            >
              ⌄
            </button>
          </div>

          {/* Body — read-only in collapsed, editable in expanded */}
          {state === 'confirmed' && !isExpanded ? (
            <p className="m-0 text-[14px] text-[#4b5563] leading-[1.8]">{localText}</p>
          ) : state === 'skipped' && !isExpanded && localText ? (
            <p className="m-0 text-[14px] text-[#9ca3af] leading-[1.8] line-through">{localText}</p>
          ) : (
            <textarea
              value={localText}
              onChange={(e) => setLocalText(e.target.value)}
              placeholder="请输入你对这个组合的假设，描述一个具体可落地的方向..."
              className={`
                w-full resize-none rounded-[14px] text-[14px] text-[#4b5563] leading-[1.8]
                outline-none transition-all duration-[0.18s] ease
                placeholder:text-[#b0b8c4]
                ${state === 'skipped' && !isExpanded ? 'text-[#9ca3af] line-through' : ''}
                ${isExpanded
                  ? 'min-h-[104px] p-2.5 bg-white/32 border border-white/42 shadow-[inset_0_1px_0_rgba(255,255,255,0.42)] focus:bg-white/48 focus:border-[rgba(180,153,255,0.52)] focus:shadow-[0_0_0_3px_rgba(180,153,255,0.12),inset_0_1px_0_rgba(255,255,255,0.48)]'
                  : 'min-h-[48px] border-0 p-0 bg-transparent'}
              `}
            />
          )}
        </div>
      </div>

      {/* Expanded area: edit hint + chips + action buttons */}
      <div
        className={`
          grid overflow-hidden
          transition-[grid-template-rows,opacity,margin-top] duration-[0.24s] ease
          ${isExpanded ? 'grid-rows-[1fr] opacity-100 mt-4' : 'grid-rows-[0fr] opacity-0 mt-0'}
        `}
      >
        <div className="overflow-hidden flex flex-col gap-3 pt-0.5">
          {/* Action buttons */}
          <div className="flex items-center justify-end gap-3">
            <span className="mr-auto text-[13px] font-[700] text-[#8b7cb8]">
              {isExpanded ? '可直接编辑结论文字' : ''}
            </span>
            <button
              onClick={handleSkip}
              className="h-[42px] rounded-full border border-white/48 bg-white/42 px-[18px] text-[14px] font-[800] text-[#6b7280] cursor-pointer shadow-[0_8px_24px_rgba(33,48,79,0.06)] transition-transform hover:-translate-y-[1px]"
            >
              跳过
            </button>
            <button
              onClick={handleConfirm}
              disabled={!canConfirm}
              className="h-[42px] rounded-full border-0 px-[18px] text-[14px] font-[800] text-white cursor-pointer transition-transform hover:-translate-y-[1px] disabled:opacity-40 disabled:cursor-not-allowed"
              style={{
                background: canConfirm
                  ? 'linear-gradient(135deg, #b499ff, #f39ad5)'
                  : undefined,
                boxShadow: canConfirm
                  ? '0 10px 20px rgba(180,153,255,0.20)'
                  : undefined,
              }}
            >
              确认这个结论
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Step3MatrixLeftPanel({
  progress,
  matrix,
  activationCode,
  selectedComboId,
  onSelectComboId,
  onSubmitAll,
  onProgressUpdate,
  externalChipText,
  onExternalChipConsumed,
}: Step3MatrixLeftPanelProps) {
  const [conclusions, setConclusions] = useState(progress.combo_conclusions || {});
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [showCompletionModal, setShowCompletionModal] = useState(false);
  const [passionAllDisabled, setPassionAllDisabled] = useState(false);
  const [pendingChipText, setPendingChipText] = useState<string | null>(null);
  const [forceExpand, setForceExpand] = useState(false);

  // 当外部 progress.combo_conclusions 变化（如重新进入 step3 被后端清空）时同步到本地 state
  useEffect(() => {
    setConclusions(progress.combo_conclusions || {});
  }, [progress.combo_conclusions, progress.combo_matrix]);

  // 外部 chip 文本注入（右侧聊天区 chip 点击）
  useEffect(() => {
    if (externalChipText) {
      setForceExpand(true);
      setPendingChipText(externalChipText);
      onExternalChipConsumed();
    }
  }, [externalChipText, onExternalChipConsumed]);

  const currentCombo = useMemo(
    () => (selectedComboId ? matrix.find((m) => m.combo_id === selectedComboId) : null),
    [matrix, selectedComboId],
  );

  // 仅含可操作的组合（排除不匹配），用于"下一个 combo"导航（afterSave）
  const matchableCombos = useMemo(
    () => matrix.filter((m) => !m.is_non_matching),
    [matrix],
  );

  // matchable 总数（进度分母）：优先读后端 meta，老数据回退到前端 filter 长度
  const totalMatchable = progress.combo_matrix_meta?.total_matchable ?? matchableCombos.length;

  // 已完成组合数（confirmed + skipped），与矩阵 ✓ 标记同口径；派生值，无累加器时序问题
  const doneCount = useMemo(
    () =>
      matchableCombos.filter(
        (c) =>
          conclusions[c.combo_id]?.state === 'confirmed' ||
          conclusions[c.combo_id]?.state === 'skipped',
      ).length,
    [matchableCombos, conclusions],
  );

  // 保存结论后的通用后处理：立即切下一个 combo，弹窗仅作提示
  const afterSave = useCallback(
    (comboId: string, resProgress: any) => {
      setConclusions(resProgress.combo_conclusions || {});
      onProgressUpdate(resProgress);
      // 立即切换到下一个 matchable combo（不依赖弹窗/pendingNextComboId）
      const curIdx = matchableCombos.findIndex((m) => m.combo_id === comboId);
      const nextIdx = curIdx + 1;
      if (nextIdx < matchableCombos.length) {
        onSelectComboId(matchableCombos[nextIdx].combo_id);
      }
      // nextIdx 越界（当前是最后一个）→ 留在当前 combo，不切
      // 弹窗仅作提示，独立弹出
      if (!progress.combo_completion_modal_dismissed) {
        setShowCompletionModal(true);
      }
    },
    [progress.combo_completion_modal_dismissed, onProgressUpdate, matchableCombos, onSelectComboId],
  );

  const handleConfirm = useCallback(
    async (text: string) => {
      if (!currentCombo) return;
      const { ruminationApi } = await import('@/lib/api/rumination');
      try {
        const res = await ruminationApi.saveComboConclusion(
          activationCode,
          currentCombo.combo_id,
          'confirm',
          text,
        );
        if (res.data?.progress) {
          afterSave(currentCombo.combo_id, res.data.progress);
        }
      } catch (e) {
        console.error('Failed to save conclusion:', e);
      }
    },
    [currentCombo, activationCode, afterSave],
  );

  const handleSkip = useCallback(
    async (text: string) => {
      if (!currentCombo) return;
      const { ruminationApi } = await import('@/lib/api/rumination');
      try {
        const res = await ruminationApi.saveComboConclusion(
          activationCode,
          currentCombo.combo_id,
          'skip',
          text,
        );
        if (res.data?.progress) {
          afterSave(currentCombo.combo_id, res.data.progress);
        }
      } catch (e) {
        console.error('Failed to skip:', e);
      }
    },
    [currentCombo, activationCode, afterSave],
  );

  const handleDismissChange = useCallback(
    async (dismissed: boolean) => {
      const { ruminationApi } = await import('@/lib/api/rumination');
      try {
        const res = await ruminationApi.save(activationCode, {
          combo_completion_modal_dismissed: dismissed,
        });
        if (res.data?.progress) {
          onProgressUpdate(res.data.progress);
        }
      } catch (e) {
        console.error('Failed to update modal dismissed:', e);
      }
    },
    [activationCode, onProgressUpdate],
  );

  const handleDisabledStrengthClick = useCallback(() => {
    // 简单内联提示：用 state 驱动 toast
    setDisabledToast(true);
  }, []);

  const [disabledToast, setDisabledToast] = useState(false);
  useEffect(() => {
    if (disabledToast) {
      const t = setTimeout(() => setDisabledToast(false), 2000);
      return () => clearTimeout(t);
    }
  }, [disabledToast]);

  const { empty: emptyCombos, text_skipped: textSkipped, confirmed: confirmedCombos } =
    useMemo(() => {
      const result = { empty: 0, text_skipped: 0, confirmed: 0 };
      for (const item of matchableCombos) {
        const c = conclusions[item.combo_id];
        if (c?.state === 'confirmed') result.confirmed++;
        else if (c?.state === 'skipped' && c.text) result.text_skipped++;
        else result.empty++;
      }
      return result;
    }, [matchableCombos, conclusions]);

  const handleSubmitAll = useCallback(() => {
    setShowSubmitModal(true);
  }, []);

  const handleConfirmSubmit = useCallback(() => {
    setShowSubmitModal(false);
    onSubmitAll();
  }, [onSubmitAll]);

  const progressPct = totalMatchable > 0 ? Math.round((doneCount / totalMatchable) * 100) : 0;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 relative">
      {/* Toast: 不匹配提示 */}
      {disabledToast && (
        <div
          className="absolute top-2 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5
            rounded-full px-3.5 py-2 text-[13px] font-[700] text-[#6b7280]
            border border-white/40 bg-white/80 shadow-[0_8px_20px_rgba(33,48,79,0.10)]
            backdrop-blur-[12px] animate-in fade-in duration-200"
        >
          <Ban size={14} className="text-[#b0b8c4]" />
          该组合已标记为不匹配
        </div>
      )}
      {/* Header row: icon + title (left), progress (center), submit (right) — all on one line */}
      <div className="flex items-center justify-between gap-4 shrink-0 px-1">
        {/* Left: icon + title + subtitle */}
        <div className="flex items-center gap-2">
          <div
            className="h-5 w-5 flex-shrink-0 rounded-[6px] mt-0.5 self-start"
            style={{
              background:
                'conic-gradient(from 160deg, #ffb76d, #f2df6d, #7be6c8, #69bdf6, #b697ff, #ffb76d)',
              boxShadow: '0 5px 12px rgba(105, 189, 246, 0.14)',
            }}
          />
          <div>
            <h2 className="m-0 text-base font-extrabold text-[#1f2937]">你的方向</h2>
            <p className="m-0 text-[11px] text-[#5e6978] leading-snug">
              自由组合热爱与优势，推断可能的方向。
            </p>
          </div>
        </div>
        {/* Center: progress bar + count — flex-1 with inner centering */}
        <div className="flex-1 flex items-center justify-center gap-2 min-w-0">
          <div className="h-3.5 w-28 rounded-full overflow-hidden bg-white/56 shadow-[inset_0_1px_0_rgba(255,255,255,0.55)]">
            <div
              className="h-full rounded-full"
              style={{
                width: `${progressPct}%`,
                background: 'linear-gradient(90deg, #8f73ff 0%, #9a75ff 45%, #f59ac0 100%)',
                boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.4)',
              }}
            />
          </div>
          <span className="text-[13px] font-[700] text-[#6b7280] shrink-0">
            {doneCount}/{totalMatchable}
          </span>
        </div>
        {/* Right: submit all */}
        <button
          onClick={handleSubmitAll}
          className="h-9 rounded-full border-0 px-4 text-[14px] font-[800] text-white shadow-[0_10px_20px_rgba(17,24,39,0.18)] transition-transform hover:-translate-y-[1px] shrink-0"
          style={{ background: 'rgba(17,24,39,0.92)' }}
        >
          全部提交
        </button>
      </div>

      {/* Selection box: glass card with button grid + summary */}
      <div
        className="rounded-[20px] p-2.5 backdrop-blur-[18px] border border-white/38 shrink-0"
        style={{
          background:
            'linear-gradient(135deg, rgba(255,245,248,0.22) 0%, rgba(255,250,241,0.18) 20%, rgba(245,239,255,0.20) 54%, rgba(237,255,247,0.18) 100%)',
        }}
      >
        <ComboMatrixFlowDiagram
          matrix={matrix}
          meta={progress.combo_matrix_meta}
          conclusions={conclusions}
          selectedComboId={selectedComboId}
          onSelectCombo={onSelectComboId}
          onDisabledStrengthClick={handleDisabledStrengthClick}
          onPassionAllDisabledChange={setPassionAllDisabled}
        />
      </div>

      {/* Result card — flex-1 fills remaining space */}
      {currentCombo ? (
        <div className="flex-1 flex flex-col min-h-0 overflow-y-auto rumination-hyp-preview-scroll">
          <ConclusionResultCard
            key={currentCombo.combo_id}
            combo={currentCombo}
            conclusion={
              conclusions[currentCombo.combo_id] || { text: '', state: 'empty' }
            }
            pendingChipText={pendingChipText}
            onPendingChipConsumed={() => setPendingChipText(null)}
            onTextChange={() => {}}
            onConfirm={handleConfirm}
            onSkip={handleSkip}
            forceExpand={forceExpand}
            onForceExpandConsumed={() => setForceExpand(false)}
          />
        </div>
      ) : passionAllDisabled ? (
        <div className="flex flex-1 items-center justify-center rounded-[20px] border border-dashed border-white/44 bg-white/20 px-6 text-center text-[14px] font-[700] text-[#9ca3af]">
          该热爱暂无组合可探讨，可切换其他热爱
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center rounded-[20px] border border-dashed border-white/44 bg-white/20 text-[14px] font-[700] text-[#9ca3af]">
          请在上方选择热爱与优势
        </div>
      )}

      {/* Modals */}
      <SubmitAllModal
        open={showSubmitModal}
        emptyCount={emptyCombos}
        textSkippedCount={textSkipped}
        confirmedCount={confirmedCombos}
        onConfirm={handleConfirmSubmit}
        onCancel={() => setShowSubmitModal(false)}
      />
      <CompletionModal
        open={showCompletionModal}
        comboIndex={doneCount}
        totalCombos={totalMatchable}
        onConfirm={(localDismissed) => {
          setShowCompletionModal(false);
          // 仅当本地勾选结果与后端当前值不一致时才提交
          if (localDismissed !== !!progress.combo_completion_modal_dismissed) {
            handleDismissChange(localDismissed);
          }
        }}
        onCancel={(localDismissed) => {
          setShowCompletionModal(false);
          if (localDismissed !== !!progress.combo_completion_modal_dismissed) {
            handleDismissChange(localDismissed);
          }
        }}
        onDismissChange={handleDismissChange}
        dismissed={!!progress.combo_completion_modal_dismissed}
      />
    </div>
  );
}
