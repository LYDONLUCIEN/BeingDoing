'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, Lock, ChevronRight, BookOpen } from 'lucide-react';
import { PHASES, loadSession, saveSession, setLastActivationCode, applyExploreResumeToSession, type PhaseKey } from '@/lib/explore/session';
import { useLocale } from '@/hooks/useLocale';
import { apiClient } from '@/lib/api/client';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';

const PHASE_COLORS = [
  'var(--bd-phase-values)',
  'var(--bd-phase-strengths)',
  'var(--bd-phase-interests)',
  'var(--bd-phase-purpose)',
  'var(--bd-phase-rumination, #8B5CF6)',
];

/** 报告节点：琥珀旧纸色（与五阶段色块区分），渐变与内阴影在按钮 class 中实现 */
const REPORT_NODE_COLOR = '#d97706';

interface JourneyItem {
  activation_code: string;
  mode: string;
  status: string;
  created_at: string;
  last_activity_at: string;
  explore_resume?: {
    resume_phase?: string;
    unlocked_phases?: string[];
    report_unlocked?: boolean;
  };
  is_latest?: boolean;
}

/**
 * 与后端 compute_explore_resume / applyExploreResumeToSession 对齐：无 report 或仅有空对象时，
 * 不能当成「五维全未解锁」，否则五个节点全灰锁，用户会以为「没有节点」。
 */
function effectiveResumeForNodes(resume?: JourneyItem['explore_resume']) {
  if (!resume?.resume_phase) {
    return { resume_phase: 'values' as PhaseKey, unlocked_phases: ['values'] as PhaseKey[] };
  }
  const rp = resume.resume_phase as PhaseKey;
  if (!PHASES.some((p) => p.key === rp)) {
    return { resume_phase: 'values' as PhaseKey, unlocked_phases: ['values'] as PhaseKey[] };
  }
  let unlocked = (resume.unlocked_phases ?? []) as PhaseKey[];
  if (unlocked.length === 0) {
    const idx = PHASES.findIndex((p) => p.key === rp);
    unlocked = PHASES.slice(0, idx + 1).map((p) => p.key);
  }
  return { resume_phase: rp, unlocked_phases: unlocked };
}

type NodeVisual = {
  id: string;
  label: string;
  status: 'in-progress' | 'completed' | 'incomplete';
  color: string;
};

function buildNodes(resume?: JourneyItem['explore_resume']): NodeVisual[] {
  const eff = effectiveResumeForNodes(resume);
  const unlocked = eff.unlocked_phases;
  const current = eff.resume_phase;
  const reportUnlocked = Boolean(resume?.report_unlocked);

  const phaseNodes: NodeVisual[] = PHASES.map((p, idx) => ({
    id: p.key,
    label: p.label,
    status: unlocked.includes(p.key)
      ? p.key === current
        ? ('in-progress' as const)
        : ('completed' as const)
      : ('incomplete' as const),
    color: PHASE_COLORS[idx] ?? PHASE_COLORS[0],
  }));

  const reportStatus: NodeVisual['status'] = reportUnlocked ? 'completed' : 'incomplete';

  return [
    ...phaseNodes,
    {
      id: 'report',
      label: '报告',
      status: reportStatus,
      color: REPORT_NODE_COLOR,
    },
  ];
}

function formatJourneyDateTime(iso?: string): string {
  if (!iso?.trim()) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('zh-CN', { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

/** 右上角状态：探索已全部收口时显示「已完成」，避免仅因激活 TTL 显示「已过期」造成误解 */
function journeyStatusLabel(journey: JourneyItem): string {
  if (journey.explore_resume?.report_unlocked) return '已完成';
  if (journey.status === 'active') return '进行中';
  if (journey.status === 'expired') return '已过期';
  return journey.status;
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
  const resumePhase = effectiveResumeForNodes(journey.explore_resume).resume_phase;
  const nodePx = featured ? 64 : 48;
  const half = nodePx / 2;

  return (
    <div className={`bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm ${featured ? 'p-8' : 'p-5'}`}>
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <h2 className={`font-medium text-bd-fg ${featured ? 'text-xl' : 'text-base'}`}>
          {featured ? t('dashboard.journeyTitle') : `旅程 ${journey.activation_code.slice(-6)}`}
        </h2>
        <span className="shrink-0 rounded-full border border-bd-border bg-bd-surface-2 px-2.5 py-0.5 text-xs text-bd-muted">
          {journeyStatusLabel(journey)}
        </span>
      </div>

      <div className="mb-4 space-y-0.5 text-xs text-bd-muted">
        <p>开始时间：{formatJourneyDateTime(journey.created_at)}</p>
        <p>最后编辑：{formatJourneyDateTime(journey.last_activity_at)}</p>
      </div>

      <div className="overflow-x-auto [-webkit-overflow-scrolling:touch] pb-1">
        <div
          className="relative flex min-w-min items-start gap-0"
          style={{
            paddingLeft: half,
            paddingRight: half,
          }}
        >
          <div
            className="pointer-events-none absolute z-0 bg-bd-border-strong"
            style={{
              left: half,
              right: half,
              top: half,
              height: 1,
              transform: 'translateY(-0.5px)',
            }}
            aria-hidden
          />
          {nodes.map((node, index) => (
            <div key={node.id} className="relative z-[1] flex shrink-0 items-start">
              <div className="flex flex-col items-center" style={{ width: nodePx }}>
                {node.id === 'report' ? (
                  <button
                    type="button"
                    onClick={() =>
                      node.status !== 'incomplete' && onNavigate(journey.activation_code, node.id)
                    }
                    disabled={node.status === 'incomplete'}
                    aria-label="报告"
                    className={`relative flex shrink-0 flex-col items-center justify-center border border-amber-900/20 bg-gradient-to-br from-[#fffdf7] via-[#fef3c7] to-[#fbbf24] text-amber-950 shadow-[inset_5px_0_14px_rgba(146,64,14,0.14),inset_0_1px_0_rgba(255,255,255,0.88)] transition-all dark:border-amber-700/35 dark:from-amber-950/90 dark:via-amber-900/85 dark:to-amber-800/70 dark:text-amber-100 dark:shadow-[inset_5px_0_14px_rgba(0,0,0,0.35),inset_0_1px_0_rgba(255,255,255,0.06)] ${
                      featured
                        ? 'h-16 w-[2.7rem] rounded-l-md rounded-r-lg'
                        : 'h-12 w-[2.05rem] rounded-l rounded-r-md'
                    } ${
                      node.status !== 'incomplete'
                        ? 'cursor-pointer hover:scale-105 hover:border-amber-800/35 hover:shadow-[inset_5px_0_14px_rgba(146,64,14,0.12),0_6px_14px_-4px_rgba(180,83,9,0.35)]'
                        : 'cursor-not-allowed opacity-[0.58]'
                    }`}
                    style={{
                      filter: node.status === 'incomplete' ? 'grayscale(0.35) brightness(0.97)' : undefined,
                    }}
                  >
                    {node.status !== 'incomplete' && (
                      <span className="absolute -right-0.5 -top-0.5 z-[2] flex h-4 w-4 items-center justify-center rounded-full border-2 border-amber-50 bg-green-600 shadow-sm dark:border-amber-900">
                        {node.status === 'completed' ? (
                          <Check className="h-2 w-2 text-white" strokeWidth={3} />
                        ) : (
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
                        )}
                      </span>
                    )}
                    {node.status === 'incomplete' ? (
                      <Lock
                        className={`${featured ? 'h-5 w-5' : 'h-4 w-4'} text-amber-900/45 dark:text-amber-200/50`}
                        aria-hidden
                      />
                    ) : (
                      <BookOpen
                        className={featured ? 'h-7 w-7' : 'h-5 w-5'}
                        strokeWidth={featured ? 1.65 : 1.5}
                        aria-hidden
                      />
                    )}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      node.status !== 'incomplete' && onNavigate(journey.activation_code, node.id)
                    }
                    disabled={node.status === 'incomplete'}
                    className={`relative flex shrink-0 items-center justify-center rounded-full text-white transition-all ${
                      featured ? 'h-16 w-16' : 'h-12 w-12'
                    } ${
                      node.status !== 'incomplete'
                        ? 'cursor-pointer hover:scale-105 hover:ring-2 hover:ring-bd-border-strong hover:ring-offset-2 hover:ring-offset-bd-card'
                        : 'cursor-not-allowed opacity-55'
                    }`}
                    style={{
                      backgroundColor: node.color,
                      filter: node.status === 'incomplete' ? 'grayscale(1) brightness(0.92)' : 'none',
                    }}
                  >
                    {node.status !== 'incomplete' && (
                      <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-white bg-green-500">
                        {node.status === 'completed' ? (
                          <Check className="h-2 w-2 text-white" />
                        ) : (
                          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
                        )}
                      </span>
                    )}
                    {node.status === 'incomplete' && (
                      <Lock
                        className={`${featured ? 'h-5 w-5' : 'h-4 w-4'} text-white/85`}
                        aria-hidden
                      />
                    )}
                  </button>
                )}
                <span
                  className={`mt-1.5 max-w-[4.5rem] text-center font-medium leading-tight text-bd-fg ${
                    featured ? 'text-xs' : 'text-[10px]'
                  }`}
                >
                  {node.label}
                </span>
              </div>
              {index < nodes.length - 1 && (
                <div
                  className="flex shrink-0 items-center justify-center text-bd-muted"
                  style={{ width: featured ? 28 : 22, height: nodePx }}
                  aria-hidden
                >
                  <ChevronRight className={featured ? 'h-5 w-5' : 'h-4 w-4'} strokeWidth={2} />
                </div>
              )}
            </div>
          ))}
        </div>
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
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchJourneys = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await apiClient.get('/simple-auth/journeys');
      const list = (res.data?.journeys ?? []) as JourneyItem[];
      setJourneys(list);
      setFetchError(null);
    } catch {
      // 仅非静默请求提示错误；静默失败保留当前列表，不打断用户
      if (!silent) {
        setFetchError('无法加载旅程数据，请检查网络或稍后重试');
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchJourneys(false);
  }, [fetchJourneys]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') void fetchJourneys(true);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchJourneys]);

  const handleNavigate = async (code: string, phase: string) => {
    setLastActivationCode(code);
    let resume = journeys.find((j) => j.activation_code === code)?.explore_resume;
    try {
      const fresh = await fetchExploreResumeFromJourneys(code);
      if (fresh?.resume_phase) resume = fresh;
    } catch {
      /* 使用列表中的缓存 resume */
    }
    if (resume?.resume_phase) {
      const session = loadSession(code);
      const updated = applyExploreResumeToSession(session, resume);
      saveSession({ ...updated, activationCode: code });
    }
    if (phase === 'report') {
      router.push('/explore/report');
      return;
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
      ) : fetchError ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-red-600/90 dark:text-red-400/90 mb-4">{fetchError}</p>
          <button
            type="button"
            onClick={() => {
              setFetchError(null);
              void fetchJourneys(false);
            }}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            重试
          </button>
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
