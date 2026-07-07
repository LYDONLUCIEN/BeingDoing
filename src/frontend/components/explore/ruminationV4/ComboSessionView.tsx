'use client';

/**
 * v4 单个 combo_session 视图(左右分栏)
 *
 * 左侧上半:固定的组合只读展示(热爱 X + 优势 [A,B,C])
 * 左侧下半:结论卡(出现后可编辑)
 * 右侧:对话面板(初始空白 + 开始讨论按钮 → AI 开场 → 对话)
 *
 * 见 wiki/开发文档/0707-tag1.6.0.md 第二节"阶段二"
 */

import { useEffect, useRef, useState } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import ConclusionCardEditable from './ConclusionCardEditable';

interface Props {
  comboId: string;
}

export default function ComboSessionView({ comboId }: Props) {
  const {
    comboCache,
    loadCombo,
    beginDiscussion,
    sendChat,
    abortChat,
    isStreaming,
    streamingText,
    fallbackActive,
    state,
  } = useRuminationV4Store();

  const combo = comboCache[comboId];
  const [input, setInput] = useState('');
  const messagesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadCombo(comboId);
  }, [comboId, loadCombo]);

  // 自动滚到底
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [combo?.messages?.length, streamingText]);

  if (!combo) {
    return <div className="flex-1 flex items-center justify-center text-gray-400">加载中…</div>;
  }

  const hasOpening = combo.messages?.some((m) => m.role === 'assistant');
  const isReadOnly = combo.status === 'concluded' || combo.status === 'abandoned';

  const handleStart = async () => {
    await beginDiscussion(comboId);
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    // 从 localStorage 取 token
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') || undefined : undefined;
    await sendChat(comboId, text, undefined, undefined, token);
  };

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* 左侧 */}
      <div className="w-2/5 border-r border-gray-100 overflow-y-auto p-4 bg-gray-50/50">
        {/* 上半:固定组合 */}
        <div className="mb-4 p-3 rounded-lg bg-white border border-gray-200">
          <div className="text-xs text-gray-500 mb-1">当前组合(只读)</div>
          <div className="text-lg font-bold text-bd-phase-rumination">{combo.passion}</div>
          <div className="flex flex-wrap gap-1 mt-2">
            {combo.strengths.map((s) => (
              <span key={s} className="px-2 py-0.5 text-xs rounded bg-green-50 text-green-700 border border-green-200">
                {s}
              </span>
            ))}
          </div>
          {isReadOnly && (
            <div className="mt-2 text-xs text-gray-400">
              状态:{combo.status === 'concluded' ? '已确认(只读,卡仍可编辑)' : '已放弃'}
            </div>
          )}
        </div>

        {/* 下半:结论卡(出现后展示)*/}
        {combo.conclusion_card && (
          <ConclusionCardEditable
            comboId={comboId}
            card={combo.conclusion_card}
            strengths={combo.strengths}
          />
        )}

        {/* 进度提示 */}
        <div className="mt-4 text-xs text-gray-400">
          对话轮数:{combo.messages?.filter((m) => m.role === 'user').length || 0}
          {combo.summary && <div className="mt-1">已自动摘要历史</div>}
        </div>
      </div>

      {/* 右侧:对话面板 */}
      <div className="flex-1 flex flex-col bg-white">
        <div ref={messagesRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          {!hasOpening && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <p className="text-gray-500 mb-4">组合已锁定。准备好开始深度对话了吗?</p>
              <button
                type="button"
                onClick={handleStart}
                className="px-6 py-2 rounded-lg bg-bd-phase-rumination text-white hover:opacity-90"
              >
                开始讨论
              </button>
            </div>
          )}

          {combo.messages?.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm whitespace-pre-wrap ${
                  m.role === 'user'
                    ? 'bg-bd-phase-rumination text-white rounded-br-sm'
                    : 'bg-gray-100 text-gray-800 rounded-bl-sm'
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}

          {/* 流式回复 */}
          {isStreaming && streamingText && (
            <div className="flex justify-start">
              <div className="max-w-[80%] px-3 py-2 rounded-2xl bg-gray-100 text-gray-800 text-sm whitespace-pre-wrap rounded-bl-sm">
                {streamingText}
              </div>
            </div>
          )}
          {fallbackActive && (
            <div className="text-center text-xs text-orange-500">兜底生成中,请稍候…</div>
          )}
        </div>

        {/* 输入框 */}
        <div className="border-t border-gray-100 p-3 flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={isStreaming || !hasOpening || isReadOnly}
            placeholder={isReadOnly ? '该组合已锁定' : hasOpening ? '输入你的回答…' : '点击「开始讨论」'}
            className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-bd-phase-rumination disabled:bg-gray-50"
          />
          <button
            type="button"
            onClick={isStreaming ? abortChat : handleSend}
            disabled={!isStreaming && (!input.trim() || !hasOpening || isReadOnly)}
            className={`px-4 py-2 rounded-lg text-sm ${
              isStreaming
                ? 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                : 'bg-bd-phase-rumination text-white hover:opacity-90 disabled:opacity-50'
            }`}
          >
            {isStreaming ? '中断' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
