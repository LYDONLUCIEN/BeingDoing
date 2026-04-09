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
  const mr = computeMaxReachedFromSnapshots(p);
  const fs = p.filter_step ?? 0;
  if (step <= mr) return true;
  if (fs > 0 && step === fs) return true;
  return false;
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
