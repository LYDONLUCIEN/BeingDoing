'use client';

import { useState } from 'react';
import { MessageSquare, Trash2 } from 'lucide-react';
import type { PhaseKey } from '@/lib/explore/session';
import type { ChatThread } from '@/lib/explore/threads';
import { useLocale } from '@/hooks/useLocale';

function formatLastTime(ms: number, t: (k: string, p?: Record<string, string>) => string): string {
  const d = new Date(ms);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const threadDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const timeStr = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  if (threadDay.getTime() === today.getTime()) {
    return t('explore.chat.todayAt', { time: timeStr });
  }
  const diff = (today.getTime() - threadDay.getTime()) / (24 * 60 * 60 * 1000);
  if (diff < 7) return t('explore.chat.daysAgo', { n: String(Math.floor(diff)) });
  return t('explore.chat.monthDay', { m: String(d.getMonth() + 1), d: String(d.getDate()) });
}

/** 取第一条有内容的对话首行作为标题 */
function getFirstLinePreview(thread: ChatThread, noContent: string): string {
  for (const m of thread.messages) {
    if (m.type === 'dimension_conclusion' && m.conclusionData?.summary) {
      const s = m.conclusionData.summary.trim().split('\n')[0].replace(/\s+/g, ' ');
      return s.length > 24 ? s.slice(0, 24) + '…' : s || noContent;
    }
    if (m.content?.trim()) {
      const s = m.content.trim().split('\n')[0].replace(/\s+/g, ' ');
      return s.length > 24 ? s.slice(0, 24) + '…' : s;
    }
  }
  return noContent;
}

/** 对话轮数：用户消息数 */
function getTurnCount(thread: ChatThread): number {
  return thread.messages.filter((m) => m.role === 'user').length;
}

function getLastMessagePreview(thread: ChatThread, noContent: string): string {
  const last = thread.messages[thread.messages.length - 1];
  if (!last?.content) return noContent;
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
  /** 本阶段已提交锁定：新建/删除等置灰（仍保留「完成并继续」在主区） */
  phaseInteractionLocked?: boolean;
  /** newchat6 哑光侧栏（前四维对话页） */
  careeringMatte?: boolean;
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
  phaseInteractionLocked = false,
  careeringMatte = false,
}: ChatPhaseSidebarProps) {
  const { t } = useLocale();
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
      className={`w-72 flex-shrink-0 flex flex-col min-h-0 border-r ${careeringMatte ? 'careering-sidebar' : ''}`}
      style={
        careeringMatte
          ? undefined
          : {
              background: 'rgba(255, 255, 255, 0.6)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              borderColor: 'rgba(0, 0, 0, 0.06)',
            }
      }
    >
      <div
        className={`p-5 border-b ${careeringMatte ? 'careering-sidebar-header' : ''}`}
        style={careeringMatte ? undefined : { borderColor: 'rgba(0,0,0,0.05)' }}
      >
        <p className="text-xs font-medium text-[var(--flow-text-muted)] mb-3 tracking-wider">
          {phaseLabel} · {t('explore.chat.threadList')}
        </p>
        <button
          type="button"
          onClick={onNewChat}
          disabled={!canNewChat || phaseInteractionLocked}
          className={`w-full px-5 py-2.5 rounded-full text-sm font-medium text-white transition-all hover:scale-[0.98] disabled:cursor-not-allowed ${
            phaseInteractionLocked ? 'opacity-35' : 'disabled:opacity-50'
          }`}
          style={{
            background: 'var(--flow-guide, #1d1d1f)',
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
          }}
        >
          + {t('explore.chat.sidebarNewChat')}
        </button>
        {phaseInteractionLocked ? (
          <p className="text-[10px] text-[var(--flow-text-muted)] mt-2 leading-snug">
            {t('explore.chat.sidebarPhaseLockedHint')}
          </p>
        ) : !canNewChat ? (
          <p className="text-[10px] text-[var(--flow-text-muted)] mt-2">{t('explore.chat.sidebarMaxReached')}</p>
        ) : null}
      </div>
      <div className="flow-sidebar-threads flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-4">
        <div className="space-y-2">
          {threads.length === 0 && (
            <p className="text-xs text-[var(--flow-text-muted)] py-4 text-center">{t('explore.chat.sidebarNoThreads')}</p>
          )}
          {threads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            const lastTime = getLastMessageTime(thread);
            const noContent = t('explore.chat.noContent');
            const title = getFirstLinePreview(thread, noContent);
            const turnCount = getTurnCount(thread);
            const preview = getLastMessagePreview(thread, noContent);
            const lastTimeStr = lastTime ? formatLastTime(lastTime, t) : '';
            return (
              <div
                key={thread.id}
                className={`group relative w-full text-left px-4 py-3 rounded-xl transition-all cursor-pointer ${
                  isActive ? 'shadow-md scale-[1.02]' : 'hover:opacity-90'
                }`}
                style={{
                  background: isActive ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.4)',
                  border: isActive ? '1px solid rgba(0,0,0,0.08)' : '1px solid transparent',
                }}
                role="button"
                tabIndex={0}
                onClick={() => onSelectThread(thread)}
                onKeyDown={(e) => e.key === 'Enter' && onSelectThread(thread)}
              >
                <div className="flex items-start gap-2 mb-1.5">
                  {careeringMatte ? (
                    <span
                      className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full"
                      style={{
                        backgroundColor:
                          thread.status === 'completed' ? '#22c55e' : '#fbbf24',
                        boxShadow:
                          thread.status === 'completed'
                            ? '0 0 0 1px rgba(34,197,94,0.25)'
                            : '0 0 0 1px rgba(251,191,36,0.35)',
                      }}
                      title={
                        thread.status === 'completed'
                          ? t('explore.chat.statusCompleted')
                          : t('explore.chat.statusInProgress')
                      }
                      aria-hidden
                    />
                  ) : (
                    <MessageSquare size={14} className="text-[var(--flow-text-muted)] flex-shrink-0 mt-0.5" />
                  )}
                  <span
                    className="text-sm font-medium truncate flex-1 leading-tight"
                    style={{ color: 'var(--flow-text-body)' }}
                  >
                    {title}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => handleDeleteClick(e, thread)}
                    disabled={phaseInteractionLocked}
                    className="opacity-0 group-hover:opacity-60 hover:opacity-100 p-1 rounded-lg hover:bg-red-100 text-red-500 transition-all flex-shrink-0 disabled:opacity-25 disabled:pointer-events-none disabled:hover:opacity-25"
                    title={t('explore.chat.sidebarDeleteThread')}
                    aria-label={t('explore.chat.sidebarDeleteThread')}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <p className="text-xs line-clamp-2 mb-2" style={{ color: 'var(--flow-text-muted)' }}>
                  {preview}
                </p>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] text-[var(--flow-text-muted)]">
                    {[turnCount > 0 && t('explore.chat.turns', { n: String(turnCount) }), lastTimeStr].filter(Boolean).join(' · ')}
                  </span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium text-white ${
                      thread.status === 'completed'
                        ? 'bg-emerald-500'
                        : 'bg-amber-500'
                    }`}
                  >
                    {thread.status === 'completed' ? t('explore.chat.statusCompleted') : t('explore.chat.statusInProgress')}
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
              {t('explore.chat.sidebarDeleteConfirm')}
            </h3>
            <p className="text-sm text-[var(--flow-text-muted)] mb-6">
              {t('explore.chat.sidebarDeleteMessage')}
            </p>
            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 rounded-xl text-sm font-medium text-[var(--flow-text-muted)] hover:bg-neutral-100 transition-colors"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-red-500 hover:bg-red-600 transition-colors"
              >
                {t('explore.chat.sidebarDeleteConfirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
