'use client';

import { useState } from 'react';
import { Pencil, ChevronDown, ChevronUp } from 'lucide-react';
import MessageContent from './MessageContent';

interface AnswerCardProps {
  questionTitle?: string;
  /** AI 的分析/反馈（只读） */
  aiAnalysis?: string;
  /** 用户的答案文本（可编辑） */
  userAnswer: string;
  onNext: () => void;
  onDiscussMore: () => void;
  onSubmitEdit: (newText: string) => Promise<void> | void;
  /** 是否允许「再讨论一会」按钮可用（历史卡片中应为 false） */
  canDiscuss: boolean;
  /** 是否在初始时折叠（历史卡片默认折叠） */
  defaultCollapsed?: boolean;
  /** 是否显示「下一题」按钮（历史卡片中可以隐藏） */
  showNext?: boolean;
}

export default function AnswerCard({
  questionTitle,
  aiAnalysis,
  userAnswer,
  onNext,
  onDiscussMore,
  onSubmitEdit,
  canDiscuss,
  defaultCollapsed = false,
  showNext = true,
}: AnswerCardProps) {
  const [editing, setEditing] = useState(false);
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [draft, setDraft] = useState(userAnswer);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    const trimmed = draft.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      await onSubmitEdit(trimmed);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-primary-400/40 bg-primary-900/40 text-white/90 shadow-md">
      <div className="flex items-center justify-between px-4 py-2 border-b border-primary-400/30">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="p-1 rounded hover:bg-primary-500/30 text-primary-100"
            aria-label={collapsed ? '展开' : '折叠'}
          >
            {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
          </button>
          <span className="text-sm font-semibold">
            {questionTitle || '当前问题的回答小结'}
          </span>
        </div>
      </div>

      {!collapsed && (
        <div className="px-4 py-3 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-primary-100/80">AI 分析（只读）</span>
          </div>

          {aiAnalysis && (
            <div className="rounded-md bg-slate-900/60 border border-white/15 px-3 py-2">
              <MessageContent content={aiAnalysis} markdown />
            </div>
          )}

          <div className="flex items-center justify-between gap-2 pt-2 border-t border-white/10 mt-2">
            <span className="text-xs text-primary-100/80">您的答案（支持 Markdown 展示，可编辑）</span>
            <button
              type="button"
              onClick={() => {
                setDraft(userAnswer);
                setEditing((v) => !v);
              }}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs bg-white/10 hover:bg-white/20 text-primary-50"
            >
              <Pencil size={14} /> 编辑
            </button>
          </div>

          {editing ? (
            <div className="space-y-2">
              <textarea
                className="w-full min-h-[120px] rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none focus:ring-1 focus:ring-primary-400/70"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="用你自己的话总结这道题的答案，可以使用 Markdown 格式。"
              />
              <div className="flex justify-end gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setDraft(userAnswer);
                  }}
                  className="px-3 py-1.5 rounded bg-white/5 hover:bg-white/10 text-white/80"
                  disabled={saving}
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  className="px-3 py-1.5 rounded bg-primary-500 hover:bg-primary-400 text-white font-medium disabled:opacity-60"
                  disabled={saving}
                >
                  {saving ? '保存中…' : '保存修改'}
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-md bg-slate-900/60 border border-white/15 px-3 py-2">
              <MessageContent content={userAnswer} markdown />
            </div>
          )}

          <div className="flex flex-wrap gap-2 justify-end pt-1">
            {showNext && (
              <button
                type="button"
                onClick={onNext}
                className="px-3 py-1.5 rounded-lg bg-emerald-500/90 hover:bg-emerald-400 text-white text-xs font-medium"
              >
                没问题啦，下一题
              </button>
            )}
            <button
              type="button"
              onClick={onDiscussMore}
              disabled={!canDiscuss}
              className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs disabled:opacity-40 disabled:cursor-not-allowed"
            >
              让我们再讨论一会？
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

