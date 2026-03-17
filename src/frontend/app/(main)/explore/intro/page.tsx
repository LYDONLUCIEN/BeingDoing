'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { useLocale } from '@/hooks/useLocale';
import { getByPath } from '@/lib/i18n';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';

const STEPS = [
  { key: 'step1', cls: 'blue' as const },
  { key: 'step2', cls: 'green' as const },
  { key: 'step3', cls: 'red' as const },
  { key: 'step4', cls: 'yellow' as const },
];

/** 模拟 guide8 的 token 显示：elapsed 秒后各 token 依次出现，或点击加速全部显示 */
function useIntroReveal(accelerated: boolean) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (accelerated) return;
    const start = Date.now();
    const id = setInterval(() => {
      setElapsed((Date.now() - start) / 1000);
    }, 80);
    return () => clearInterval(id);
  }, [accelerated]);
  return (delay: number) => accelerated || elapsed >= delay;
}

export default function ExploreIntroPage() {
  const router = useRouter();
  const { t, locale, dict } = useLocale();
  const isZh = locale === 'zh';
  const [accelerated, setAccelerated] = useState(false);
  const isRevealed = useIntroReveal(accelerated);
  const { isAuthenticated } = useAuthStore();
  const { openAuthModal } = useAuthModalStore();

  useEffect(() => {
    document.documentElement.setAttribute('data-explore-intro', 'true');
    return () => document.documentElement.removeAttribute('data-explore-intro');
  }, []);

  const handleAccelerate = useCallback(() => {
    if (accelerated) return;
    setAccelerated(true);
  }, [accelerated]);

  const canNavigate = isRevealed(6); /* 最后一块（开启探索）已展示即可进入 */
  const handleBegin = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!canNavigate) {
        setAccelerated(true);
      } else if (!isAuthenticated) {
        openAuthModal('/explore/activate');
      } else {
        router.push('/explore/activate');
      }
    },
    [canNavigate, isAuthenticated, openAuthModal, router]
  );

  return (
    <div
      className="explore-intro-wrap min-h-screen flex flex-col items-center justify-center px-6 py-16 cursor-default"
      onClick={handleAccelerate}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' || e.key === ' ' ? handleAccelerate() : null}
      aria-label={t('explore.intro.clickHint')}
    >
      {/* 首页 mesh 背景（略增不透明度） */}
      <div className="landing-mesh-bg fixed inset-0 z-0" aria-hidden>
        <div className="landing-mesh-blob landing-mesh-blob-1" />
        <div className="landing-mesh-blob landing-mesh-blob-2" />
        <div className="landing-mesh-blob landing-mesh-blob-3" />
        <div className="landing-mesh-blob landing-mesh-blob-4" />
      </div>
      <div className="landing-mesh-noise fixed inset-0 z-[1]" aria-hidden />
      <div className="relative z-[2] w-full max-w-[460px] flex flex-col items-center">
        {/* 返回 */}
        <motion.button
          type="button"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          onClick={(e) => { e.stopPropagation(); router.push('/'); }}
          className="text-sm text-bd-subtle hover:text-bd-fg transition-colors self-start mb-6"
        >
          ← {t('explore.intro.back')}
        </motion.button>

        {/* 毛玻璃卡片（guide8 内容完全复用） */}
        <motion.div
          className="bd-intro-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.15, ease: [0.25, 0.8, 0.35, 1] }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* ① 请寻找安静空间 ② 导师指引 */}
          <div className="mb-6">
            <IntroToken revealed={isRevealed(0.4)} accelerated={accelerated}>
              <p className="bd-intro-premise">{t('explore.intro.premise1')}</p>
            </IntroToken>
            <IntroToken revealed={isRevealed(1.0)} accelerated={accelerated}>
              <p className="bd-intro-premise">
                {t('explore.intro.premise2Before')}
                <span className="mark">{t('explore.intro.premise2Mentor')}</span>
                {t('explore.intro.premise2After')}
              </p>
            </IntroToken>
          </div>

          {/* ③ 你将完成的探索 + 4 步骤 */}
          <IntroToken revealed={isRevealed(1.6)} accelerated={accelerated}>
            <div className="bd-intro-rule" />
          </IntroToken>
          <IntroToken revealed={isRevealed(1.9)} accelerated={accelerated}>
            <p className="bd-intro-block-label">{t('explore.intro.blockLabel')}</p>
          </IntroToken>
          <div className="bd-intro-steps">
            {STEPS.map((s, i) => {
              const stepData = getByPath(dict, `explore.intro.${s.key}`) as { cn?: string; en?: string } | undefined;
              const cn = stepData?.cn ?? '';
              const en = stepData?.en ?? '';
              return (
                <IntroToken key={s.key} revealed={isRevealed(2.2 + i * 0.4)} accelerated={accelerated}>
                  <div className={`bd-intro-step ${s.cls}`}>
                    <span className="bd-intro-step-num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="bd-intro-step-cn">{cn}</span>
                    {isZh && en && <span className="bd-intro-step-dot" />}
                    {isZh && en && <span className="bd-intro-step-en">{en}</span>}
                  </div>
                </IntroToken>
              );
            })}
          </div>

          {/* ④ 不必追求完美 + 开启探索 */}
          <IntroToken revealed={isRevealed(4.2)} accelerated={accelerated}>
            <div className="bd-intro-rule" />
          </IntroToken>
          <IntroToken revealed={isRevealed(4.8)} accelerated={accelerated}>
            <div className="bd-intro-soul-wrap">
              <div className="bd-intro-soul-bar" aria-hidden />
              <p className="bd-intro-soul whitespace-pre-line">
                {t('explore.intro.soul')}
              </p>
            </div>
          </IntroToken>

          <IntroToken revealed={isRevealed(5.5)} accelerated={accelerated}>
            <div className="bd-intro-rule-full" />
          </IntroToken>
          <IntroToken revealed={isRevealed(6)} accelerated={accelerated}>
            <div className="bd-intro-cta-row">
              <button
                type="button"
                className="bd-intro-btn-begin"
                onClick={handleBegin}
              >
                {t('explore.intro.cta')}
                <svg className="bd-intro-btn-arrow" width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M1 7h12M8 2l5 5-5 5"
                    stroke="currentColor"
                    strokeWidth="1.1"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </IntroToken>
        </motion.div>
      </div>

      {/* 点击提示 */}
      <AnimatePresence>
        {!accelerated && (
          <motion.div
            className="bd-intro-click-hint"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ delay: 0.8, duration: 0.4 }}
          >
            <div className="bd-intro-hint-pulse" />
            {t('explore.intro.clickHint')}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function IntroToken({
  children,
  revealed,
  accelerated,
}: {
  children: React.ReactNode;
  revealed: boolean;
  accelerated: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={revealed ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
      transition={{
        duration: accelerated ? 0.25 : 0.6,
        ease: [0.25, 0.8, 0.35, 1],
      }}
    >
      {children}
    </motion.div>
  );
}
