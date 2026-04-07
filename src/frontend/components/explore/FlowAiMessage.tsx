'use client';

import { useState, useEffect } from 'react';
import { Copy, ThumbsUp } from 'lucide-react';
import MessageContent from './MessageContent';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { recordLike } from '@/lib/api/analytics';
import { useLocale } from '@/hooks/useLocale';

type PhaseClass = 'values' | 'strength' | 'interest' | 'purpose' | 'rumination';

function formatMessageTime(ms: number): string {
  const d = new Date(ms);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

/** 思考流式片段压成单行展示（不换行、不泄露完整推理） */
function thinkChunkSingleLine(raw: string): string {
  const s = raw.replace(/\r\n|\n/g, ' ').replace(/\s+/g, ' ').trim();
  return s || '\u00A0';
}

interface FlowAiMessageProps {
  content: string;
  phase: PhaseClass;
  /** 沉淀工作台右栏：磨砂气泡；careeringMatte：前四维 newchat6 哑光 + 顶栏 meta */
  variant?: 'default' | 'ruminationWorkbench' | 'careeringMatte';
  /** careeringMatte 时 AI 身份文案，如「AI 职业教练」 */
  careeringAiRoleLabel?: string;
  /** 是否流式输出中 */
  streaming?: boolean;
  /** @deprecated 思考全文不再展示，保留字段仅为类型兼容 */
  thinkContent?: string;
  /** 思考中占位（流式时显示） */
  thinkStreaming?: boolean;
  /** 思考过程实时输出预览（单行、无换行） */
  thinkChunkContent?: string;
  /** 思考过程占位文案（轮流展示） */
  thinkPlaceholders?: string[];
  /** @deprecated 思考结果已隐藏 */
  thinkLabel?: string;
  /** 消息时间戳（Unix ms） */
  timestamp?: number;
  onCopy?: () => void;
  /** 埋点：session_id、log_index、dimension，点赞时上报 */
  sessionId?: string;
  logIndex?: number;
  dimension?: string;
  toolbarCopyTitle?: string;
  toolbarLikeTitle?: string;
  /** 为 true 时不显示底部复制/点赞条（如静态引导文案） */
  hideToolbar?: boolean;
}

/**
 * AI 消息气泡 + 工具栏。思考过程仅流式阶段显示单行状态，结束后不保留/不展示推理全文，避免提示词泄露。
 */
export default function FlowAiMessage({
  content,
  phase,
  variant = 'default',
  careeringAiRoleLabel = 'AI',
  streaming = false,
  thinkStreaming = false,
  thinkChunkContent,
  thinkPlaceholders = ['我正在梳理，请稍后。', '我正在思考，请耐心等待。'],
  timestamp,
  onCopy,
  sessionId,
  logIndex,
  dimension,
  toolbarCopyTitle,
  toolbarLikeTitle,
  hideToolbar = false,
}: FlowAiMessageProps) {
  const { t } = useLocale();
  const [liked, setLiked] = useState(false);
  const [thinkPlaceholderIdx, setThinkPlaceholderIdx] = useState(0);
  const placeholders = thinkPlaceholders.length > 0 ? thinkPlaceholders : ['请稍等…'];
  const thinkLine = thinkChunkSingleLine(thinkChunkContent || '');

  /** 思考阶段：显示占位 + 单行预览。仅首包前等待也显示占位 */
  const showThinkRow = thinkStreaming || (streaming && !content);
  const showContentBubble = !showThinkRow;
  useEffect(() => {
    if (!showThinkRow) return;
    const timer = window.setInterval(() => {
      setThinkPlaceholderIdx((i) => (i + 1) % placeholders.length);
    }, 3600);
    return () => clearInterval(timer);
  }, [showThinkRow, placeholders.length]);

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

  const copyTitle = toolbarCopyTitle ?? t('explore.chat.messageToolbar.copy');
  const likeTitle = toolbarLikeTitle ?? t('explore.chat.messageToolbar.like');
  const wrapClass =
    variant === 'ruminationWorkbench'
      ? 'flow-msg-ai-wrap flow-msg-ai-wrap--rumination-wb'
      : 'flow-msg-ai-wrap';

  const showCareeringMeta = variant === 'careeringMatte';

  return (
    <div className={wrapClass}>
      {showCareeringMeta && timestamp !== undefined && (
        <div className="flow-msg-careering-meta">
          <div className="flow-msg-careering-avatar flow-msg-careering-avatar--ai" aria-hidden>
            ✨
          </div>
          <span>
            {careeringAiRoleLabel} · {formatMessageTime(timestamp)}
          </span>
        </div>
      )}
      {!showCareeringMeta && timestamp !== undefined && (
        <span className="flow-msg-time text-[10px] text-[var(--flow-text-muted)] mb-1">
          {formatMessageTime(timestamp)}
        </span>
      )}
      {showThinkRow && (
        <div
          className={`flow-msg-think-wrap${
            variant === 'ruminationWorkbench' ? ' flow-msg-think-wrap--rumination-wb' : ''
          }`}
        >
          <div className="flow-msg-think-placeholder flow-msg-think-placeholder--single-row">
            <span className="flow-msg-think-dot" aria-hidden />
            <span className="flow-msg-think-placeholder-label">{placeholders[thinkPlaceholderIdx]}</span>
            {thinkStreaming && thinkChunkContent && thinkChunkContent.trim().length > 0 ? (
              <span className="flow-msg-think-chunk-line" aria-live="polite">
                {thinkLine}
              </span>
            ) : null}
          </div>
        </div>
      )}
      {showContentBubble && (
        <div
          className={`flow-msg-ai-content ${phase}${
            variant === 'ruminationWorkbench' ? ' flow-msg-ai-content--rumination-wb' : ''
          }`}
        >
          <MessageContent content={content} markdown colorMode="light" />
        </div>
      )}
      {!hideToolbar && (
        <div className="flow-msg-ai-toolbar">
          <button type="button" className="flow-toolbar-btn" title={copyTitle} onClick={handleCopy}>
            <Copy size={14} strokeWidth={1.6} />
          </button>
          <button
            type="button"
            className={`flow-toolbar-btn ${liked ? 'liked' : ''}`}
            title={likeTitle}
            onClick={handleLike}
          >
            <ThumbsUp size={14} strokeWidth={1.6} />
          </button>
        </div>
      )}
    </div>
  );
}
