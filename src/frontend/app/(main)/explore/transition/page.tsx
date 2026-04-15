'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { CheckCircle2 } from 'lucide-react';
import { PHASES, getLastActivationCode, loadSession } from '@/lib/explore/session';
import { useLocale } from '@/hooks/useLocale';

function TransitionContent() {
  const { t } = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromParam = searchParams.get('from');
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    document.documentElement.setAttribute('data-explore-intro', 'true');
    return () => document.documentElement.removeAttribute('data-explore-intro');
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
    <div
      className="explore-intro-wrap min-h-screen flex flex-col items-center justify-center px-6 py-16"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="landing-mesh-bg fixed inset-0 z-0" aria-hidden>
        <div className="landing-mesh-blob landing-mesh-blob-1" />
        <div className="landing-mesh-blob landing-mesh-blob-2" />
        <div className="landing-mesh-blob landing-mesh-blob-3" />
        <div className="landing-mesh-blob landing-mesh-blob-4" />
      </div>
      <div className="landing-mesh-noise fixed inset-0 z-[1]" aria-hidden />

      <div className="relative z-[2] w-full max-w-[460px] flex flex-col items-center">
        <motion.button
          type="button"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          onClick={() => router.push(`/explore/chat/${from}`)}
          className="text-sm text-bd-subtle hover:text-bd-fg transition-colors self-start mb-6"
        >
          ← 返回
        </motion.button>

        <motion.div
          className="bd-intro-card"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.25, 0.8, 0.35, 1] }}
        >
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-full flex items-center justify-center bg-emerald-100 text-emerald-600">
              <CheckCircle2 size={24} />
            </div>
            <div>
              <p className="text-xs tracking-widest uppercase text-bd-primary font-medium">
                {t('explore.transition.badge')}
              </p>
              <h1 className="text-xl font-semibold text-bd-fg">
                {ruminationFilterDone
                  ? t('explore.transition.titleRuminationDone')
                  : t('explore.transition.titlePhaseDone', { dim: fromLabel })}
              </h1>
            </div>
          </div>

          <div className="bd-intro-rule-full mb-6" />

          <p className="bd-intro-premise mb-6">
            {ruminationFilterDone
              ? t('explore.transition.blurbRuminationDone')
              : t('explore.transition.blurbGeneric')}
          </p>

          <div className="space-y-4 mb-8">
            <p className="text-xs font-medium text-bd-fg-subtle tracking-wider uppercase">
              {t('explore.transition.progressLabel')}
            </p>
            <div className="flex gap-2">
              {PHASES.map((p, i) => {
                const done = i <= currentIdx;
                return (
                  <div
                    key={p.key}
                    className={`flex-1 h-1.5 rounded-full transition-colors ${
                      done ? 'bg-emerald-400' : 'bg-neutral-200'
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

          <p className="bd-intro-soul mb-8">
            {ruminationFilterDone
              ? t('explore.transition.soulRuminationDone')
              : nextPhase
                ? t('explore.transition.soulNext', { next: nextLabel })
                : t('explore.transition.soulReport')}
          </p>

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
      <div className="min-h-screen flex items-center justify-center bg-bd-bg">
        <div className="animate-spin rounded-full h-10 w-10 border-2 border-bd-primary border-t-transparent" />
      </div>
    }>
      <TransitionContent />
    </Suspense>
  );
}
