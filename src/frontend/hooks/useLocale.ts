'use client';

import { useCallback } from 'react';
import { useLocaleStore } from '@/stores/localeStore';
import { locales, getByPath, type LocaleId } from '@/lib/i18n';

function resolvePath(path: string, dict: Record<string, unknown>): unknown {
  const val = getByPath(dict, path);
  return val;
}

/**
 * 获取当前语言的 t 函数
 * 用法：t('nav.home') => '首页'
 * 模板：t('nav.logoutUserTemplate', { name: 'xxx' }) => '退出（xxx）'
 * @param overrideLocale 用于首帧渲染，避免 hydration 时 locale 与服务器不一致
 */
export function useLocale(overrideLocale?: LocaleId) {
  const locale = useLocaleStore((s) => s.locale);
  const setLocale = useLocaleStore((s) => s.setLocale);
  const effectiveLocale = overrideLocale ?? locale;
  const dict = locales[effectiveLocale] as Record<string, unknown>;

  /** 稳定引用，避免依赖 t 的 useEffect（如 chat 页线程同步）在每次渲染时重复跑 */
  const t = useCallback((path: string, params?: Record<string, string>): string => {
    const val = resolvePath(path, dict);
    if (val == null) return path;
    let s = String(val);
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        s = s.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
      }
    }
    return s;
  }, [dict]);

  return { t, locale: effectiveLocale, setLocale, dict };
}
