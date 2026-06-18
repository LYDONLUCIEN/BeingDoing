'use client';

import { useState, useCallback, useEffect } from 'react';
import { Check, SkipForward, ChevronDown, ChevronUp } from 'lucide-react';
import type { ComboItem } from '@/lib/api/rumination';

interface ComboConclusionCardProps {
  combo: ComboItem;
  conclusion: { text: string; state: 'empty' | 'confirmed' | 'skipped' };
  /** Chip text to auto-fill into textarea */
  pendingChipText: string | null;
  onPendingChipConsumed: () => void;
  onTextChange: (text: string) => void;
  onConfirm: (text: string) => void;
  onSkip: (text: string) => void;
}

export default function ComboConclusionCard({
  combo,
  conclusion,
  pendingChipText,
  onPendingChipConsumed,
  onTextChange,
  onConfirm,
  onSkip,
}: ComboConclusionCardProps) {
  const [localText, setLocalText] = useState(conclusion.text);
  const [isExpanded, setIsExpanded] = useState(conclusion.state !== 'confirmed');

  const state = conclusion.state;
  const textLen = localText.length;
  const canConfirm = textLen >= 5;

  // Auto-fill chip text
  useEffect(() => {
    if (pendingChipText && (state === 'empty' || state === 'confirmed' && isExpanded)) {
      setLocalText(pendingChipText);
      onTextChange(pendingChipText);
      onPendingChipConsumed();
    }
  }, [pendingChipText, state, isExpanded, onTextChange, onPendingChipConsumed]);

  const handleTextChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setLocalText(e.target.value);
      onTextChange(e.target.value);
    },
    [onTextChange],
  );

  const handleConfirm = useCallback(() => {
    if (canConfirm) {
      onConfirm(localText);
    }
  }, [localText, canConfirm, onConfirm]);

  const handleSkip = useCallback(() => {
    onSkip(localText);
  }, [localText, onSkip]);

  const handleExpand = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  // Sync local text when conclusion changes externally (e.g. initial load)
  if (conclusion.text !== localText && !isExpanded) {
    setLocalText(conclusion.text);
  }

  return (
    <div
      className={`flex flex-col rounded-xl border-2 p-4 transition-all flex-1 min-h-0 ${
        state === 'skipped'
          ? 'border-gray-300 bg-gray-50'
          : state === 'confirmed' && !isExpanded
            ? 'border-teal-300 bg-teal-50'
            : 'border-gray-200 bg-white'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500">
            {combo.passion_name} × {combo.strength_name}
          </span>
          {state === 'confirmed' && !isExpanded && (
            <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-teal-100 text-teal-700 text-xs font-medium">
              <Check size={12} /> 已确认
            </span>
          )}
          {state === 'skipped' && (
            <span className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full bg-gray-200 text-gray-500 text-xs font-medium">
              <SkipForward size={12} /> 已跳过
            </span>
          )}
        </div>
        {state === 'confirmed' && (
          <button
            onClick={handleExpand}
            className="p-1 rounded hover:bg-gray-100 text-gray-400 transition-colors"
            title={isExpanded ? '收起' : '展开编辑'}
          >
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </div>

      {/* Textarea — flex-1 fills remaining space */}
      {(state === 'empty' || state === 'confirmed' || (state === 'skipped' && localText)) && (
        <textarea
          value={localText}
          onChange={handleTextChange}
          disabled={state === 'confirmed' && !isExpanded}
          placeholder="请输入你对这个组合的假设，描述一个具体可落地的方向..."
          className={`w-full flex-1 min-h-[40px] text-sm resize-none rounded-lg border p-3 transition-all ${
            state === 'skipped' && localText.trim()
              ? 'bg-gray-100 text-gray-400 border-gray-200 line-through'
              : state === 'skipped'
                ? 'bg-gray-100 text-gray-400 border-gray-200'
                : state === 'confirmed' && !isExpanded
                  ? 'bg-teal-50 text-teal-800 border-teal-200'
                  : 'bg-white text-gray-800 border-gray-200 focus:border-teal-400 focus:ring-1 focus:ring-teal-200'
          }`}
        />
      )}
      {state === 'skipped' && !localText && (
        <div className="flex-1 flex items-center justify-center text-sm text-gray-400 italic">
          此组合已跳过
        </div>
      )}

      {/* Action buttons — only show when editable */}
      {(state === 'empty' || isExpanded) && (
        <div className="flex items-center gap-2 mt-2 shrink-0">
          <button
            onClick={handleConfirm}
            disabled={!canConfirm}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              canConfirm
                ? 'bg-teal-500 text-white hover:bg-teal-600 active:bg-teal-700'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            <Check size={14} />
            确认
          </button>
          <button
            onClick={handleSkip}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium border border-gray-300 text-gray-500 hover:bg-gray-50 transition-all"
          >
            <SkipForward size={14} />
            跳过
          </button>
          <div className="flex-1" />
          <span className={`text-xs ${canConfirm ? 'text-teal-500' : 'text-gray-400'}`}>
            {textLen}/5 字
          </span>
        </div>
      )}
    </div>
  );
}
