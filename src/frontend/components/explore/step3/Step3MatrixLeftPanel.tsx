'use client';

import { useState, useCallback, useMemo } from 'react';
import { Check, SkipForward } from 'lucide-react';
import ComboMatrixFlowDiagram from './ComboMatrixSelector';
import ComboConclusionCard from './ComboConclusionCard';
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
            className="px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            我再看看
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-teal-500 text-white hover:bg-teal-600 transition-colors"
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
  onConfirm: () => void;
  onCancel: () => void;
  onDismissChange: (dismissed: boolean) => void;
  dismissed: boolean;
}) {
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
            checked={dismissed}
            onChange={(e) => onDismissChange(e.target.checked)}
            className="rounded border-gray-300"
          />
          不再提示
        </label>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-teal-500 text-white hover:bg-teal-600 transition-colors"
          >
            确认
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Step3MatrixLeftPanel({
  progress,
  matrix,
  activationCode,
  allMessages,
  selectedComboId,
  onSelectComboId,
  onSubmitAll,
  onProgressUpdate,
}: Step3MatrixLeftPanelProps) {
  const [conclusions, setConclusions] = useState(progress.combo_conclusions || {});
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [showCompletionModal, setShowCompletionModal] = useState(false);
  const [completedCount, setCompletedCount] = useState(0);
  const [pendingChipText, setPendingChipText] = useState<string | null>(null);

  const currentCombo = useMemo(
    () => (selectedComboId ? matrix.find((m) => m.combo_id === selectedComboId) : null),
    [matrix, selectedComboId],
  );

  // Messages for current combo (for extracting hyp candidates)
  const comboMessages = useMemo(
    () => allMessages.filter((m) => m.comboId === selectedComboId),
    [allMessages, selectedComboId],
  );

  // Extract latest hyp candidates from assistant messages
  const latestHypCandidates = useMemo(() => {
    for (let i = comboMessages.length - 1; i >= 0; i--) {
      const m = comboMessages[i];
      if (m.role === 'assistant' && m.hypCandidates && m.hypCandidates.length > 0) {
        return m.hypCandidates;
      }
    }
    return null;
  }, [comboMessages]);

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
          setConclusions(res.data.progress.combo_conclusions || {});
          onProgressUpdate(res.data.progress);
          setCompletedCount((prev) => prev + 1);
          if (!progress.combo_completion_modal_dismissed) {
            setShowCompletionModal(true);
          }
          // Auto-advance to next combo
          const nextIndex = matrix.findIndex((m) => m.combo_id === currentCombo.combo_id) + 1;
          if (nextIndex < matrix.length) {
            onSelectComboId(matrix[nextIndex].combo_id);
          }
        }
      } catch (e) {
        console.error('Failed to save conclusion:', e);
      }
    },
    [currentCombo, activationCode, matrix, progress, onProgressUpdate, onSelectComboId],
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
          setConclusions(res.data.progress.combo_conclusions || {});
          onProgressUpdate(res.data.progress);
          setCompletedCount((prev) => prev + 1);
          if (!progress.combo_completion_modal_dismissed) {
            setShowCompletionModal(true);
          }
          const nextIndex = matrix.findIndex((m) => m.combo_id === currentCombo.combo_id) + 1;
          if (nextIndex < matrix.length) {
            onSelectComboId(matrix[nextIndex].combo_id);
          }
        }
      } catch (e) {
        console.error('Failed to skip:', e);
      }
    },
    [currentCombo, activationCode, matrix, progress, onProgressUpdate, onSelectComboId],
  );

  const handleDismissChange = useCallback(
    async (dismissed: boolean) => {
      const { ruminationApi } = await import('@/lib/api/rumination');
      try {
        const res = await ruminationApi.save(activationCode, {
          combo_completion_modal_dismissed: dismissed,
        } as any);
        if (res.data?.progress) {
          onProgressUpdate(res.data.progress);
        }
      } catch (e) {
        console.error('Failed to update modal dismissed:', e);
      }
    },
    [activationCode, onProgressUpdate],
  );

  const handleChipClick = useCallback((chipText: string) => {
    setPendingChipText(chipText);
  }, []);

  // Classify for submit popup
  const { empty: emptyCombos, text_skipped: textSkipped, confirmed: confirmedCombos } =
    useMemo(() => {
      const result = { empty: 0, text_skipped: 0, confirmed: 0 };
      for (const item of matrix) {
        const c = conclusions[item.combo_id];
        if (c?.state === 'confirmed') result.confirmed++;
        else if (c?.state === 'skipped' && c.text) result.text_skipped++;
        else result.empty++;
      }
      return result;
    }, [matrix, conclusions]);

  const handleSubmitAll = useCallback(() => {
    setShowSubmitModal(true);
  }, []);

  const handleConfirmSubmit = useCallback(() => {
    setShowSubmitModal(false);
    onSubmitAll();
  }, [onSubmitAll]);

  const progressPct = matrix.length > 0 ? Math.round((completedCount / matrix.length) * 100) : 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Top bar: progress bar + submit */}
      <div className="shrink-0 mb-3">
        <div className="flex items-center justify-between mb-1.5">
          <div className="text-xs text-gray-500">
            已完成 {completedCount}/{matrix.length}
          </div>
          <button
            onClick={handleSubmitAll}
            className="px-3 py-1 rounded-lg text-xs font-medium bg-teal-500 text-white hover:bg-teal-600 transition-colors"
          >
            全部提交
          </button>
        </div>
        {/* Progress bar */}
        <div className="h-1 rounded-full bg-gray-200/60 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-teal-400 to-teal-500 transition-all duration-300"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Scrollable content area: matrix selector + conclusion card + chips */}
      <div className="flex-1 overflow-y-auto rumination-beautiful-table-scroll min-h-0">
        <ComboMatrixFlowDiagram
          matrix={matrix}
          conclusions={conclusions}
          selectedComboId={selectedComboId}
          onSelectCombo={onSelectComboId}
        />

        {/* Conclusion card */}
        {currentCombo && (
          <div className="mt-3">
            <ComboConclusionCard
              combo={currentCombo}
              conclusion={
                conclusions[currentCombo.combo_id] || {
                  text: '',
                  state: 'empty',
                }
              }
              pendingChipText={pendingChipText}
              onPendingChipConsumed={() => setPendingChipText(null)}
              onTextChange={() => {}}
              onConfirm={handleConfirm}
              onSkip={handleSkip}
            />
          </div>
        )}

        {/* Hyp candidates chips */}
        {latestHypCandidates && selectedComboId && currentCombo && (
          <div className="mt-3 pb-3">
            <div className="text-xs text-gray-400 mb-1.5">AI 生成的假设，点击填入结论卡</div>
            <div className="flex flex-wrap gap-1.5">
              {latestHypCandidates.map((chip, idx) => (
                <button
                  key={idx}
                  onClick={() => handleChipClick(chip)}
                  className="px-2.5 py-1 rounded-full text-xs border border-teal-300 bg-teal-50 text-teal-700 hover:bg-teal-100 transition-colors truncate max-w-[200px]"
                  title={chip}
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

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
        comboIndex={completedCount}
        totalCombos={matrix.length}
        onConfirm={() => setShowCompletionModal(false)}
        onCancel={() => setShowCompletionModal(false)}
        onDismissChange={handleDismissChange}
        dismissed={!!progress.combo_completion_modal_dismissed}
      />
    </div>
  );
}
