'use client';

import MarkdownPreview from '@uiw/react-markdown-preview';
import { preprocessMarkdown } from '@/lib/mdPreprocess';

interface MessageContentProps {
  content: string;
  className?: string;
  /** 是否使用 Markdown 渲染（助手消息默认 true，用户回答可选用） */
  markdown?: boolean;
  /** light: flow 页浅色主题下的 Markdown 配色 */
  colorMode?: 'dark' | 'light';
  /** 子步 3：假设候选列表，渲染为可点击 chip */
  hypCandidates?: string[];
  /** 子步 3：假设目标行（0-based） */
  hypTargetRow?: number;
  /** 子步 3：有候选但未能确定目标行 */
  hypRowUnresolved?: boolean;
  /** 子步 3：用户点选表格行后作为填入目标（仅 hypRowUnresolved 时生效） */
  selectedRowFallback?: number | null;
  /** 子步 3：点击假设候选时的回调 */
  onHypCandidateClick?: (
    text: string,
    meta: { hypTargetRow?: number; hypRowUnresolved?: boolean }
  ) => void;
  /** step3 matrix 模式：chips 始终可点击，无需选择表格行 */
  comboMatrixMode?: boolean;
}

const HYP_ROW_UNRESOLVED_HINT =
  '未能确定目标行，请点击左侧表格对应行后再聊，或点该行「重新生成」以生成假设。';

const hypRowSelectedHint = (rowIndex: number) =>
  `已选中左侧第 ${rowIndex + 1} 行，可点击下方假设填入。`;

/**
 * 清除后端隐藏协议块标签，防止泄露到 UI。
 */
function stripHiddenBlocks(text: string): string {
  return text
    .replace(/\[STEP3_HYP_JSON\][\s\S]*?\[\/STEP3_HYP_JSON\]/g, '')
    .replace(/\[HYP_CANDIDATE\][\s\S]*?\[\/HYP_CANDIDATE\]/g, '')
    .replace(/\[ROW_STATE_JSON\][\s\S]*?\[\/ROW_STATE_JSON\]/g, '')
    .replace(/\[STATE_JSON\][\s\S]*?\[\/STATE_JSON\]/g, '')
    .trim();
}

export default function MessageContent({
  content,
  className = '',
  markdown = true,
  colorMode = 'dark',
  hypCandidates,
  hypTargetRow,
  hypRowUnresolved,
  selectedRowFallback,
  onHypCandidateClick,
  comboMatrixMode,
}: MessageContentProps) {
  const safeContent = stripHiddenBlocks(content || '');
  if (!safeContent && !hypCandidates?.length) {
    return null;
  }

  const effectiveTargetRow =
    hypTargetRow ??
    (hypRowUnresolved && selectedRowFallback != null ? selectedRowFallback : undefined);
  const chipsDisabled = comboMatrixMode
    ? false
    : hypCandidates?.length ? effectiveTargetRow == null : false;
  const chipMeta = {
    hypTargetRow: effectiveTargetRow,
    hypRowUnresolved: hypRowUnresolved && effectiveTargetRow == null,
  };
  const rowHint = comboMatrixMode
    ? null
    : hypRowUnresolved && effectiveTargetRow == null
        ? HYP_ROW_UNRESOLVED_HINT
        : hypRowUnresolved && effectiveTargetRow != null
          ? hypRowSelectedHint(effectiveTargetRow)
          : null;

  return (
    <div className={`message-content text-sm leading-relaxed ${className}`.trim()}>
      {safeContent ? (
        markdown ? (
          <MarkdownPreview
            source={preprocessMarkdown(safeContent)}
            wrapperElement={{ 'data-color-mode': colorMode }}
            style={{ backgroundColor: 'transparent' }}
          />
        ) : (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{safeContent}</p>
        )
      ) : null}
      {hypCandidates && hypCandidates.length > 0 && onHypCandidateClick && (
        <div className="mt-3">
          {rowHint && (
            <p
              className={`mb-2 text-xs leading-relaxed ${
                chipsDisabled
                  ? 'text-amber-800/90 dark:text-amber-200/90'
                  : 'text-primary-700/90 dark:text-primary-300/90'
              }`}
              role="status"
            >
              {rowHint}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {hypCandidates.map((cand, i) => (
              <span key={i} className="relative group inline-flex">
                <button
                  type="button"
                  disabled={chipsDisabled}
                  onClick={() => {
                    if (chipsDisabled) return;
                    onHypCandidateClick(cand, chipMeta);
                  }}
                  className={`inline-flex items-center rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors active:scale-[0.97] ${
                    chipsDisabled
                      ? 'cursor-not-allowed border-neutral-200 bg-neutral-50 text-neutral-400 dark:border-neutral-700 dark:bg-neutral-800/40 dark:text-neutral-500'
                      : 'border-primary-300 bg-primary-50 text-primary-700 hover:bg-primary-100 hover:border-primary-400 dark:border-primary-600 dark:bg-primary-900/30 dark:text-primary-300 dark:hover:bg-primary-900/50'
                  }`}
                >
                  {cand.length > 40 ? cand.slice(0, 37) + '...' : cand}
                </button>
                {!chipsDisabled && (
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 max-w-xs -translate-x-1/2 whitespace-normal rounded-lg border border-neutral-100 bg-white px-3 py-2 text-left text-xs leading-relaxed text-neutral-700 shadow-lg opacity-0 transition-opacity group-hover:opacity-100 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200"
                  >
                    {cand}
                  </span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
