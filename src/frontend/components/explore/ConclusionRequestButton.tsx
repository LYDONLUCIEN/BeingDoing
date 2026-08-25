'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useLocale } from '@/hooks/useLocale';

export type ConclusionRequestState = 'idle' | 'loading' | 'error';

interface Props {
  /** 按钮状态：idle 可点击 / loading 生成中 / error 失败可重试 */
  state: ConclusionRequestState;
  /** 是否闲置（非流式、输入框为空、无引导任务），用于触发提醒抖动 */
  idle: boolean;
  onClick: () => void;
}

/**
 * 「对话结束无法进行下一步？点击这里」手动出卡按钮。
 *
 * - 首次出现：冒泡长出（spring: opacity + y + scale）；
 * - 闲置提醒：出现 10s 后抖动一次，继续闲置满 60s 再抖一次，每阶段封顶 2 次，
 *   之后永久安静（提醒是告知"多了个东西"，不是催促）；
 * - 失败不静默：error 态红色文案「生成失败，点击重试」。
 */
export default function ConclusionRequestButton({ state, idle, onClick }: Props) {
  const { t } = useLocale();
  const [shaking, setShaking] = useState(false);
  const [shakesUsed, setShakesUsed] = useState(0);

  // 闲置抖动提醒：最多 2 次（10s / 再过 60s），页面不在前台不抖
  useEffect(() => {
    if (!idle || state === 'loading' || shakesUsed >= 2) return;
    const delay = shakesUsed === 0 ? 10_000 : 60_000;
    const timer = setTimeout(() => {
      if (document.visibilityState !== 'visible') return;
      setShakesUsed((n) => n + 1);
      setShaking(true);
      setTimeout(() => setShaking(false), 600);
    }, delay);
    return () => clearTimeout(timer);
  }, [idle, state, shakesUsed]);

  const label =
    state === 'loading'
      ? t('explore.chat.conclusionRequestLoading')
      : state === 'error'
        ? t('explore.chat.conclusionRequestError')
        : t('explore.chat.conclusionRequestButton');

  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      className="mb-1.5 w-full shrink-0"
    >
      <motion.button
        type="button"
        onClick={onClick}
        disabled={state === 'loading'}
        animate={shaking ? { x: [0, -4, 4, -3, 3, 0] } : { x: 0 }}
        transition={{ duration: 0.45 }}
        className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-wait ${
          state === 'error'
            ? 'border-red-300 bg-red-50 text-red-700 hover:bg-red-100'
            : 'border-amber-300/80 bg-amber-50 text-amber-900 hover:bg-amber-100'
        }`}
      >
        {state === 'loading' && (
          <span className="mr-1.5 inline-block h-3 w-3 animate-spin rounded-full border border-amber-400 border-t-transparent align-[-2px]" />
        )}
        {label}
      </motion.button>
    </motion.div>
  );
}
