'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import PaperVeilLayers from '@/components/explore/PaperVeilLayers';
import { PHASES, getLastActivationCode, loadSession } from '@/lib/explore/session';
import { useLocale } from '@/hooks/useLocale';

function TransitionContent() {
  const { t } = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromParam = searchParams.get('from');
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  // 与 关于我们/社区 同款纸层背景：置 data-mesh-page 统一布局底色
  useEffect(() => {
    document.documentElement.setAttribute('data-mesh-page', 'true');
    return () => document.documentElement.removeAttribute('data-mesh-page');
  }, []);

  const code = mounted ? getLastActivationCode() : '';
  const session = code ? loadSession(code) : null;
  const from = (fromParam && PHASES.some((p) => p.key === fromParam)) ? fromParam : 'values';

  const currentIdx = PHASES.findIndex((p) => p.key === from);
  const nextPhase = PHASES[currentIdx + 1];
  const completedCount = currentIdx + 1;
  const totalCount = PHASES.length;

  const handleContinue = () => {
    if (nextPhase) {
      router.push(`/explore/chat/${nextPhase.key}`);
    } else {
      router.push('/explore/report');
    }
  };

  if (!mounted || !session) return null;

  const fromLabel = t(`explore.chat.phaseLabels.${from}`);
  const nextLabel = nextPhase
    ? t(`explore.chat.phaseLabels.${nextPhase.key}`)
    : t('explore.transition.viewReport');
  const ruminationFilterDone = from === 'rumination';

  return (
    <div className="bd-mesh-page min-h-screen text-bd-fg flex flex-col items-center justify-center px-6 py-16">
      {/* 半透明纸层 + 毛玻璃背景（与 关于我们/社区/引导页 同款） */}
      <PaperVeilLayers />

      <div className="relative z-[2] w-full max-w-[460px] flex flex-col items-center">
        <motion.button
          type="button"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          onClick={() => router.push(`/explore/chat/${from}`)}
          className="text-sm text-bd-subtle hover:text-bd-fg transition-colors self-start mb-6"
        >
          ← {t('explore.transition.back')}
        </motion.button>

        <motion.div
          className="bd-glass-card w-full rounded-2xl p-8 md:p-10"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.25, 0.8, 0.35, 1] }}
        >
          {/* 头部：完成图标 + 徽标 + 标题（居中排版，与关于我们页同款） */}
          <div className="flex flex-col items-center text-center mb-8">
            <div className="w-14 h-14 rounded-full flex items-center justify-center bg-bd-success-dim text-bd-success mb-4">
              <CheckCircle2 size={26} />
            </div>
            <p className="text-xs tracking-widest uppercase text-bd-primary font-medium mb-2">
              {t('explore.transition.badge')}
            </p>
            <h1 className="text-xl md:text-2xl font-semibold text-bd-fg">
              {ruminationFilterDone
                ? t('explore.transition.titleRuminationDone')
                : t('explore.transition.titlePhaseDone', { dim: fromLabel })}
            </h1>
          </div>

          <p className="text-bd-muted leading-loose text-sm md:text-base text-center mb-8">
            {ruminationFilterDone
              ? t('explore.transition.blurbRuminationDone')
              : t('explore.transition.blurbGeneric')}
          </p>

          {/* 探索进度 */}
          <div className="space-y-3 mb-8">
            <p className="text-xs font-medium text-bd-subtle tracking-wider uppercase">
              {t('explore.transition.progressLabel')}
            </p>
            <div className="flex gap-2">
              {PHASES.map((p, i) => {
                const done = i <= currentIdx;
                return (
                  <div
                    key={p.key}
                    className={`flex-1 h-1.5 rounded-full transition-colors ${
                      done ? 'bg-bd-success' : 'bg-bd-subtle opacity-25'
                    }`}
                  />
                );
              })}
            </div>
            <p className="text-sm text-bd-muted">
              {t('explore.transition.progressCount', {
                done: String(completedCount),
                total: String(totalCount),
              })}
            </p>
          </div>

          {/* 灵魂句：沿用引导页呼吸竖条样式 */}
          <div className="bd-intro-soul-wrap">
            <div className="bd-intro-soul-bar" aria-hidden />
            <p className="bd-intro-soul">
              {ruminationFilterDone
                ? t('explore.transition.soulRuminationDone')
                : nextPhase
                  ? t('explore.transition.soulNext', { next: nextLabel })
                  : t('explore.transition.soulReport')}
            </p>
          </div>

          <div className="bd-intro-cta-row">
            <button
              type="button"
              onClick={handleContinue}
              className="bd-intro-btn-begin"
            >
              {nextPhase
                ? t('explore.transition.continueNext', { next: nextLabel })
                : ruminationFilterDone
                  ? t('explore.transition.viewGrowthReport')
                  : t('explore.transition.viewReport')}
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
        </motion.div>
      </div>
    </div>
  );
}

export default function ExploreTransitionPage() {
  return (
    <Suspense fallback={
      <div className="bd-mesh-page min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-bd-primary border-t-transparent" />
      </div>
    }>
      <TransitionContent />
    </Suspense>
  );
}
