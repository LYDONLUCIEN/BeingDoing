import type { ChatThread, DimensionConclusionData, ThreadMessage } from './threads';

/**
 * 侧栏线程预览/元信息计算（2026-10-05 性能优化抽离）：
 * ChatPhaseSidebar（非活动线程回退路径）与 chat 页（活动线程实时元信息，
 * 替代整份 messages 注入侧栏）共用同一口径，避免两处实现漂移。
 */

export function conclusionDataPreview(d: DimensionConclusionData | undefined): string {
  if (!d) return '';
  const bits = [d.summary, d.ai_summary, d.final_answer, d.dimension_goal]
    .map((x) => (typeof x === 'string' ? x.trim() : ''))
    .filter(Boolean);
  return bits[0] ?? '';
}

/** 最后一条助手回复（摘要），用于列表主文案（前四维对话） */
export function getLastAssistantMessagePreview(
  thread: Pick<ChatThread, 'messages' | 'dimensionConclusion'>,
  noContent: string
): string {
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
export function getTurnCount(thread: Pick<ChatThread, 'messages'>): number {
  return thread.messages.filter((m) => m.role === 'user').length;
}

export function getLastMessageTime(
  thread: Pick<ChatThread, 'messages'> & { createdAt?: number }
): number | null {
  const last = thread.messages[thread.messages.length - 1];
  if (last?.createdAt) return last.createdAt;
  return thread.createdAt ?? null;
}

/**
 * 活动线程的侧栏元信息：chat 页对流式中的线程在父级单遍计算这 3 个原始值
 * 传入侧栏（旧 threadsForSidebar 每帧注入整份 messages，击穿侧栏 memo）。
 * 口径与上方各函数完全一致。
 */
export function computeActiveThreadSidebarMeta(
  messages: ThreadMessage[],
  thread: Pick<ChatThread, 'dimensionConclusion' | 'createdAt'> | undefined,
  noContent: string
): { preview: string; turnCount: number; lastAt: number | null } {
  const preview = getLastAssistantMessagePreview(
    { messages, dimensionConclusion: thread?.dimensionConclusion },
    noContent
  );
  const last = messages[messages.length - 1];
  return {
    preview,
    turnCount: getTurnCount({ messages }),
    lastAt: last?.createdAt ?? thread?.createdAt ?? null,
  };
}
