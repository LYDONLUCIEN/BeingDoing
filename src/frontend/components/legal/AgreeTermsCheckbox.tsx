'use client';

import type { InputHTMLAttributes } from 'react';
import LegalDocLink from './LegalDocLink';

export type AgreeTermsCheckboxProps = {
  /** form.register('agreeTerms') 的返回值展开传入 */
  inputProps: InputHTMLAttributes<HTMLInputElement>;
  /** 校验错误信息（未勾选提交时展示） */
  error?: string;
  /** 文案颜色等样式覆盖（默认适配 bd 主题） */
  labelClassName?: string;
  errorClassName?: string;
};

/**
 * 「我已阅读并同意《隐私政策》和《服务条款》」勾选项。
 * 登录、注册等表单共用，配合 useLegalConsentPersistence 实现勾选记忆。
 */
export default function AgreeTermsCheckbox({
  inputProps,
  error,
  labelClassName = 'flex items-start gap-2 text-sm text-bd-muted cursor-pointer',
  errorClassName = 'mt-1 text-xs text-bd-err',
}: AgreeTermsCheckboxProps) {
  return (
    <div>
      <label className={labelClassName}>
        <input
          type="checkbox"
          {...inputProps}
          className="mt-0.5 h-4 w-4 rounded border-bd-border text-primary-600 focus:ring-primary-500"
        />
        <span>
          我已阅读并同意
          <LegalDocLink
            type="privacy"
            className="text-primary-600 hover:text-primary-700 hover:underline mx-1 align-baseline"
          />
          和
          <LegalDocLink
            type="terms"
            className="text-primary-600 hover:text-primary-700 hover:underline ml-1 align-baseline"
          />
        </span>
      </label>
      {error && <p className={errorClassName}>{error}</p>}
    </div>
  );
}
