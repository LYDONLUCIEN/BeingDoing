'use client';

import { useState, type CSSProperties, type ReactNode } from 'react';
import { useLocale } from '@/hooks/useLocale';
import LegalDocModal from './LegalDocModal';

export type LegalDocLinkProps = {
  /** 'privacy' | 'terms' */
  type: 'privacy' | 'terms';
  /** 触发器文案，默认取 i18n footer.privacyPolicy / footer.termsOfService */
  label?: ReactNode;
  /** 透传到触发 button，便于调用方控制样式 */
  className?: string;
  style?: CSSProperties;
};

/**
 * 带触发器的法律协议链接：点击后弹出 LegalDocModal。
 * 调用方只管 className/style，组件内部维护 open 状态。
 * 两处调用点（注册页 / 主页页脚）共享同一份 i18n 文案。
 */
export default function LegalDocLink({ type, label, className, style }: LegalDocLinkProps) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);

  const title = type === 'privacy' ? t('footer.privacyPolicy') : t('footer.termsOfService');
  const body = type === 'privacy' ? t('footer.privacyBody') : t('footer.termsBody');

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={className}
        style={style}
      >
        {label ?? title}
      </button>
      <LegalDocModal
        open={open}
        title={title}
        body={body}
        onClose={() => setOpen(false)}
      />
    </>
  );
}
