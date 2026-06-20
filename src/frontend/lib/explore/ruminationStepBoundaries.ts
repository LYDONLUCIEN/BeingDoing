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

  // ── 优先按 filterStep 标签过滤（后端已打标签的消息）──
  const hasFilterStepTags = messages.some((m) => m.filterStep != null && m.filterStep !== undefined);
  if (hasFilterStepTags) {
    return messages.filter(
      (m) => m.filterStep === viewStep && m.type !== 'table_widget',
    );
  }

  // ── 降级：按下标切片（兼容历史无标签数据）──
  const b = ensureDefaultStepOne(boundaries);
  let start =
    viewStep === 1
      ? b['1'] ?? 0
      : b[String(viewStep)] !== undefined
        ? b[String(viewStep)]!
        : messages.length;
  let end = messages.length;
  const active = opts?.activeFilterStep;
  const viewingCurrentFilterStep =
    typeof active === 'number' && active > 0 && viewStep === active;
  /**
   * 边界若因异步晚于首条消息写入，可能被记成 len，导致起点==len 本步对话全被裁掉。
   * 正在查看当前子步时，回退到上一子步起点，至少能看到本步新消息（可能短暂与上一步末尾重叠，待边界修正后消失）。
   */
  if (
    viewingCurrentFilterStep &&
    viewStep > 1 &&
    start === messages.length &&
    messages.length > 0
  ) {
    const prev = b[String(viewStep - 1)];
    if (prev !== undefined && prev < messages.length) {
      start = prev;
    }
  }
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
 * 判断当前 viewStep 是否处于「回看模式」。
 * 条件：后端有 submitted 快照，且 viewStep 不等于后端当前活跃 filter_step。
 * 回看模式下表格只读，消息区仅展示该步切片，不影响当前数据。
 */
export function isRuminationReviewMode(
  viewStep: number,
  progress: { main_section?: string | null; filter_step?: number | null; filter_step_snapshots?: Record<string, { submitted?: unknown }>; rumination_neg_state?: { status?: string | null; step?: number | null } | null; pending_table_submit?: { step?: number | null } | null } | null
): boolean {
  if (!progress || viewStep < 1) return false;
  const ms = progress.main_section;

  // 不在筛选段（或已完成）：所有步骤都是回看
  if (ms !== 'filter') return true;

  // neg_gate 正在进行的步骤不是回看（用户正在该步深度讨论）
  const negState = progress.rumination_neg_state;
  if (negState && negState.status && negState.status !== 'closed') {
    if (typeof negState.step === 'number' && negState.step === viewStep) return false;
  }
  // pending_table_submit 指向的步骤也不是回看
  const pending = progress.pending_table_submit;
  if (pending && typeof pending.step === 'number' && pending.step === viewStep) return false;

  // 有 submitted 快照 → 该步已确认 → 回看
  const snap = progress.filter_step_snapshots?.[String(viewStep)];
  if (snap?.submitted != null) return true;

  // 无 submitted → 尚未确认 → 可编辑
  return false;
}

/**
 * 「重新填写」从当前筛选子步起直到对话末尾整段删除（与后端从本步起清空后续快照一致）。
 * 保留本子步起点边界 b[viewStep]，删除 viewStep+1.. 的边界键。
 * 若 b[viewStep] 不存在，向前回退到最近的已有 boundary；若仍无则截断到 0。
 * 仅允许从当前活跃步（非回看模式）执行。
 */
export function cutMessagesForRuminationStepRefill(
  messages: ThreadMessage[],
  viewStep: number,
  boundaries: Record<string, number>
): { messages: ThreadMessage[]; boundaries: Record<string, number> } {
  const b = ensureDefaultStepOne({ ...boundaries });
  const sk = String(viewStep);
  let lo = b[sk];
  if (lo === undefined) {
    // 向前回退到最近的已有 boundary
    for (let s = viewStep - 1; s >= 1; s--) {
      if (b[String(s)] !== undefined) {
        lo = b[String(s)];
        break;
      }
    }
    if (lo === undefined) lo = 0;
  }
  const hi = messages.length;
  const newB: Record<string, number> = { ...b };
  for (let s = viewStep + 1; s <= 12; s++) {
    delete newB[String(s)];
  }
  if (lo >= hi) {
    // boundary 值异常（>= 消息总数）时，回退到按 filterStep 标签裁剪，
    // 确保 viewStep 及之后的消息被清除。
    const cut = messages.filter((m) => {
      if (m.type === 'table_widget') return false;
      if (m.filterStep == null) return true; // 无标签消息保留（如 entry greeting）
      return m.filterStep < viewStep;
    });
    return { messages: cut, boundaries: newB };
  }
  return { messages: messages.slice(0, lo), boundaries: newB };
}
