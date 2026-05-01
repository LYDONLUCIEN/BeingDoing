import type { RuminationProgress } from '@/lib/api/rumination';

/** 与后端 MAX_FILTER_STEP 一致 */
export const RUMINATION_FILTER_STEP_MAX = 7;

export function computeMaxReachedFromSnapshots(p: RuminationProgress | null): number {
  if (!p?.filter_step_snapshots) return 0;
  let m = 0;
  for (const [key, snap] of Object.entries(p.filter_step_snapshots)) {
    const n = parseInt(key, 10);
    if (Number.isNaN(n)) continue;
    if (snap?.submitted != null) m = Math.max(m, n);
  }
  return m;
}

/**
 * 某筛选子步是否允许进入（进度条点击 / 上一阶段·下一阶段）。
 * 规则：已提交过的步（submitted）任意回看；未提交的步仅当等于当前后端 filter_step 时可进入。
 * 不将「仅有 initial、无 submitted」的快照视为已到达（短链保险快照否则会误开 step6）。
 */
export function isRuminationFilterStepReachable(
  step: number,
  p: RuminationProgress | null
): boolean {
  if (step < 1 || step > RUMINATION_FILTER_STEP_MAX) return false;
  if (!p) return step === 1;

  const ms = p.main_section;
  const fs = p.filter_step ?? 0;

  // 已进入最终选择或之后：进度条 7 段用于回看筛选表，须允许点击任意 1–7（否则短链 snapshot 未标 submitted 时第 7 段会灰掉）
  if (ms === 'final_choice' || ms === 'recommend' || ms === 'end') {
    return true;
  }

  // 仍在筛选且服务端当前子步已到 7：同样允许在 1–7 间跳转（与 furthest 快照不完全一致时的兜底）
  if (ms === 'filter' && fs >= RUMINATION_FILTER_STEP_MAX) {
    return true;
  }

  const mr = computeMaxReachedFromSnapshots(p);
  if (step <= mr) return true;
  if (fs > 0 && step === fs) return true;
  return false;
}

/**
 * 五轮结束后回看时的最佳展示步骤。
 * 优先 step7 submitted 快照（终选结果），无则回退到 max_reached step。
 * 用于 recommend/end 终态下自动加载左栏只读结果表。
 */
export function resolveReviewStepAfterCompletion(p: RuminationProgress | null): number {
  if (!p) return 0;
  const snaps = p.filter_step_snapshots ?? {};
  // 优先 step7 submitted
  const s7 = snaps['7'];
  if (s7?.submitted != null) return 7;
  // 回退到 max_reached
  return computeMaxReachedFromSnapshots(p);
}

/**
 * 兼容旧调用：可浏览的「序号上界」近似值（用于少数仍需单值的逻辑）。
 * 注意：进度条分段是否可点请以 {@link isRuminationFilterStepReachable} 为准，勿用本值做 step<=N 判断。
 */
export function computeFurthestBrowsableFilterStep(p: RuminationProgress | null): number {
  if (!p) return 1;
  const fs = p.filter_step ?? 0;
  const mr = computeMaxReachedFromSnapshots(p);
  return Math.min(RUMINATION_FILTER_STEP_MAX, Math.max(1, fs, mr));
}
