'use client';

import type { ReactNode } from 'react';
import type { PromptContentSegment } from '@/lib/api/admin';
import { PromptVariableTag } from './PromptVariableTag';

interface PromptContentRendererProps {
  segments?: PromptContentSegment[];
  content?: string;
  variableSamples?: Record<string, string>;
  muted?: boolean;
  highlightQuery?: string;
}

function highlightPlainText(text: string, query: string): ReactNode {
  const q = query.trim();
  if (!q) return text;
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
  return parts.map((part, i) =>
    part.toLowerCase() === q.toLowerCase() ? (
      <mark key={`h-${i}`} className="bg-yellow-200 dark:bg-yellow-700/60 text-inherit rounded-sm px-0.5">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

export function PromptContentRenderer({
  segments,
  content,
  variableSamples,
  muted = false,
  highlightQuery = '',
}: PromptContentRendererProps) {
  if (segments && segments.length > 0) {
    return (
      <pre
        className={`whitespace-pre-wrap font-mono text-[11px] leading-relaxed ${
          muted ? 'text-bd-subtle opacity-60' : 'text-bd-fg'
        }`}
      >
        {segments.map((seg, i) => {
          if (seg.type === 'variable' && seg.name) {
            return (
              <PromptVariableTag
                key={`${seg.name}-${i}`}
                name={seg.name}
                sample={variableSamples?.[seg.name]}
              />
            );
          }
          return <span key={`t-${i}`}>{highlightPlainText(seg.content || '', highlightQuery)}</span>;
        })}
      </pre>
    );
  }
  return (
    <pre
      className={`whitespace-pre-wrap font-mono text-[11px] leading-relaxed ${
        muted ? 'text-bd-subtle opacity-60' : 'text-bd-fg'
      }`}
    >
      {content ? highlightPlainText(content, highlightQuery) : '—'}
    </pre>
  );
}
