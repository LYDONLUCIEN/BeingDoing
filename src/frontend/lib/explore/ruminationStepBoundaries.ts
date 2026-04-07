/**
 * 沉淀筛选子步与消息列表下标的映射（方案 B：仅存前端 + localStorage）。
 * 同一 thread 下，step N 的聊天区展示 messages[start, nextStepStart)。
 */

import type { ThreadMessage } from '@/lib/explore/threads';

const PREFIX = 'bd_rumination_step_idx_v1';

export function ruminationStepBoundaryKey(activationCode: string, threadId: string): string {
  return `${PREFIX}_${activationCode}_${threadId}`;
}

export function loadRuminationStepBoundaries(
  activationCode: string | null,
  threadId: string | null
): Record<string, number> {
  if (!activationCode || !threadId || typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(ruminationStepBoundaryKey(activationCode, threadId));
    if (raw) {
      const p = JSON.parse(raw) as Record<string, number>;
      return typeof p === 'object' && p ? p : {};
    }
  } catch {
    /* ignore */
  }
  return {};
}

export function saveRuminationStepBoundaries(
  activationCode: string,
  threadId: string,
  boundaries: Record<string, number>
): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(
      ruminationStepBoundaryKey(activationCode, threadId),
      JSON.stringify(boundaries)
    );
  } catch {
    /* ignore */
  }
}

/** 确保第 1 步从索引 0 开始 */
export function ensureDefaultStepOne(boundaries: Record<string, number>): Record<string, number> {
  if (boundaries['1'] === undefined) return { ...boundaries, '1': 0 };
  return boundaries;
}

export type SliceRuminationMessagesOpts = {
  /**
   * 后端当前筛选子步（main_section=filter 且 >0）。
   * 与 viewStep 一致时，聊天区延伸到 messages 末尾，避免已存在的「下一子步起点」边界把新发出的用户/助手消息整段裁掉。
   */
  activeFilterStep?: number | null;
  /** false：opening/review 等非筛选主阶段，不按子步切片，展示完整对话 */
  inFilterSection?: boolean;
};

export function sliceMessagesForRuminationStep(
  messages: ThreadMessage[],
  viewStep: number,
  boundaries: Record<string, number>,
  opts?: SliceRuminationMessagesOpts
): ThreadMessage[] {
  if (opts?.inFilterSection === false) {
    return messages.filter((m) => m.type !== 'table_widget');
  }

  const b = ensureDefaultStepOne(boundaries);
  const start =
    viewStep === 1
      ? b['1'] ?? 0
      : b[String(viewStep)] !== undefined
        ? b[String(viewStep)]
        : messages.length;
  let end = messages.length;
  const active = opts?.activeFilterStep;
  const viewingCurrentFilterStep =
    typeof active === 'number' && active > 0 && viewStep === active;
  if (!viewingCurrentFilterStep) {
    for (let s = viewStep + 1; s <= 12; s++) {
      const x = b[String(s)];
      if (x != null) {
        end = x;
        break;
      }
    }
  }
  const lo = Math.max(0, Math.min(start, messages.length));
  const hi = Math.max(lo, Math.min(end, messages.length));
  return messages.slice(lo, hi).filter((m) => m.type !== 'table_widget');
}

/**
 * 「重新填写」从当前筛选子步起直到对话末尾整段删除（与后端从本步起清空后续快照一致）。
 * 保留本子步起点边界 b[viewStep]，删除 viewStep+1.. 的边界键。
 */
export function cutMessagesForRuminationStepRefill(
  messages: ThreadMessage[],
  viewStep: number,
  boundaries: Record<string, number>
): { messages: ThreadMessage[]; boundaries: Record<string, number> } {
  const b = ensureDefaultStepOne({ ...boundaries });
  const sk = String(viewStep);
  const lo = b[sk];
  if (lo === undefined) {
    return { messages, boundaries: b };
  }
  const hi = messages.length;
  const newB: Record<string, number> = { ...b };
  for (let s = viewStep + 1; s <= 12; s++) {
    delete newB[String(s)];
  }
  if (lo >= hi) {
    return { messages, boundaries: newB };
  }
  return { messages: messages.slice(0, lo), boundaries: newB };
}
