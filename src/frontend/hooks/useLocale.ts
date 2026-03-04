'use client';

import { useLocaleStore } from '@/stores/localeStore';
import { locales, getByPath } from '@/lib/i18n';

function resolvePath(path: string, dict: Record<string, unknown>): unknown {
  const val = getByPath(dict, path);
  return val;
}

/**
 * 获取当前语言的 t 函数
 * 用法：t('nav.home') => '首页'
 * 模板：t('nav.logoutUserTemplate', { name: 'xxx' }) => '退出（xxx）'
 */
export function useLocale() {
  const locale = useLocaleStore((s) => s.locale);
  const setLocale = useLocaleStore((s) => s.setLocale);
  const dict = locales[locale] as Record<string, unknown>;

  function t(path: string, params?: Record<string, string>): string {
    const val = resolvePath(path, dict);
    if (val == null) return path;
    let s = String(val);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
      }
    }
    return s;
  }

  return { t, locale, setLocale, dict };
}
