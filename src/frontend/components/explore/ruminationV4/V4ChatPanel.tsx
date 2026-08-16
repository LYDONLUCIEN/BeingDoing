'use client';

/**
 * v4 对话面板 — DOM/样式对齐 v3 rumination 聊天区
 *
 * 复用 v3 风格：
 * - 用户消息：头像 + 名称 + 时间 + 复制工具栏
 * - AI 消息：FlowAiMessage（✨ 头像 meta + 思考占位动画 + 复制/点赞/保存工具栏，复用前四 phase）
 * - 输入区：白色胶囊 + 发送/停止按钮
 * - 草稿态：整区模糊锁定
 * - 分析中(ADR-0015)：输入锁定,提示「正在分析中」
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { ArrowUp, Square, Copy } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { useAuthStore } from '@/stores/authStore';
import { copyToClipboard } from '@/lib/utils/clipboard';
import type { ComboMessage } from '@/lib/explore/ruminationV4Api';

const FlowAiMessage = dynamic(() => import('@/components/explore/FlowAiMessage'), {
  ssr: false,
});

interface Props {
  comboId: string | null;
}

function formatMsgTime(ts?: string): string {
  const d = ts ? new Date(ts) : new Date();
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

export default function V4ChatPanel({ comboId }: Props) {
  const {
    comboCache,
    beginDiscussion,
    sendChat,
    abortChat,
    isStreaming,
    streamingText,
    thinkStreaming,
    thinkChunkContent,
    error,
    init,
    clearError,
    activationCode,
    state,
  } = useRuminationV4Store();
  const { user } = useAuthStore();

  const [input, setInput] = useState('');
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** 记录上一帧是否在流式中，用于流式结束后把光标放回输入框 */
  const wasStreamingRef = useRef(false);

  const userInitials = useMemo(
    () => (user?.username || user?.email || 'U').slice(0, 2).toUpperCase(),
    [user?.username, user?.email]
  );

  const isDraft = !comboId;
  const combo = comboId ? comboCache[comboId] : null;
  const messages = useMemo(() => combo?.messages || [], [combo?.messages]);
  const hasOpening = messages.some((m) => m.role === 'assistant');
  const isReadOnly = combo?.status === 'concluded' || combo?.status === 'abandoned';
  // ADR-0015:判定分析中锁对话输入(锁是 combo 级的,可切换/新建其他组合)
  const isAnalyzing = combo?.balance_analysis?.status === 'analyzing';
  /** 终选已提交：整页回看模式，对话输入与「开始讨论」全部禁用 */
  const finalSubmitted = !!state?.final_selection?.submitted;

  // 为每条消息补充稳定 id / 时间，用于 key、时间戳、埋点
  // 过滤空内容消息(历史 tool-only 轮次可能落盘过空 assistant 消息,避免空气泡)
  const enrichedMessages = useMemo(
    () =>
      messages
        .filter((m) => (m.content || '').trim().length > 0)
        .map((m, idx) => ({
          ...m,
          id: `${comboId || 'draft'}-${m.role}-${idx}`,
          createdAt: m.ts ? new Date(m.ts).getTime() : Date.now() - (messages.length - 1 - idx) * 60000,
        })),
    [messages, comboId]
  );

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [enrichedMessages.length, streamingText, thinkStreaming]);

  // 流式结束（含中止）后 textarea 重新可用时，自动聚焦，用户可直接继续输入
  useEffect(() => {
    if (wasStreamingRef.current && !isStreaming) {
      inputRef.current?.focus();
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming]);

  const handleStart = async () => {
    if (!comboId) return;
    await beginDiscussion(comboId);
  };

  const sendText = async (text: string) => {
    if (!comboId || isDraft) return;
    if (!text || isStreaming) return;
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('token') || undefined : undefined;
    await sendChat(comboId, text, undefined, token);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    await sendText(text);
    // 发送未进入流式（如分析中被拦）时，聚焦由这里保证；流式结束由上面的 effect 保证
    inputRef.current?.focus();
  };

  const canInput =
    !!comboId &&
    hasOpening &&
    !isStreaming &&
    !isReadOnly &&
    !isDraft &&
    !isAnalyzing &&
    !finalSubmitted;

  return (
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      {/* 与 v3 右栏一致的毛玻璃聊天卡 */}
      <div className="rumination-beautiful-card rumination-beautiful-card--chat flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden py-4 px-3 sm:px-5 sm:py-5">
        <div className="mb-2 shrink-0 border-b border-black/[0.06] pb-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-bd-fg">
                {combo ? `${combo.passion} × ${combo.strengths.join('、')}` : '探索对话'}
              </h2>
              <p className="mt-0.5 text-xs text-neutral-500">
                {isDraft
                  ? '请先在左侧选点并点击「开始探索」'
                  : combo
                    ? finalSubmitted
                      ? '最终选择已提交，内容已锁定，仅供回看'
                      : isAnalyzing
                      ? '结论卡分析中，完成后可继续探讨'
                      : isReadOnly
                        ? combo.status === 'concluded'
                          ? '结论已确认，点左侧结论卡上的「再聊聊」可继续探讨'
                          : '该组合已跳过，点左侧结论卡可恢复'
                        : hasOpening
                          ? '与我探讨这个组合的假设方向'
                          : '点击下方开始讨论'
                    : '请从左侧选择或创建一个组合开始探索'}
              </p>
            </div>
          </div>
        </div>

        <div
          className={`flex min-h-0 flex-1 flex-col overflow-hidden py-1 transition-[filter,opacity] duration-300 ${
            isDraft ? 'pointer-events-none select-none opacity-[0.45] blur-[2.5px]' : ''
          }`}
          aria-disabled={isDraft}
        >
          <div className="flow-chat-box rumination-beautiful-chat-panel relative flex min-h-0 min-w-0 w-full max-w-none flex-1 flex-col">
            <div
              ref={bodyRef}
              className="flow-chat-body rumination-chat-body-fade min-h-0 min-w-0 w-full flex-1 overflow-y-auto"
            >
              <div className="careering-chat-messages-inner min-w-0 w-full max-w-none px-4 sm:px-6 lg:px-8">
                {error && !isStreaming && !isDraft && (
                  <div className="flex flex-col items-center justify-center py-10 text-center">
                    <p className="mb-1 text-sm text-red-500">操作失败</p>
                    <p className="mb-4 text-xs text-neutral-400">{error}</p>
                    <button
                      type="button"
                      onClick={() => {
                        clearError();
                        if (activationCode) init(activationCode);
                      }}
                      className="bd-btn-black rounded-full px-5 py-2.5 text-sm font-semibold text-white"
                    >
                      重新加载
                    </button>
                  </div>
                )}

                {!error && isDraft ? (
                  <p className="flow-progress-text py-8 text-center text-sm text-neutral-400">
                    选择热爱与优势后，点击「开始探索」解锁对话
                  </p>
                ) : !error && !hasOpening && !isStreaming ? (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <p className="mb-4 text-sm text-neutral-500">
                      {finalSubmitted
                        ? '最终选择已提交，内容已锁定，仅供回看。'
                        : '组合已锁定。准备好开始深度对话了吗？'}
                    </p>
                    {!finalSubmitted && (
                      <button
                        type="button"
                        onClick={handleStart}
                        className="bd-btn-black rounded-full px-5 py-2.5 text-sm font-semibold text-white"
                      >
                        开始讨论
                      </button>
                    )}
                  </div>
                ) : (
                  <>
                    {enrichedMessages.map((m, idx) => (
                      <MessageRow
                        key={m.id}
                        msg={m}
                        isLast={idx === enrichedMessages.length - 1}
                        isStreaming={isStreaming}
                        userInitials={userInitials}
                        comboId={comboId}
                        activationCode={activationCode}
                        aiLogIndex={
                          enrichedMessages
                            .slice(0, idx)
                            .filter((x) => x.role === 'assistant').length
                        }
                      />
                    ))}

                    {isStreaming && (
                      <FlowAiMessage
                        content={streamingText}
                        phase="rumination"
                        variant="ruminationWorkbench"
                        showCareeringAiMeta
                        contentMode="markdown"
                        streaming
                        careeringAiRoleLabel="路路"
                        toolbarCopyTitle="复制"
                        toolbarLikeTitle="点赞"
                        toolbarSavepointTitle="保存"
                        thinkStreaming={thinkStreaming}
                        thinkChunkContent={thinkChunkContent}
                        thinkPlaceholders={['正在思考…', '整理思路中…', '组织回复…']}
                        timestamp={Date.now()}
                        sessionId={activationCode ?? undefined}
                        messageId={`${comboId}-streaming-assistant`}
                        threadId={comboId ?? undefined}
                        phaseKey="rumination"
                        activationCode={activationCode ?? undefined}
                      />
                    )}
                    {isAnalyzing && (
                      <p className="py-2 text-center text-xs text-[#b57908]">
                        结论卡正在分析中，请稍后…
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* 输入区：结构对齐 v3 careering-input-dock + flow-input-* */}
            <div className="careering-input-dock w-full flex-shrink-0">
              <div className="flow-input-area">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleSend();
                  }}
                  className="w-full"
                >
                  <div
                    className={`flow-input-box !flex !flex-col !items-stretch gap-1.5${
                      !canInput && !isStreaming ? ' opacity-40 pointer-events-none' : ''
                    }`}
                  >
                    <div className="flex w-full min-w-0 items-end gap-2.5">
                      <textarea
                        ref={inputRef}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSend();
                          }
                        }}
                        placeholder={
                          finalSubmitted
                            ? '已提交锁定，仅供回看'
                            : isDraft
                              ? '请先点击「开始探索」'
                              : !hasOpening
                              ? '点击「开始讨论」'
                              : isAnalyzing
                                ? '正在分析中，请稍后…'
                                : isReadOnly
                                  ? combo.status === 'concluded'
                                    ? '已确认，点左侧结论卡「再聊聊」继续探讨'
                                    : '已跳过，点左侧结论卡可恢复'
                                  : '输入你的想法...'
                        }
                        rows={1}
                        disabled={!canInput}
                        className="flow-input-field"
                      />
                      <div className="flow-send-btn-wrap">
                        {isStreaming && <div className="flow-send-glow" aria-hidden />}
                        <button
                          type="button"
                          onClick={isStreaming ? abortChat : handleSend}
                          disabled={!isStreaming && (!canInput || !input.trim())}
                          className={`flow-send-btn ${isStreaming ? 'is-stop' : ''}`}
                          aria-label={isStreaming ? '停止' : '发送'}
                        >
                          {isStreaming ? (
                            <Square size={16} strokeWidth={0} fill="white" />
                          ) : (
                            <ArrowUp size={16} strokeWidth={2.2} />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          </div>
        </div>
      </div>

      {isDraft && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center px-6">
          <div
            className="rounded-2xl px-5 py-3.5 text-center text-[13px] font-[700] text-[#536184]"
            style={{
              background: 'rgba(255,255,255,0.82)',
              border: '1px solid rgba(255,255,255,0.7)',
              boxShadow: '0 10px 28px rgba(33,48,79,0.08)',
              backdropFilter: 'blur(8px)',
            }}
          >
            左侧选完热爱与优势后
            <br />
            点击「开始探索」解锁对话
          </div>
        </div>
      )}
    </div>
  );
}

/** 用户/AI 气泡 DOM 对齐 v3 rumination workbench */
function MessageRow({
  msg,
  isLast,
  isStreaming,
  userInitials,
  comboId,
  activationCode,
  aiLogIndex,
}: {
  msg: ComboMessage & { id: string; createdAt: number };
  isLast: boolean;
  isStreaming: boolean;
  userInitials: string;
  comboId: string | null;
  activationCode: string | null;
  aiLogIndex: number;
}) {
  const { user } = useAuthStore();
  if (msg.role === 'user') {
    const s = (msg.content || '').replace(/\r\n/g, '\n');
    const charCount = [...s].length;
    const hasManualBreak = s.includes('\n');
    const compact = charCount > 0 && charCount <= 8 && !hasManualBreak;
    const textClass = `flow-msg-user-text flow-msg-user-text--careering-plain${
      compact ? ' flow-msg-user-text--compact' : ''
    }`;

    return (
      <div className="flow-msg-user">
        <div className="flow-msg-user-wrap">
          <div className="flow-msg-careering-meta flow-msg-careering-meta--user">
            <div
              className="flow-msg-careering-avatar flow-msg-careering-avatar--user text-xs font-semibold text-white"
              style={{
                background: user?.avatar_url
                  ? `url(${user.avatar_url}) center/cover no-repeat`
                  : 'linear-gradient(135deg, var(--bd-phase-values), var(--bd-phase-strengths))',
              }}
              aria-hidden
            >
              {!user?.avatar_url ? userInitials : null}
            </div>
            <span>
              我 · {formatMsgTime(new Date(msg.createdAt).toISOString())}
            </span>
          </div>
          <div className="flow-msg-user-anchor">
            <div className="flow-msg-user-content" lang="zh-CN">
              <span className={textClass}>{s}</span>
            </div>
          </div>
          <div className="flow-msg-user-toolbar opacity-0 transition-opacity hover:opacity-100">
            <button
              type="button"
              className="flow-toolbar-btn"
              title="复制"
              onClick={() => copyToClipboard(msg.content)}
            >
              <Copy size={14} strokeWidth={1.6} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (msg.role === 'system') return null;

  return (
    <FlowAiMessage
      content={msg.content}
      phase="rumination"
      variant="ruminationWorkbench"
      showCareeringAiMeta
      contentMode="markdown"
      streaming={isStreaming && isLast}
      careeringAiRoleLabel="路路"
      toolbarCopyTitle="复制"
      toolbarLikeTitle="点赞"
      toolbarSavepointTitle="保存"
      thinkPlaceholders={['正在思考…', '整理思路中…', '组织回复…']}
      timestamp={msg.createdAt}
      sessionId={activationCode ?? undefined}
      logIndex={aiLogIndex}
      dimension="rumination"
      messageId={msg.id}
      threadId={comboId ?? undefined}
      phaseKey="rumination"
      activationCode={activationCode ?? undefined}
    />
  );
}
