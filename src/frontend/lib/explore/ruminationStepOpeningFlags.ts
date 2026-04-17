/**
 * 沉淀子步「开始引导」流式文案：同一线程内每个子步只自动播放一次；
 * 用户选择「重新填写」时从该步起清除标记，便于再次生成。
 */

function key(activationCode: string, threadId: string, filterStep: number) {
  return `bd_rum_open_shown_${activationCode}_${threadId}_${filterStep}`;
}

export function hasRuminationStepOpeningBeenShown(
  activationCode: string,
  threadId: string,
  filterStep: number
): boolean {
  if (typeof window === 'undefined' || !threadId.trim()) return false;
  try {
    return window.sessionStorage.getItem(key(activationCode, threadId, filterStep)) === '1';
  } catch {
    return false;
  }
}

export function markRuminationStepOpeningShown(
  activationCode: string,
  threadId: string,
  filterStep: number
): void {
  if (typeof window === 'undefined' || !threadId.trim()) return;
  try {
    window.sessionStorage.setItem(key(activationCode, threadId, filterStep), '1');
  } catch {
    /* quota / private mode */
  }
}

/** 从「重新填写」的起始子步起清除该步及之后子步的标记（含第 7 步） */
export function clearRuminationStepOpeningShownFromStep(
  activationCode: string,
  threadId: string,
  fromStepInclusive: number
): void {
  if (typeof window === 'undefined' || !threadId.trim()) return;
  const lo = Math.max(1, Math.min(7, Math.floor(fromStepInclusive)));
  try {
    for (let s = lo; s <= 7; s++) {
      window.sessionStorage.removeItem(key(activationCode, threadId, s));
    }
  } catch {
    /* ignore */
  }
}
