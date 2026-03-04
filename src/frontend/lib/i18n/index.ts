/**
 * i18n 文案配置
 * 支持中英文，所有 UI 文字通过 t(key) 获取
 */
import { zh } from './locales/zh';
import { en } from './locales/en';

export type LocaleId = 'zh' | 'en';

export type LocaleDict = Record<string, unknown>;

export const locales: Record<LocaleId, LocaleDict> = {
  zh: zh as LocaleDict,
  en: en as LocaleDict,
};

/** 根据路径取值，如 t('nav.home') */
export function getByPath(obj: Record<string, unknown>, path: string): unknown {
  const keys = path.split('.');
  let current: unknown = obj;
  for (const k of keys) {
    if (current == null || typeof current !== 'object') return undefined;
    current = (current as Record<string, unknown>)[k];
  }
  return current;
}
