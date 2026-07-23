'use client';

import { useEffect } from 'react';
import type { UseFormSetValue, UseFormWatch } from 'react-hook-form';
import { getStoredLegalConsent, setStoredLegalConsent } from '@/lib/legalConsent';

/**
 * 将表单中的 agreeTerms 字段与 localStorage 记忆打通：
 * - 挂载时：若用户上次勾选过，则自动预勾选
 * - 用户变更勾选时：实时记忆/清除
 *
 * 用于登录、注册等所有需要「同意隐私政策/服务条款」的表单。
 */
export function useLegalConsentPersistence(
  watch: UseFormWatch<any>,
  setValue: UseFormSetValue<any>
): void {
  useEffect(() => {
    if (getStoredLegalConsent()) {
      setValue('agreeTerms', true);
    }
    const subscription = watch((values, { name }) => {
      if (name === 'agreeTerms') {
        setStoredLegalConsent(Boolean(values.agreeTerms));
      }
    });
    return () => subscription.unsubscribe();
  }, [watch, setValue]);
}
