/**
 * 旧浏览器内核检测（ADR-0020）。
 *
 * 采用**特性检测**而非 UA 嗅探：国产双核浏览器 UA 千奇百怪且可切换内核，
 * 直接探测本项目实际依赖的 CSS 特性更可靠。判定为「旧内核」即展示
 * LegacyBrowserNotice 推荐换浏览器；用户不切换则由 vh 回退/静态色兜底
 * 保证基本可用。
 *
 * 持久化用 localStorage（浏览器维度，而非账号维度）——提示针对的是
 * 「当前这台浏览器」，换浏览器后应重新检测提示。
 */

const DISMISS_KEY = 'bd-legacy-browser-dismissed';

/** 是否旧内核（SSR 下返回 false，由客户端水合后再判定，避免闪烁误报） */
export function isLegacyKernel(): boolean {
  if (typeof window === 'undefined') return false;
  if (typeof CSS === 'undefined' || typeof CSS.supports !== 'function') return true;
  // dvh（Chrome 108+）：探索/沉淀页外壳布局硬依赖，缺失会导致布局塌陷
  if (!CSS.supports('height', '100dvh')) return true;
  // color-mix（Chrome 111+）：聊天气泡配色
  if (!CSS.supports('color', 'color-mix(in srgb, red, blue)')) return true;
  return false;
}

/** 用户是否已点过「不再提示」 */
export function isLegacyNoticeDismissed(): boolean {
  try {
    return window.localStorage.getItem(DISMISS_KEY) === '1';
  } catch {
    return false;
  }
}

/** 持久化「不再提示」 */
export function dismissLegacyNotice(): void {
  try {
    window.localStorage.setItem(DISMISS_KEY, '1');
  } catch {
    /* 隐私模式等写入失败时降级为本次会话仍提示 */
  }
}

/** 是否应展示旧内核提示弹窗 */
export function shouldShowLegacyNotice(): boolean {
  return isLegacyKernel() && !isLegacyNoticeDismissed();
}
