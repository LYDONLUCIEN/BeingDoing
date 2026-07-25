'use client';

/**
 * v4 假设候选 chips 选择器
 *
 * 渲染在输入区上方，三选项：[假设A][假设B][✏️ 自己写]
 * - 点 A/B → 该文本作为用户消息发送（走现有 combo-chat 发送链路）
 * - 点 C → 展开内联输入框 + 提交按钮 → 提交内容作为用户消息发送
 *
 * 见 wiki/开发文档/7-25-rumination-v4-实施口径.md §3.1
 */

import { useState } from 'react';
import { PenLine } from 'lucide-react';

interface Props {
  candidates: string[];
  /** 流式中/只读时禁用点击 */
  disabled?: boolean;
  /** 把文本作为用户消息发送 */
  onSend: (text: string) => void;
}

export default function V4HypChipsSelector({ candidates, disabled, onSend }: Props) {
  const [customOpen, setCustomOpen] = useState(false);
  const [customText, setCustomText] = useState('');

  if (!candidates.length) return null;

  const submitCustom = () => {
    const text = customText.trim();
    if (!text || disabled) return;
    setCustomText('');
    setCustomOpen(false);
    onSend(text);
  };

  return (
    <div className="w-full shrink-0 px-1 pb-1.5" role="group" aria-label="假设方向候选">
      <p className="mb-1.5 text-xs leading-snug text-neutral-500">
        选一个假设方向，或写下你自己的想法：
      </p>
      <div className="flex flex-wrap gap-2">
        {candidates.map((cand, i) => (
          <span key={i} className="group relative inline-flex">
            <button
              type="button"
              disabled={disabled}
              onClick={() => !disabled && onSend(cand)}
              className={`inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors active:scale-[0.97] ${
                disabled
                  ? 'cursor-not-allowed border-neutral-200 bg-neutral-50 text-neutral-400'
                  : 'border-[#c9befb] bg-[#f4f1ff] text-[#5d49ef] hover:border-[#a594f7] hover:bg-[#ece7ff]'
              }`}
            >
              {cand.length > 40 ? cand.slice(0, 37) + '...' : cand}
            </button>
            {!disabled && (
              <span
                role="tooltip"
                className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 max-w-xs -translate-x-1/2 whitespace-normal rounded-lg border border-neutral-100 bg-white px-3 py-2 text-left text-xs leading-relaxed text-neutral-700 opacity-0 shadow-lg transition-opacity group-hover:opacity-100"
              >
                {cand}
              </span>
            )}
          </span>
        ))}
        <button
          type="button"
          disabled={disabled}
          onClick={() => setCustomOpen((v) => !v)}
          className={`inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors active:scale-[0.97] ${
            disabled
              ? 'cursor-not-allowed border-neutral-200 bg-neutral-50 text-neutral-400'
              : customOpen
                ? 'border-[#a594f7] bg-[#ece7ff] text-[#5d49ef]'
                : 'border-dashed border-[#c9befb] bg-white/70 text-[#5d49ef] hover:bg-[#f4f1ff]'
          }`}
        >
          <PenLine size={12} strokeWidth={2} />
          自己写
        </button>
      </div>

      {customOpen && (
        <div className="mt-2 flex items-end gap-2">
          <textarea
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitCustom();
              }
            }}
            placeholder="写下你自己的假设方向…"
            rows={2}
            autoFocus
            className="min-w-0 flex-1 resize-y rounded-[13px] border border-[rgba(109,121,176,0.16)] bg-[rgba(250,251,255,0.92)] px-3 py-2 text-[13px] leading-[1.6] text-[#334163] outline-none focus:border-[#7b68ff] focus:shadow-[0_0_0_3px_rgba(123,104,255,0.10)]"
          />
          <button
            type="button"
            disabled={disabled || !customText.trim()}
            onClick={submitCustom}
            className="shrink-0 rounded-[10px] border-0 px-4 py-2 text-[13px] font-[700] text-white transition-transform hover:-translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: 'linear-gradient(135deg,#7a64ff,#5d49ef)' }}
          >
            提交
          </button>
        </div>
      )}
    </div>
  );
}
