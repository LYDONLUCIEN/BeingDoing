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
  /** 子步 3：点击假设候选时的回调 */
  onHypCandidateClick?: (text: string) => void;
}

export default function MessageContent({
  content,
  className = '',
  markdown = true,
  colorMode = 'dark',
  hypCandidates,
  onHypCandidateClick,
}: MessageContentProps) {
  if (!content?.trim() && !hypCandidates?.length) {
    return null;
  }

  return (
    <div className={`message-content text-sm leading-relaxed ${className}`.trim()}>
      {content?.trim() ? (
        markdown ? (
          <MarkdownPreview
            source={preprocessMarkdown(content)}
            wrapperElement={{ 'data-color-mode': colorMode }}
            style={{ backgroundColor: 'transparent' }}
          />
        ) : (
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>
        )
      ) : null}
      {hypCandidates && hypCandidates.length > 0 && onHypCandidateClick && (
        <div className="mt-3 flex flex-wrap gap-2">
          {hypCandidates.map((cand, i) => (
            <span key={i} className="relative group inline-flex">
              <button
                type="button"
                onClick={() => onHypCandidateClick(cand)}
                className="inline-flex items-center rounded-lg border border-primary-300 bg-primary-50 px-3 py-1.5 text-xs font-medium text-primary-700 transition-colors hover:bg-primary-100 hover:border-primary-400 active:scale-[0.97] dark:border-primary-600 dark:bg-primary-900/30 dark:text-primary-300 dark:hover:bg-primary-900/50"
              >
                {cand.length > 40 ? cand.slice(0, 37) + '...' : cand}
              </button>
              <span
                role="tooltip"
                className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 max-w-xs -translate-x-1/2 whitespace-normal rounded-lg border border-neutral-100 bg-white px-3 py-2 text-left text-xs leading-relaxed text-neutral-700 shadow-lg opacity-0 transition-opacity group-hover:opacity-100 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200"
              >
                {cand}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
