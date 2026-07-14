'use client';

/**
 * v4 对话面板 — DOM/样式对齐 v3 rumination beautiful 聊天区
 *
 * 依赖父级 `.rumination-beautiful-root.flow-light[data-phase=rumination]`。
 * 选点草稿（无 active combo）：整区模糊锁定。
 */

import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import type { ComboMessage } from '@/lib/explore/ruminationV4Api';

const FlowAiMessage = dynamic(() => import('@/components/explore/FlowAiMessage'), {
  ssr: false,
});

interface Props {
  comboId: string | null;
}

export default function V4ChatPanel({ comboId }: Props) {
  const {
    comboCache,
    beginDiscussion,
    sendChat,
    abortChat,
    isStreaming,
    streamingText,
    fallbackActive,
    error,
    init,
    clearError,
    activationCode,
  } = useRuminationV4Store();

  const [input, setInput] = useState('');
  const bodyRef = useRef<HTMLDivElement>(null);

  const isDraft = !comboId;
  const combo = comboId ? comboCache[comboId] : null;
  const messages = combo?.messages || [];
  const hasOpening = messages.some((m) => m.role === 'assistant');
  const isReadOnly = combo?.status === 'concluded' || combo?.status === 'abandoned';

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages.length, streamingText]);

  const handleStart = async () => {
    if (!comboId) return;
    await beginDiscussion(comboId);
  };

  const handleSend = async () => {
    if (!comboId || isDraft) return;
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    const token =
      typeof window !== 'undefined' ? localStorage.getItem('token') || undefined : undefined;
    await sendChat(comboId, text, undefined, undefined, token);
  };

  const canInput = !!comboId && hasOpening && !isStreaming && !isReadOnly && !isDraft;

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
                    ? isReadOnly
                      ? '该组合已锁定'
                      : hasOpening
                        ? '与 AI 探讨这个组合的假设方向'
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
              <div className="careering-chat-messages-inner min-w-0 w-full max-w-none px-4 sm:px-6 lg:px-12">
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
                      组合已锁定。准备好开始深度对话了吗？
                    </p>
                    <button
                      type="button"
                      onClick={handleStart}
                      className="bd-btn-black rounded-full px-5 py-2.5 text-sm font-semibold text-white"
                    >
                      开始讨论
                    </button>
                  </div>
                ) : (
                  <>
                    {messages.map((m, idx) => (
                      <MessageRow
                        key={`${m.role}-${idx}-${m.ts || ''}`}
                        msg={m}
                        isLast={idx === messages.length - 1}
                        isStreaming={isStreaming}
                      />
                    ))}

                    {isStreaming && streamingText && (
                      <FlowAiMessage
                        content={streamingText}
                        phase="rumination"
                        variant="ruminationWorkbench"
                        contentMode="markdown"
                        streaming
                        careeringAiRoleLabel="AI 助手"
                        toolbarCopyTitle="复制"
                        toolbarLikeTitle="点赞"
                        toolbarSavepointTitle="保存"
                        thinkPlaceholders={['正在思考…', '整理思路中…', '组织回复…']}
                      />
                    )}
                    {fallbackActive && (
                      <p className="py-2 text-center text-xs text-orange-500">
                        兜底生成中，请稍候…
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
                    {isStreaming && (
                      <p
                        className="w-full shrink-0 px-1 text-left text-xs leading-snug text-neutral-500"
                        role="status"
                        aria-live="polite"
                      >
                        AI 正在回复…
                      </p>
                    )}
                    <div className="flex w-full min-w-0 items-end gap-2.5">
                      <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSend();
                          }
                        }}
                        placeholder={
                          isDraft
                            ? '请先点击「开始探索」'
                            : !hasOpening
                              ? '点击「开始讨论」'
                              : isReadOnly
                                ? '该组合已锁定'
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
                        />
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
}: {
  msg: ComboMessage;
  isLast: boolean;
  isStreaming: boolean;
}) {
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
          <div className="flow-msg-user-anchor">
            <div className="flow-msg-user-content" lang="zh-CN">
              <span className={textClass}>{s}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <FlowAiMessage
      content={msg.content}
      phase="rumination"
      variant="ruminationWorkbench"
      contentMode="markdown"
      streaming={isStreaming && isLast}
      careeringAiRoleLabel="AI 助手"
      toolbarCopyTitle="复制"
      toolbarLikeTitle="点赞"
      toolbarSavepointTitle="保存"
      thinkPlaceholders={['正在思考…', '整理思路中…', '组织回复…']}
    />
  );
}
