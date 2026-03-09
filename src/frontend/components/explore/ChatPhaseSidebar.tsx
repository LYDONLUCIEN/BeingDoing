'use client';

import { useState } from 'react';
import { MessageSquare, Trash2 } from 'lucide-react';
import type { PhaseKey } from '@/lib/explore/session';
import type { ChatThread } from '@/lib/explore/threads';

function formatLastTime(ms: number): string {
  const d = new Date(ms);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const threadDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (threadDay.getTime() === today.getTime()) {
    return `今天 ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  }
  const diff = (today.getTime() - threadDay.getTime()) / (24 * 60 * 60 * 1000);
  if (diff < 7) return `${Math.floor(diff)} 天前`;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/** 取第一条有内容的对话首行作为标题 */
function getFirstLinePreview(thread: ChatThread): string {
  for (const m of thread.messages) {
    if (m.type === 'dimension_conclusion' && m.conclusionData?.summary) {
      const s = m.conclusionData.summary.trim().split('\n')[0].replace(/\s+/g, ' ');
      return s.length > 24 ? s.slice(0, 24) + '…' : s || '暂无内容';
    }
    if (m.content?.trim()) {
      const s = m.content.trim().split('\n')[0].replace(/\s+/g, ' ');
      return s.length > 24 ? s.slice(0, 24) + '…' : s;
    }
  }
  return '暂无内容';
}

/** 对话轮数：用户消息数 */
function getTurnCount(thread: ChatThread): number {
  return thread.messages.filter((m) => m.role === 'user').length;
}

function getLastMessagePreview(thread: ChatThread): string {
  const last = thread.messages[thread.messages.length - 1];
  if (!last?.content) return '暂无内容';
  const s = last.content.trim().replace(/\s+/g, ' ');
  return s.length > 36 ? s.slice(0, 36) + '…' : s;
}

function getLastMessageTime(thread: ChatThread): number | null {
  const last = thread.messages[thread.messages.length - 1];
  if (last?.createdAt) return last.createdAt;
  return thread.createdAt;
}

interface ChatPhaseSidebarProps {
  phase: PhaseKey;
  phaseLabel: string;
  threads: ChatThread[];
  activeThreadId: string | null;
  onSelectThread: (thread: ChatThread) => void;
  onNewChat: () => void;
  onDeleteThread: (thread: ChatThread) => void;
  canNewChat: boolean;
}

export default function ChatPhaseSidebar({
  phase,
  phaseLabel,
  threads,
  activeThreadId,
  onSelectThread,
  onNewChat,
  onDeleteThread,
  canNewChat,
}: ChatPhaseSidebarProps) {
  const [deleteTarget, setDeleteTarget] = useState<ChatThread | null>(null);

  const handleDeleteClick = (e: React.MouseEvent, thread: ChatThread) => {
    e.stopPropagation();
    setDeleteTarget(thread);
  };

  const handleConfirmDelete = () => {
    if (deleteTarget) {
      onDeleteThread(deleteTarget);
      setDeleteTarget(null);
    }
  };

  return (
    <aside
      className="w-72 flex-shrink-0 flex flex-col min-h-0 border-r"
      style={{
        background: 'rgba(255, 255, 255, 0.6)',
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        borderColor: 'rgba(0, 0, 0, 0.06)',
      }}
    >
      <div className="p-5 border-b" style={{ borderColor: 'rgba(0,0,0,0.05)' }}>
        <p className="text-xs font-medium text-[var(--flow-text-muted)] mb-3 tracking-wider">
          {phaseLabel} · 对话列表
        </p>
        <button
          type="button"
          onClick={onNewChat}
          disabled={!canNewChat}
          className="w-full px-5 py-2.5 rounded-full text-sm font-medium text-white transition-all hover:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            background: 'var(--flow-guide, #1d1d1f)',
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
          }}
        >
          + 新建对话
        </button>
        {!canNewChat && (
          <p className="text-[10px] text-[var(--flow-text-muted)] mt-2">已达上限（最多 5 个）</p>
        )}
      </div>
      <div className="flow-sidebar-threads flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-4">
        <div className="space-y-2">
          {threads.length === 0 && (
            <p className="text-xs text-[var(--flow-text-muted)] py-4 text-center">暂无对话，点击上方新建</p>
          )}
          {threads.map((t, i) => {
            const isActive = t.id === activeThreadId;
            const lastTime = getLastMessageTime(t);
            const title = getFirstLinePreview(t);
            const turnCount = getTurnCount(t);
            const preview = getLastMessagePreview(t);
            return (
              <div
                key={t.id}
                className={`group relative w-full text-left px-4 py-3 rounded-xl transition-all cursor-pointer ${
                  isActive ? 'shadow-md scale-[1.02]' : 'hover:opacity-90'
                }`}
                style={{
                  background: isActive ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.4)',
                  border: isActive ? '1px solid rgba(0,0,0,0.08)' : '1px solid transparent',
                }}
                role="button"
                tabIndex={0}
                onClick={() => onSelectThread(t)}
                onKeyDown={(e) => e.key === 'Enter' && onSelectThread(t)}
              >
                <div className="flex items-start gap-2 mb-1.5">
                  <MessageSquare size={14} className="text-[var(--flow-text-muted)] flex-shrink-0 mt-0.5" />
                  <span
                    className="text-sm font-medium truncate flex-1 leading-tight"
                    style={{ color: 'var(--flow-text-body)' }}
                  >
                    {title}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => handleDeleteClick(e, t)}
                    className="opacity-0 group-hover:opacity-60 hover:opacity-100 p-1 rounded-lg hover:bg-red-100 text-red-500 transition-all flex-shrink-0"
                    title="删除对话"
                    aria-label="删除对话"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className="text-xs line-clamp-2 mb-2" style={{ color: 'var(--flow-text-muted)' }}>
                  {preview}
                </p>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] text-[var(--flow-text-muted)]">
                    {[turnCount > 0 && `${turnCount} 轮`, lastTime && formatLastTime(lastTime)].filter(Boolean).join(' · ')}
                  </span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium text-white ${
                      t.status === 'completed'
                        ? 'bg-emerald-500'
                        : 'bg-amber-500'
                    }`}
                  >
                    {t.status === 'completed' ? '已完成' : '进行中'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 删除确认弹窗 */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
          onClick={() => setDeleteTarget(null)}
          role="presentation"
        >
          <div
            className="bg-white rounded-2xl shadow-xl p-6 max-w-sm mx-4"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-confirm-title"
          >
            <h3 id="delete-confirm-title" className="text-lg font-semibold text-[var(--flow-text-body)] mb-2">
              确认删除
            </h3>
            <p className="text-sm text-[var(--flow-text-muted)] mb-6">
              确定要删除该对话吗？删除后无法恢复。
            </p>
            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 rounded-xl text-sm font-medium text-[var(--flow-text-muted)] hover:bg-neutral-100 transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-red-500 hover:bg-red-600 transition-colors"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
