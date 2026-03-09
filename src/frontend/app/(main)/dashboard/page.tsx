'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, Lock, ChevronRight } from 'lucide-react';
import { PHASES, getLastActivationCode, loadSession, type PhaseKey } from '@/lib/explore/session';
import { useLocale } from '@/hooks/useLocale';

const PHASE_COLORS = [
  'var(--bd-phase-values)',
  'var(--bd-phase-strengths)',
  'var(--bd-phase-interests)',
  'var(--bd-phase-purpose)',
];

export default function DashboardCurrentProgressPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [session, setSession] = useState<ReturnType<typeof loadSession> | null>(null);

  useEffect(() => {
    const code = getLastActivationCode();
    if (code) setSession(loadSession(code));
  }, []);

  const nodes = PHASES.map((p, idx) => ({
    id: p.key,
    label: p.label,
    status: session
      ? session.unlockedPhases.includes(p.key)
        ? p.key === session.currentPhase
          ? ('in-progress' as const)
          : ('completed' as const)
        : ('incomplete' as const)
      : ('incomplete' as const),
    color: PHASE_COLORS[idx],
  }));

  const handleNodeClick = (key: string) => {
    const unlocked = session?.unlockedPhases.includes(key as PhaseKey);
    if (unlocked) router.push(`/explore/chat/${key}`);
  };

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-bd-fg mb-8">{t('dashboard.currentProgress')}</h1>

      {session ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 shadow-sm">
          <h2 className="text-xl font-medium text-bd-fg mb-6">{t('dashboard.journeyTitle')}</h2>

          <div className="flex flex-wrap items-center justify-between gap-4">
            {nodes.map((node, index) => (
              <div key={node.id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleNodeClick(node.id)}
                  disabled={node.status === 'incomplete'}
                  className={`relative w-16 h-16 rounded-full flex flex-col items-center justify-center transition-all ${
                    node.status !== 'incomplete'
                      ? 'cursor-pointer hover:scale-105'
                      : 'cursor-not-allowed opacity-50'
                  }`}
                  style={{
                    backgroundColor: node.color,
                    filter: node.status === 'incomplete' ? 'grayscale(100%)' : 'none',
                  }}
                >
                  {node.status !== 'incomplete' && (
                    <span className="absolute -top-0.5 -right-0.5 w-5 h-5 rounded-full flex items-center justify-center border-2 border-white bg-green-500">
                      {node.status === 'completed' ? (
                        <Check className="w-2.5 h-2.5 text-white" />
                      ) : (
                        <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                      )}
                    </span>
                  )}
                  {node.status === 'incomplete' && (
                    <Lock className="w-5 h-5 text-white/80" />
                  )}
                  <span className="text-white font-medium text-xs mt-0.5 px-1 text-center">
                    {node.label}
                  </span>
                </button>
                {index < nodes.length - 1 && (
                  <ChevronRight className="w-5 h-5 text-bd-muted flex-shrink-0" />
                )}
              </div>
            ))}
          </div>

          <div className="mt-8 flex gap-4">
            <Link
              href="/explore/intro"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
            >
              {t('common.startExploreArrow')}
            </Link>
            {session.unlockedPhases.includes('purpose') && (
              <Link
                href="/explore/report/view"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-bd-border text-bd-fg hover:bg-bd-overlay-md"
              >
                {t('common.viewReport')}
              </Link>
            )}
          </div>
        </div>
      ) : (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-bd-muted mb-6">尚未开始探索，或未激活当前会话</p>
          <Link
            href="/explore/intro"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            {t('common.startExplore')}
          </Link>
        </div>
      )}
    </div>
  );
}
