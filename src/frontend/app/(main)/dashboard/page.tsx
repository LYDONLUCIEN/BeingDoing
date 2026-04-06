'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, Lock, ChevronRight } from 'lucide-react';
import { PHASES, loadSession, saveSession, setLastActivationCode, applyExploreResumeToSession, type PhaseKey } from '@/lib/explore/session';
import { useLocale } from '@/hooks/useLocale';
import { apiClient } from '@/lib/api/client';

const PHASE_COLORS = [
  'var(--bd-phase-values)',
  'var(--bd-phase-strengths)',
  'var(--bd-phase-interests)',
  'var(--bd-phase-purpose)',
  'var(--bd-phase-rumination, #8B5CF6)',
];

interface JourneyItem {
  activation_code: string;
  mode: string;
  status: string;
  created_at: string;
  last_activity_at: string;
  explore_resume?: { resume_phase?: string; unlocked_phases?: string[] };
  is_latest?: boolean;
}

function buildNodes(resume?: JourneyItem['explore_resume']) {
  const unlocked = (resume?.unlocked_phases ?? []) as PhaseKey[];
  const current = (resume?.resume_phase ?? 'values') as PhaseKey;
  return PHASES.map((p, idx) => ({
    id: p.key,
    label: p.label,
    status: unlocked.includes(p.key)
      ? p.key === current ? ('in-progress' as const) : ('completed' as const)
      : ('incomplete' as const),
    color: PHASE_COLORS[idx] ?? PHASE_COLORS[0],
  }));
}

function JourneyCard({
  journey,
  featured,
  onNavigate,
  t,
}: {
  journey: JourneyItem;
  featured?: boolean;
  onNavigate: (code: string, phase: string) => void;
  t: (k: string) => string;
}) {
  const nodes = buildNodes(journey.explore_resume);
  const resumePhase = journey.explore_resume?.resume_phase ?? 'values';

  return (
    <div className={`bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm ${featured ? 'p-8' : 'p-5'}`}>
      <div className="flex items-center justify-between mb-4">
        <h2 className={`font-medium text-bd-fg ${featured ? 'text-xl' : 'text-base'}`}>
          {featured ? t('dashboard.journeyTitle') : `旅程 ${journey.activation_code.slice(-6)}`}
        </h2>
        <span className="text-xs text-bd-muted">
          {journey.status === 'active' ? '进行中' : journey.status === 'expired' ? '已过期' : journey.status}
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        {nodes.map((node, index) => (
          <div key={node.id} className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => node.status !== 'incomplete' && onNavigate(journey.activation_code, node.id)}
              disabled={node.status === 'incomplete'}
              className={`relative ${featured ? 'w-16 h-16' : 'w-12 h-12'} rounded-full flex flex-col items-center justify-center transition-all ${
                node.status !== 'incomplete' ? 'cursor-pointer hover:scale-105' : 'cursor-not-allowed opacity-50'
              }`}
              style={{
                backgroundColor: node.color,
                filter: node.status === 'incomplete' ? 'grayscale(100%)' : 'none',
              }}
            >
              {node.status !== 'incomplete' && (
                <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full flex items-center justify-center border-2 border-white bg-green-500">
                  {node.status === 'completed' ? (
                    <Check className="w-2 h-2 text-white" />
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                  )}
                </span>
              )}
              {node.status === 'incomplete' && <Lock className={`${featured ? 'w-5 h-5' : 'w-4 h-4'} text-white/80`} />}
              <span className={`text-white font-medium ${featured ? 'text-xs' : 'text-[10px]'} mt-0.5 px-1 text-center`}>
                {node.label}
              </span>
            </button>
            {index < nodes.length - 1 && <ChevronRight className="w-4 h-4 text-bd-muted flex-shrink-0" />}
          </div>
        ))}
      </div>

      {featured && (
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            onClick={() => onNavigate(journey.activation_code, resumePhase)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            继续探索 →
          </button>
        </div>
      )}
    </div>
  );
}

export default function DashboardCurrentProgressPage() {
  const { t } = useLocale();
  const router = useRouter();
  const [journeys, setJourneys] = useState<JourneyItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiClient.get('/simple-auth/journeys');
        const list = (res.data?.journeys ?? []) as JourneyItem[];
        setJourneys(list);
      } catch {
        // 后端不可用时不显示任何 journey
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleNavigate = (code: string, phase: string) => {
    // 同步 session 到 localStorage 并跳转
    setLastActivationCode(code);
    const journey = journeys.find((j) => j.activation_code === code);
    if (journey?.explore_resume) {
      const session = loadSession(code);
      const updated = applyExploreResumeToSession(session, journey.explore_resume);
      saveSession({ ...updated, activationCode: code });
    }
    router.push(`/explore/chat/${phase}`);
  };

  const featured = journeys[0]; // 最近使用的排第一
  const others = journeys.slice(1);

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-bd-fg mb-8">{t('dashboard.currentProgress')}</h1>

      {loading ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-bd-muted">加载中...</p>
        </div>
      ) : featured ? (
        <div className="space-y-4">
          <JourneyCard journey={featured} featured onNavigate={handleNavigate} t={t} />
          {others.map((j) => (
            <JourneyCard key={j.activation_code} journey={j} onNavigate={handleNavigate} t={t} />
          ))}
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
