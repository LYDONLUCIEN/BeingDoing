'use client';

import { useState, useEffect } from 'react';
import { BookmarkPlus, Copy, Heart } from 'lucide-react';
import MessageContent from './MessageContent';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { toggleLike } from '@/lib/api/analytics';
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
  /** 正文展示：markdown（默认）| plain_line（单行等宽，用于确认稿 JSON 流式预览） */
  contentMode?: 'markdown' | 'plain_line';
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
  /** 埋点：session_id、log_index（旧版兼容） */
  sessionId?: string;
  logIndex?: number;
  dimension?: string;
  /** 点赞 v2：消息唯一标识 */
  messageId?: string;
  /** 点赞 v2：线程 ID */
  threadId?: string;
  /** 点赞 v2：阶段 key */
  phaseKey?: string;
  /** 点赞 v2：激活码 */
  activationCode?: string;
  toolbarCopyTitle?: string;
  toolbarLikeTitle?: string;
  toolbarSavepointTitle?: string;
  onSavepoint?: () => void;
  /** 为 true 时不显示底部复制/点赞条（如静态引导文案） */
  hideToolbar?: boolean;
  /** 子步 3：假设候选列表 */
  hypCandidates?: string[];
  /** 子步 3：假设目标行（0-based） */
  hypTargetRow?: number;
  /** 子步 3：未能确定目标行 */
  hypRowUnresolved?: boolean;
  /** 子步 3：用户点选表格行后作为填入目标 */
  selectedRowFallback?: number | null;
  /** 子步 3：点击假设候选回调 */
  onHypCandidateClick?: (text: string, meta: { hypTargetRow?: number; hypRowUnresolved?: boolean }) => void;
  /** step3 matrix 模式：chips 始终可点击 */
  comboMatrixMode?: boolean;
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
  contentMode = 'markdown',
  thinkStreaming = false,
  thinkChunkContent,
  thinkPlaceholders = ['我正在梳理，请稍后。', '我正在思考，请耐心等待。'],
  timestamp,
  onCopy,
  sessionId,
  logIndex,
  dimension,
  messageId,
  threadId,
  phaseKey,
  activationCode,
  toolbarCopyTitle,
  toolbarLikeTitle,
  toolbarSavepointTitle,
  onSavepoint,
  hideToolbar = false,
  hypCandidates,
  hypTargetRow,
  hypRowUnresolved,
  selectedRowFallback,
  onHypCandidateClick,
  comboMatrixMode,
}: FlowAiMessageProps) {
  const { t } = useLocale();
  const [liked, setLiked] = useState(false);
  const [thinkPlaceholderIdx, setThinkPlaceholderIdx] = useState(0);
  const placeholders = thinkPlaceholders.length > 0 ? thinkPlaceholders : ['请稍等…'];
  const thinkLine = thinkChunkSingleLine(thinkChunkContent || '');

  /** 思考阶段：显示占位 + 单行预览。仅首包前等待也显示占位 */
  const showThinkRow =
    thinkStreaming || (streaming && !content && contentMode !== 'plain_line');
  /** plain_line：正文区在流式全程可占位（避免首 token 前空白），有思考时仍以思考行为主 */
  const showContentBubble =
    !showThinkRow ||
    (contentMode === 'plain_line' && streaming && !thinkStreaming);
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
    if (sessionId) {
      toggleLike({
        session_id: sessionId,
        thread_id: threadId,
        message_id: messageId || `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        role: 'assistant',
        content_preview: content?.slice(0, 500) || undefined,
        content_snapshot: content || undefined,
        dimension: dimension || phase,
        phase: phaseKey || phase,
        activation_code: activationCode,
        log_index: logIndex,
      }).then((res) => {
        // 以服务端返回为准
        if (res.data?.liked !== undefined) setLiked(res.data.liked);
      }).catch(() => {});
    }
  };

  const copyTitle = toolbarCopyTitle ?? t('explore.chat.messageToolbar.copy');
  const likeTitle = toolbarLikeTitle ?? t('explore.chat.messageToolbar.like');
  const savepointTitle = toolbarSavepointTitle ?? '保存为检查点';
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
          {contentMode === 'plain_line' ? (
            <div className="flex min-h-[1.25rem] max-w-full items-center gap-1">
              <span
                className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[13px] leading-relaxed text-[var(--flow-text)]"
                title={content}
                aria-live="polite"
              >
                {thinkChunkSingleLine(content || '')}
              </span>
              {streaming ? (
                <span
                  className="h-4 w-px shrink-0 animate-pulse bg-current opacity-60"
                  aria-hidden
                />
              ) : null}
            </div>
          ) : (
            <MessageContent
              content={content}
              markdown
              colorMode="light"
              hypCandidates={hypCandidates}
              hypTargetRow={hypTargetRow}
              hypRowUnresolved={hypRowUnresolved}
              selectedRowFallback={selectedRowFallback}
              onHypCandidateClick={onHypCandidateClick}
              comboMatrixMode={comboMatrixMode}
            />
          )}
        </div>
      )}
      {!hideToolbar && (
        <div className="flow-msg-ai-toolbar">
          <button type="button" className="flow-toolbar-btn" title={copyTitle} onClick={handleCopy}>
            <Copy size={14} strokeWidth={1.6} />
          </button>
          <button
            type="button"
            className={`flow-toolbar-btn flow-toolbar-like-btn ${liked ? 'liked' : ''}`}
            title={likeTitle}
            onClick={handleLike}
            aria-pressed={liked}
          >
            <Heart
              size={14}
              strokeWidth={1.6}
              className={`flow-toolbar-like-icon ${liked ? 'filled' : ''}`}
            />
          </button>
          {onSavepoint && (
            <button
              type="button"
              className="flow-toolbar-btn"
              title={savepointTitle}
              onClick={onSavepoint}
            >
              <BookmarkPlus size={14} strokeWidth={1.6} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
