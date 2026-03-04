'use client';

import MarkdownPreview from '@uiw/react-markdown-preview';

interface MessageContentProps {
  content: string;
  className?: string;
  /** 是否使用 Markdown 渲染（助手消息默认 true，用户回答可选用） */
  markdown?: boolean;
  /** light: flow 页浅色主题下的 Markdown 配色 */
  colorMode?: 'dark' | 'light';
}

export default function MessageContent({
  content,
  className = '',
  markdown = true,
  colorMode = 'dark',
}: MessageContentProps) {
  if (!content?.trim()) {
    return null;
  }

  if (!markdown) {
    return <p className={`whitespace-pre-wrap text-sm leading-relaxed ${className}`}>{content}</p>;
  }

  return (
    <div className={`message-content text-sm leading-relaxed ${className}`.trim()}>
      <MarkdownPreview
        source={content}
        wrapperElement={{ 'data-color-mode': colorMode }}
        style={{ backgroundColor: 'transparent' }}
      />
    </div>
  );
}
