'use client';

import { useState, useEffect, useRef } from 'react';
import { Copy, RefreshCw, ThumbsUp, ChevronDown, ChevronRight, Lightbulb } from 'lucide-react';
import MessageContent from './MessageContent';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { recordLike } from '@/lib/api/analytics';
import { useLocale } from '@/hooks/useLocale';

type PhaseClass = 'values' | 'strength' | 'interest' | 'purpose' | 'rumination';

function formatMessageTime(ms: number): string {
  const d = new Date(ms);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

interface FlowAiMessageProps {
  content: string;
  phase: PhaseClass;
  /** 沉淀工作台右栏：薰衣草磨砂气泡 */
  variant?: 'default' | 'ruminationWorkbench';
  /** 是否流式输出中 */
  streaming?: boolean;
  /** 推理模型思考过程（折叠展示） */
  thinkContent?: string;
  /** 思考中占位（流式时显示） */
  thinkStreaming?: boolean;
  /** 思考过程实时输出预览（单行展示） */
  thinkChunkContent?: string;
  /** 思考过程占位文案（5~6 条轮流展示，每 3.6s 换一条） */
  thinkPlaceholders?: string[];
  /** 思考过程折叠标题 */
  thinkLabel?: string;
  /** 消息时间戳（Unix ms） */
  timestamp?: number;
  onCopy?: () => void;
  onRegenerate?: () => void;
  /** 埋点：session_id、log_index、dimension，点赞时上报 */
  sessionId?: string;
  logIndex?: number;
  dimension?: string;
  toolbarCopyTitle?: string;
  toolbarRegenerateTitle?: string;
  toolbarLikeTitle?: string;
}

/**
 * 复刻 llmchat：AI 消息无气泡，左侧色条 + 工具栏（复制、重新生成、点赞）
 * 支持推理模型思考过程：思考中显示占位，完成后折叠展示
 */
export default function FlowAiMessage({
  content,
  phase,
  variant = 'default',
  streaming = false,
  thinkContent,
  thinkStreaming = false,
  thinkChunkContent,
  thinkPlaceholders = ['我正在梳理，请稍后。', '我正在思考，请耐心等待。'],
  thinkLabel = '思考过程',
  timestamp,
  onCopy,
  onRegenerate,
  sessionId,
  logIndex,
  dimension,
  toolbarCopyTitle,
  toolbarRegenerateTitle,
  toolbarLikeTitle,
}: FlowAiMessageProps) {
  const { t } = useLocale();
  const [liked, setLiked] = useState(false);
  const [thinkExpanded, setThinkExpanded] = useState(false);
  const [thinkPlaceholderIdx, setThinkPlaceholderIdx] = useState(0);
  const thinkPreviewRef = useRef<HTMLDivElement>(null);
  const placeholders = thinkPlaceholders.length > 0 ? thinkPlaceholders : ['请稍等…'];
  const thinkPreviewLine =
    (thinkChunkContent || '')
      .split(/\r?\n/)
      .filter((s) => s.trim().length > 0)
      .slice(-1)[0] || thinkChunkContent || '\u00A0';

  useEffect(() => {
    if (thinkChunkContent && thinkPreviewRef.current) {
      thinkPreviewRef.current.scrollTop = thinkPreviewRef.current.scrollHeight;
    }
  }, [thinkChunkContent]);

  /** 思考阶段：显示占位，不渲染思考内容。think_end 后内容在气泡中流式显示 */
  const showPlaceholder = thinkStreaming || (streaming && !content);
  const showContentBubble = !showPlaceholder;
  useEffect(() => {
    if (!showPlaceholder) return;
    const t = setInterval(() => {
      setThinkPlaceholderIdx((i) => (i + 1) % placeholders.length);
    }, 3600);
    return () => clearInterval(t);
  }, [showPlaceholder, placeholders.length]);

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
  const regenTitle = toolbarRegenerateTitle ?? t('explore.chat.messageToolbar.regenerate');
  const likeTitle = toolbarLikeTitle ?? t('explore.chat.messageToolbar.like');
  const wrapClass =
    variant === 'ruminationWorkbench'
      ? 'flow-msg-ai-wrap flow-msg-ai-wrap--rumination-wb'
      : 'flow-msg-ai-wrap';

  return (
    <div className={wrapClass}>
      {timestamp !== undefined && (
        <span className="flow-msg-time text-[10px] text-[var(--flow-text-muted)] mb-1">
          {formatMessageTime(timestamp)}
        </span>
      )}
      {/* 思考过程：占位或折叠区。streaming 且 content 为空时也显示占位（首包前的等待） */}
      {(thinkStreaming || thinkContent || (streaming && !content)) && (
        <div
          className={`flow-msg-think-wrap${variant === 'ruminationWorkbench' ? ' flow-msg-think-wrap--rumination-wb' : ''}`}
        >
          {showPlaceholder ? (
            <div className="flow-msg-think-placeholder">
              <div className="flow-msg-think-placeholder-text">
                <span className="flow-msg-think-dot" />
                {placeholders[thinkPlaceholderIdx]}
              </div>
              {thinkStreaming && (
                <div
                  ref={thinkPreviewRef}
                  className="flow-msg-think-preview"
                  role="log"
                  aria-live="polite"
                >
                  {thinkPreviewLine}
                </div>
              )}
            </div>
          ) : (
            <button
              type="button"
              className="flow-msg-think-toggle"
              onClick={() => setThinkExpanded((e) => !e)}
              aria-expanded={thinkExpanded}
            >
              {thinkExpanded ? (
                <ChevronDown size={14} className="flow-msg-think-chevron" aria-hidden />
              ) : (
                <span className="flow-msg-think-icon-wrap">
                  <Lightbulb size={14} className="flow-msg-think-bulb" aria-hidden />
                  <ChevronRight size={14} className="flow-msg-think-arrow" aria-hidden />
                </span>
              )}
              <span>{thinkLabel}</span>
            </button>
          )}
          {thinkContent && thinkExpanded && (
            <div className="flow-msg-think-content">
              <MessageContent content={thinkContent} markdown colorMode="light" />
            </div>
          )}
        </div>
      )}
      {showContentBubble && (
        <div
          className={`flow-msg-ai-content ${phase}${variant === 'ruminationWorkbench' ? ' flow-msg-ai-content--rumination-wb' : ''}`}
        >
          <MessageContent content={content} markdown colorMode="light" />
        </div>
      )}
      <div className="flow-msg-ai-toolbar">
        <button
          type="button"
          className="flow-toolbar-btn"
          title={copyTitle}
          onClick={handleCopy}
        >
          <Copy size={14} strokeWidth={1.6} />
        </button>
        {onRegenerate && (
          <button
            type="button"
            className="flow-toolbar-btn"
            title={regenTitle}
            onClick={onRegenerate}
          >
            <RefreshCw size={14} strokeWidth={1.6} />
          </button>
        )}
        <button
          type="button"
          className={`flow-toolbar-btn ${liked ? 'liked' : ''}`}
          title={likeTitle}
          onClick={handleLike}
        >
          <ThumbsUp size={14} strokeWidth={1.6} />
        </button>
      </div>
    </div>
  );
}
