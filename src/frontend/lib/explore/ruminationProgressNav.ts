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
 * 筛选子步可向前浏览到的最右步：含已提交步、当前 filter_step、以及已有 initial/submitted 快照的步。
 */
export function computeFurthestBrowsableFilterStep(p: RuminationProgress | null): number {
  if (!p) return 1;
  const fs = p.filter_step ?? 0;
  const mr = computeMaxReachedFromSnapshots(p);
  let maxSnap = 0;
  const snaps = p.filter_step_snapshots ?? {};
  for (const [key, ent] of Object.entries(snaps)) {
    const n = parseInt(key, 10);
    if (Number.isNaN(n) || n < 1 || n > RUMINATION_FILTER_STEP_MAX) continue;
    const e = ent as { initial?: unknown; submitted?: unknown } | null;
    if (e != null && (e.initial != null || e.submitted != null)) {
      maxSnap = Math.max(maxSnap, n);
    }
  }
  return Math.min(RUMINATION_FILTER_STEP_MAX, Math.max(1, fs, mr, maxSnap));
}
