/** 简单行级 diff，无第三方依赖。 */

export type DiffRowType = 'unchanged' | 'added' | 'removed' | 'changed';

export interface DiffRow {
  type: DiffRowType;
  left?: string;
  right?: string;
}

function lcsTable(aLines: string[], bLines: string[]): number[][] {
  const m = aLines.length;
  const n = bLines.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 1; i <= m; i += 1) {
    for (let j = 1; j <= n; j += 1) {
      if (aLines[i - 1] === bLines[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }
  return dp;
}

/** 对比两段文本，返回 side-by-side 行 diff。 */
export function computeLineDiff(left: string, right: string): DiffRow[] {
  const aLines = left.split('\n');
  const bLines = right.split('\n');
  const dp = lcsTable(aLines, bLines);

  type Op =
    | { kind: 'same'; line: string }
    | { kind: 'remove'; line: string }
    | { kind: 'add'; line: string };

  const ops: Op[] = [];
  let i = aLines.length;
  let j = bLines.length;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && aLines[i - 1] === bLines[j - 1]) {
      ops.unshift({ kind: 'same', line: aLines[i - 1] });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.unshift({ kind: 'add', line: bLines[j - 1] });
      j -= 1;
    } else if (i > 0) {
      ops.unshift({ kind: 'remove', line: aLines[i - 1] });
      i -= 1;
    }
  }

  const rows: DiffRow[] = [];
  let idx = 0;
  while (idx < ops.length) {
    const cur = ops[idx];
    const next = ops[idx + 1];
    if (cur.kind === 'remove' && next?.kind === 'add') {
      rows.push({ type: 'changed', left: cur.line, right: next.line });
      idx += 2;
      continue;
    }
    if (cur.kind === 'same') {
      rows.push({ type: 'unchanged', left: cur.line, right: cur.line });
    } else if (cur.kind === 'remove') {
      rows.push({ type: 'removed', left: cur.line });
    } else {
      rows.push({ type: 'added', right: cur.line });
    }
    idx += 1;
  }
  return rows;
}

export const DIFF_ROW_CLASS: Record<DiffRowType, string> = {
  unchanged: '',
  added: 'bg-emerald-50 dark:bg-emerald-950/30',
  removed: 'bg-rose-50 dark:bg-rose-950/30',
  changed: 'bg-amber-50 dark:bg-amber-950/30',
};
