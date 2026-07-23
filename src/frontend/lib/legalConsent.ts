/**
 * 隐私政策/服务条款 同意状态的本地记忆。
 * 勾选后写入 localStorage，下次打开登录/注册表单时自动预勾选；
 * 用户取消勾选则清除记忆。
 */

const STORAGE_KEY = 'bd_legal_consent_v1';

/** 读取记住的同意状态（SSR 或异常时返回 false） */
export function getStoredLegalConsent(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

/** 记忆/清除同意状态 */
export function setStoredLegalConsent(agreed: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    if (agreed) {
      window.localStorage.setItem(STORAGE_KEY, '1');
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // localStorage 不可用（隐私模式等）时静默失败，不影响表单
  }
}
