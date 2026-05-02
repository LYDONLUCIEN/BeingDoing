'use client';

import { useCallback, useRef, useState } from 'react';
import { Copy, MessageSquare, Trash2 } from 'lucide-react';
import type { ChatThread, DimensionConclusionData } from '@/lib/explore/threads';
import { useLocale } from '@/hooks/useLocale';

const SWIPE_DELETE_PX = 72;

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

function conclusionDataPreview(d: DimensionConclusionData | undefined): string {
  if (!d) return '';
  const bits = [d.summary, d.ai_summary, d.final_answer, d.dimension_goal]
    .map((x) => (typeof x === 'string' ? x.trim() : ''))
    .filter(Boolean);
  return bits[0] ?? '';
}

/** 最后一条助手回复（摘要），用于列表主文案（前四维对话） */
function getLastAssistantMessagePreview(thread: ChatThread, noContent: string): string {
  for (let i = thread.messages.length - 1; i >= 0; i--) {
    const m = thread.messages[i];
    if (m.role !== 'assistant') continue;
    if (m.type === 'table_widget') continue;
    let raw = m.content?.trim() ?? '';
    if (!raw && m.type === 'dimension_conclusion') {
      raw = conclusionDataPreview(m.conclusionData) || conclusionDataPreview(thread.dimensionConclusion);
    }
    if (!raw) continue;
    return raw.replace(/\s+/g, ' ');
  }
  return noContent;
}

/** 对话轮数：用户消息数 */
function getTurnCount(thread: ChatThread): number {
  return thread.messages.filter((m) => m.role === 'user').length;
}

function getLastMessageTime(thread: ChatThread): number | null {
  const last = thread.messages[thread.messages.length - 1];
  if (last?.createdAt) return last.createdAt;
  return thread.createdAt;
}

/** 导出为 Markdown，供用户复制存档 */
export function buildThreadMarkdownExport(thread: ChatThread, phaseTitle: string): string {
  const lines: string[] = [
    `# ${phaseTitle}`,
    ``,
    `**会话**：${thread.title || thread.id}`,
    ``,
  ];
  for (const m of thread.messages) {
    const ts = m.createdAt ? new Date(m.createdAt).toLocaleString() : '';
    if (m.type === 'dimension_conclusion' && m.conclusionData) {
      const d = m.conclusionData;
      lines.push(`## 探索结论汇总`, ``);
      if (ts) lines.push(`*${ts}*`, ``);
      if (d.summary || d.ai_summary) lines.push((d.summary || d.ai_summary || '').trim(), ``);
      if (d.keywords?.length) lines.push(`**关键词**：${d.keywords.join('、')}`, ``);
      lines.push(`---`, ``);
      continue;
    }
    if (m.type === 'table_widget') {
      lines.push(`### [表格 Widget]`, ts ? `*${ts}*` : '', ``);
      continue;
    }
    if (m.role === 'user') {
      lines.push(`## 用户`, ts ? `*${ts}*` : '', ``, m.content.trim(), ``, `---`, ``);
    } else if (m.role === 'assistant') {
      const parts: string[] = [`## 助手`, ts ? `*${ts}*` : '', ``];
      if (m.thinkContent?.trim()) {
        parts.push(`### 思考过程`, ``, m.thinkContent.trim(), ``);
      }
      parts.push(m.content.trim(), ``, `---`, ``);
      lines.push(...parts);
    }
  }
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

interface ChatPhaseSidebarProps {
  threads: ChatThread[];
  activeThreadId: string | null;
  onSelectThread: (thread: ChatThread) => void;
  onNewChat: () => void;
  onDeleteThread: (thread: ChatThread) => void;
  canNewChat: boolean;
  /** 当前阶段中文名，写入导出 Markdown */
  phaseTitle: string;
  /** 本阶段已提交锁定：新建/删除等置灰（仍保留「完成并继续」在主区） */
  phaseInteractionLocked?: boolean;
  /** newchat6 哑光侧栏（前四维对话页） */
  careeringMatte?: boolean;
  /** 会话列表下方展示「对话自动保存」提示（主区输入框下方不再重复） */
  showAutoSaveHint?: boolean;
  /** 主对话正在流式输出：非当前会话弱化，提示切换需确认 */
  streamBlocksSessionSwitch?: boolean;
  /** 线程列表是否正在从后端加载（为 true 时隐藏空列表提示，显示加载态） */
  threadsLoading?: boolean;
}

export default function ChatPhaseSidebar({
  threads,
  activeThreadId,
  onSelectThread,
  onNewChat,
  onDeleteThread,
  canNewChat,
  phaseTitle,
  phaseInteractionLocked = false,
  careeringMatte = false,
  showAutoSaveHint = true,
  streamBlocksSessionSwitch = false,
  threadsLoading = false,
}: ChatPhaseSidebarProps) {
  const { t } = useLocale();
  const [deleteTarget, setDeleteTarget] = useState<ChatThread | null>(null);
  const [copyHint, setCopyHint] = useState(false);
  const [openSwipeId, setOpenSwipeId] = useState<string | null>(null);
  const [, setSwipeRenderTick] = useState(0);
  const dragRef = useRef<{
    threadId: string;
    pointerId: number;
    startX: number;
    lastX: number;
    startOffset: number;
    moved: boolean;
  } | null>(null);

  const bumpSwipe = useCallback(() => setSwipeRenderTick((x) => x + 1), []);

  const offsetForThread = useCallback(
    (threadId: string) => {
      // 阶段已锁定：仅允许点选切换会话查看，禁止左滑露出删除
      if (phaseInteractionLocked) return 0;
      const d = dragRef.current;
      if (d && d.threadId === threadId) {
        const dx = d.lastX - d.startX;
        const v = d.startOffset + dx;
        return Math.max(-SWIPE_DELETE_PX, Math.min(0, v));
      }
      if (openSwipeId === threadId) return -SWIPE_DELETE_PX;
      return 0;
    },
    [openSwipeId, phaseInteractionLocked]
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent, thread: ChatThread) => {
      if (e.button !== 0) return;
      if (openSwipeId && openSwipeId !== thread.id) setOpenSwipeId(null);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      dragRef.current = {
        threadId: thread.id,
        pointerId: e.pointerId,
        startX: e.clientX,
        lastX: e.clientX,
        startOffset: offsetForThread(thread.id),
        moved: false,
      };
    },
    [openSwipeId, offsetForThread]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      const d = dragRef.current;
      if (!d || d.pointerId !== e.pointerId) return;
      const moveThreshold = phaseInteractionLocked ? 20 : 8;
      if (Math.abs(e.clientX - d.startX) > moveThreshold) d.moved = true;
      d.lastX = e.clientX;
      bumpSwipe();
    },
    [bumpSwipe, phaseInteractionLocked]
  );

  const endDrag = useCallback(
    (e: React.PointerEvent, thread: ChatThread) => {
      const d = dragRef.current;
      if (!d || d.pointerId !== e.pointerId) return;
      const dx = d.lastX - d.startX;
      const finalOff = Math.max(-SWIPE_DELETE_PX, Math.min(0, d.startOffset + dx));
      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
      dragRef.current = null;
      if (phaseInteractionLocked) {
        setOpenSwipeId(null);
        if (!d.moved) {
          onSelectThread(thread);
        }
        bumpSwipe();
        return;
      }
      if (d.moved) {
        if (finalOff < -SWIPE_DELETE_PX / 2) setOpenSwipeId(thread.id);
        else setOpenSwipeId(null);
      } else {
        onSelectThread(thread);
        setOpenSwipeId(null);
      }
      bumpSwipe();
    },
    [bumpSwipe, onSelectThread, phaseInteractionLocked]
  );

  const handleCopyClick = useCallback(
    async (e: React.MouseEvent, thread: ChatThread) => {
      e.stopPropagation();
      const md = buildThreadMarkdownExport(thread, phaseTitle);
      try {
        await navigator.clipboard.writeText(md);
        setCopyHint(true);
        window.setTimeout(() => setCopyHint(false), 2200);
      } catch {
        window.prompt(t('explore.chat.sidebarCopyFallback'), md);
      }
    },
    [phaseTitle, t]
  );

  const handleDeleteFromSwipe = useCallback((e: React.MouseEvent, thread: ChatThread) => {
    e.stopPropagation();
    setDeleteTarget(thread);
  }, []);

  const handleConfirmDelete = () => {
    if (deleteTarget) {
      onDeleteThread(deleteTarget);
      setDeleteTarget(null);
      setOpenSwipeId(null);
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
        className={`border-b px-4 py-3 sm:px-4 sm:py-3.5 ${careeringMatte ? 'careering-sidebar-header' : ''}`}
        style={careeringMatte ? undefined : { borderColor: 'rgba(0,0,0,0.05)' }}
      >
        <button
          type="button"
          onClick={onNewChat}
          disabled={!canNewChat || phaseInteractionLocked}
          className={`w-full rounded-full px-4 py-2 text-sm font-medium text-white transition-all hover:scale-[0.98] disabled:cursor-not-allowed ${
            phaseInteractionLocked ? 'opacity-35' : 'disabled:opacity-50'
          }`}
          style={{
            background: 'var(--flow-guide, #1d1d1f)',
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
          }}
        >
          + {t('explore.chat.sidebarNewChat')}
        </button>
        {copyHint && (
          <p className="mt-2 text-center text-[11px] font-medium text-emerald-600" role="status">
            {t('explore.chat.sidebarCopyOk')}
          </p>
        )}
        {phaseInteractionLocked ? (
          <p className="mt-1.5 text-[10px] leading-snug text-[var(--flow-text-muted)]">
            {t('explore.chat.sidebarPhaseLockedHint')}
          </p>
        ) : !canNewChat ? (
          <p className="mt-1.5 text-[10px] text-[var(--flow-text-muted)]">{t('explore.chat.sidebarMaxReached')}</p>
        ) : (
          <p className="mt-1.5 text-[10px] text-[var(--flow-text-muted)]">{t('explore.chat.sidebarSwipeDeleteHint')}</p>
        )}
      </div>
      <div className="flow-sidebar-threads min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-3">
        <div className="space-y-1.5">
          {threadsLoading && threads.length === 0 ? (
            <div className="flex items-center justify-center py-6">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent text-[var(--flow-text-muted)]" />
            </div>
          ) : threads.length === 0 ? (
            <p className="text-xs text-[var(--flow-text-muted)] py-4 text-center">{t('explore.chat.sidebarNoThreads')}</p>
          ) : null}
          {threads.map((thread) => {
            const isActive = thread.id === activeThreadId;
            const lastTime = getLastMessageTime(thread);
            const noContent = t('explore.chat.noContent');
            const summary = getLastAssistantMessagePreview(thread, noContent);
            const turnCount = getTurnCount(thread);
            const lastTimeStr = lastTime ? formatLastTime(lastTime, t) : '';
            const off = offsetForThread(thread.id);
            const dragging = dragRef.current?.threadId === thread.id;
            const streamSwitchCue = streamBlocksSessionSwitch && !isActive;

            return (
              <div
                key={thread.id}
                className="relative w-full overflow-hidden rounded-xl"
                style={{ touchAction: 'pan-y' }}
              >
                <div
                  className="grid gap-0"
                  style={{
                    width: `calc(100% + ${SWIPE_DELETE_PX}px)`,
                    gridTemplateColumns: `minmax(0, 1fr) ${SWIPE_DELETE_PX}px`,
                    transform: `translateX(${off}px)`,
                    transition: dragging ? 'none' : 'transform 0.2s ease-out',
                  }}
                >
                  <div
                    role="button"
                    tabIndex={0}
                    title={
                      streamSwitchCue ? t('explore.chat.threadSwitchWhileStreamingHint') : undefined
                    }
                    className={`min-w-0 cursor-pointer rounded-xl px-3 py-2 text-left transition-all ${
                      isActive ? 'shadow-md' : 'hover:opacity-90'
                    } ${
                      streamSwitchCue
                        ? careeringMatte
                          ? 'opacity-[0.82] ring-1 ring-neutral-400/30'
                          : 'opacity-[0.82] ring-1 ring-amber-400/35'
                        : ''
                    }`}
                    style={{
                      background: isActive ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.4)',
                      border: isActive ? '1px solid rgba(0,0,0,0.08)' : '1px solid transparent',
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && onSelectThread(thread)}
                    onPointerDown={(e) => handlePointerDown(e, thread)}
                    onPointerMove={handlePointerMove}
                    onPointerUp={(e) => endDrag(e, thread)}
                    onPointerCancel={(e) => endDrag(e, thread)}
                  >
                    <div className="flex items-start gap-2">
                      {careeringMatte ? (
                        <span
                          className={`mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full ${
                            thread.status === 'completed'
                              ? 'careering-thread-status-dot--done'
                              : 'careering-thread-status-dot--doing'
                          }`}
                          title={
                            thread.status === 'completed'
                              ? t('explore.chat.statusCompleted')
                              : t('explore.chat.statusInProgress')
                          }
                          aria-hidden
                        />
                      ) : (
                        <MessageSquare size={14} className="mt-0.5 flex-shrink-0 text-[var(--flow-text-muted)]" />
                      )}
                      <p
                        className="line-clamp-2 min-w-0 flex-1 text-sm font-medium leading-snug"
                        style={{ color: 'var(--flow-text-body)' }}
                      >
                        {summary}
                      </p>
                      <button
                        type="button"
                        onClick={(e) => handleCopyClick(e, thread)}
                        onPointerDown={(e) => e.stopPropagation()}
                        className="flex-shrink-0 rounded-lg p-1 text-neutral-500 opacity-80 transition-all hover:bg-neutral-100 hover:text-neutral-800 hover:opacity-100"
                        title={t('explore.chat.sidebarCopyThread')}
                        aria-label={t('explore.chat.sidebarCopyThread')}
                      >
                        <Copy size={14} />
                      </button>
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2 pl-3.5">
                      <span className="text-[10px] text-[var(--flow-text-muted)]">
                        {[turnCount > 0 && t('explore.chat.turns', { n: String(turnCount) }), lastTimeStr]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                      <span
                        className={
                          careeringMatte
                            ? `rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                thread.status === 'completed'
                                  ? 'careering-thread-status-badge--done'
                                  : 'careering-thread-status-badge--doing'
                              }`
                            : `rounded-full px-2 py-0.5 text-[10px] font-medium text-white ${
                                thread.status === 'completed' ? 'bg-emerald-500' : 'bg-amber-500'
                              }`
                        }
                      >
                        {thread.status === 'completed'
                          ? t('explore.chat.statusCompleted')
                          : t('explore.chat.statusInProgress')}
                      </span>
                    </div>
                  </div>
                  <div
                    className="flex min-h-full items-stretch justify-stretch"
                    style={{ minHeight: '100%' }}
                  >
                    <button
                      type="button"
                      onClick={(e) => handleDeleteFromSwipe(e, thread)}
                      disabled={phaseInteractionLocked}
                      className="flex w-full flex-col items-center justify-center gap-0.5 bg-red-500 px-1 text-[10px] font-semibold leading-tight text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-40"
                      title={t('explore.chat.sidebarDeleteThread')}
                    >
                      <Trash2 size={16} strokeWidth={2.2} />
                      <span>{t('explore.chat.sidebarDeleteShort')}</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {showAutoSaveHint && (
        <div
          className={`careering-sidebar-auto-save-hint shrink-0 px-4 py-3 ${
            careeringMatte ? 'border-t border-black/[0.06]' : ''
          }`}
          style={careeringMatte ? undefined : { borderTop: '1px solid rgba(0,0,0,0.06)' }}
        >
          <p className="text-center text-xs text-neutral-500">{t('explore.chat.autoSave')}</p>
        </div>
      )}

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
            <p className="text-sm text-[var(--flow-text-muted)] mb-6">{t('explore.chat.sidebarDeleteMessage')}</p>
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
