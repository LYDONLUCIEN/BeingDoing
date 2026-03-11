'use client';

import { useState } from 'react';
import { Copy, RefreshCw, ThumbsUp } from 'lucide-react';
import MessageContent from './MessageContent';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { recordLike } from '@/lib/api/analytics';

type PhaseClass = 'values' | 'strength' | 'interest' | 'purpose';

function formatMessageTime(ms: number): string {
  const d = new Date(ms);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

interface FlowAiMessageProps {
  content: string;
  phase: PhaseClass;
  /** 是否流式输出中（显示光标） */
  streaming?: boolean;
  /** 消息时间戳（Unix ms） */
  timestamp?: number;
  onCopy?: () => void;
  onRegenerate?: () => void;
  /** 埋点：session_id、log_index、dimension，点赞时上报 */
  sessionId?: string;
  logIndex?: number;
  dimension?: string;
}

/**
 * 复刻 llmchat：AI 消息无气泡，左侧色条 + 工具栏（复制、重新生成、点赞）
 */
export default function FlowAiMessage({
  content,
  phase,
  streaming = false,
  timestamp,
  onCopy,
  onRegenerate,
  sessionId,
  logIndex,
  dimension,
}: FlowAiMessageProps) {
  const [liked, setLiked] = useState(false);

  const handleCopy = () => {
    copyToClipboard(content).then((ok) => ok && onCopy?.());
  };

  const handleLike = () => {
    const next = !liked;
    setLiked(next);
    if (next && sessionId != null && logIndex != null) {
      recordLike({
        session_id: sessionId,
        log_index: logIndex,
        content_preview: content?.slice(0, 200) || undefined,
        dimension: dimension || phase,
      }).catch(() => {});
    }
  };

  return (
    <div className="flow-msg-ai-wrap">
      {timestamp !== undefined && (
        <span className="flow-msg-time text-[10px] text-[var(--flow-text-muted)] mb-1">
          {formatMessageTime(timestamp)}
        </span>
      )}
      <div className={`flow-msg-ai-content ${phase}`}>
        <MessageContent content={content} markdown colorMode="light" />
        {streaming && <span className="flow-stream-cursor" aria-hidden />}
      </div>
      <div className="flow-msg-ai-toolbar">
        <button
          type="button"
          className="flow-toolbar-btn"
          title="复制"
          onClick={handleCopy}
        >
          <Copy size={14} strokeWidth={1.6} />
        </button>
        {onRegenerate && (
          <button
            type="button"
            className="flow-toolbar-btn"
            title="重新生成"
            onClick={onRegenerate}
          >
            <RefreshCw size={14} strokeWidth={1.6} />
          </button>
        )}
        <button
          type="button"
          className={`flow-toolbar-btn ${liked ? 'liked' : ''}`}
          title="点赞"
          onClick={handleLike}
        >
          <ThumbsUp size={14} strokeWidth={1.6} />
        </button>
      </div>
    </div>
  );
}
