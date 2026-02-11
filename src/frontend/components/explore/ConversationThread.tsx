'use client';

import { useRef, useEffect } from 'react';
import type { Answer } from '@/lib/api/answers';
import type { Message } from '@/lib/api/chat';
import type { AnswerChangeType } from '@/lib/api/answers';
import MessageContent from './MessageContent';

export type ConversationItem =
  | { type: 'answer'; answer: Answer; questionContent?: string }
  | { type: 'chat'; message: Message };

interface ConversationThreadProps {
  items: ConversationItem[];
  /** 当前正在流式输出的助手消息（显示在列表末尾） */
  streamingContent?: string;
  editingAnswerId: string | null;
  onStartEdit: (answerId: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: (answerId: string, content: string, changeType: AnswerChangeType) => void;
  editContent: string;
  editChangeType: AnswerChangeType;
  onEditContentChange: (v: string) => void;
  onEditChangeTypeChange: (v: AnswerChangeType) => void;
  savingEdit: boolean;
}

const CHANGE_TYPE_LABELS: Record<AnswerChangeType, string> = {
  same_direction: '同向（更精确）',
  opposite: '反向（推翻）',
  unrelated: '无关（随机）',
};

export default function ConversationThread({
  items,
  streamingContent = '',
  editingAnswerId,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  editContent,
  editChangeType,
  onEditContentChange,
  onEditChangeTypeChange,
  savingEdit,
}: ConversationThreadProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items, editingAnswerId, streamingContent]);

  return (
    <div className="flex-1 overflow-y-auto space-y-6 pb-4">
      {items.length === 0 && !streamingContent && (
        <div className="text-center text-white/50 py-12">
          <p>在这里与咨询师对话，或回答当前问题。</p>
        </div>
      )}
      {items.map((item) => {
        if (item.type === 'answer') {
          const { answer, questionContent } = item;
          const isEditing = editingAnswerId === answer.id;

          if (isEditing) {
            return (
              <div key={`edit-${answer.id}`} className="rounded-xl border border-primary-400/50 bg-slate-800/80 p-4 space-y-3">
                {questionContent && (
                  <p className="text-white/70 text-sm">{questionContent}</p>
                )}
                <textarea
                  value={editContent}
                  onChange={(e) => onEditContentChange(e.target.value)}
                  rows={4}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900/80 text-white border border-white/10 focus:border-primary-400/50 focus:ring-1 focus:ring-primary-400/30 resize-none"
                  placeholder="修改后的回答..."
                />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-white/60 text-sm">修改类型：</span>
                  {(['same_direction', 'opposite', 'unrelated'] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => onEditChangeTypeChange(t)}
                      className={
                        'px-3 py-1.5 rounded-lg text-sm transition-colors ' +
                        (editChangeType === t
                          ? 'bg-primary-500 text-white'
                          : 'bg-white/10 text-white/80 hover:bg-white/20')
                      }
                    >
                      {CHANGE_TYPE_LABELS[t]}
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => onSaveEdit(answer.id, editContent, editChangeType)}
                    disabled={savingEdit || !editContent.trim()}
                    className="px-4 py-2 rounded-lg bg-primary-500 text-white text-sm font-medium disabled:opacity-50"
                  >
                    {savingEdit ? '保存中…' : '保存'}
                  </button>
                  <button
                    type="button"
                    onClick={onCancelEdit}
                    className="px-4 py-2 rounded-lg bg-white/10 text-white/80 text-sm hover:bg-white/20"
                  >
                    取消
                  </button>
                </div>
              </div>
            );
          }

          return (
            <div key={answer.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary-500/90 text-white px-4 py-3 shadow-lg">
                {questionContent && (
                  <p className="text-primary-100/90 text-xs mb-2 border-b border-primary-400/30 pb-2">
                    {questionContent}
                  </p>
                )}
                <MessageContent content={answer.content} markdown={false} />
                <div className="mt-2 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => onStartEdit(answer.id)}
                    className="text-xs text-primary-100/90 hover:text-white underline"
                  >
                    编辑
                  </button>
                </div>
              </div>
            </div>
          );
        }

        const { message } = item;
        const isAssistant = message.role === 'assistant';
        return (
          <div key={message.id} className={isAssistant ? 'flex justify-start' : 'flex justify-end'}>
            <div
              className={
                'max-w-[85%] rounded-2xl px-4 py-3 shadow-lg ' +
                (isAssistant
                  ? 'rounded-bl-md bg-white/10 text-white/95 border border-white/10'
                  : 'rounded-br-md bg-primary-500/90 text-white')
              }
            >
              <MessageContent content={message.content} markdown={isAssistant} />
            </div>
          </div>
        );
      })}
      {streamingContent !== '' && (
        <div className="flex justify-start">
          <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-white/10 text-white/95 border border-white/10 px-4 py-3 shadow-lg">
            <MessageContent content={streamingContent} markdown />
            <span className="inline-block w-2 h-4 ml-0.5 bg-white/70 animate-pulse" aria-hidden />
          </div>
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
