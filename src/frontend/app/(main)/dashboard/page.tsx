'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, Lock, ChevronRight, BookOpen, User } from 'lucide-react';
import { PHASES, loadSession, saveSession, setLastActivationCode, applyExploreResumeToSession, type PhaseKey } from '@/lib/explore/session';
import { clearThreadCache } from '@/lib/explore/threads';
import { useLocale } from '@/hooks/useLocale';
import { apiClient } from '@/lib/api/client';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';
import { useAuthStore } from '@/stores/authStore';
import type { SurveyData } from '@/lib/survey/schema';

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

/** 后端 /simple-auth/journeys 返回的用户级问卷摘要 */
interface UserSurveyInfo {
  completed: boolean;
  survey_data: SurveyData;
}

/** Journeys 响应完整结构 */
interface JourneysResponse {
  journeys: JourneyItem[];
  user_survey?: UserSurveyInfo;
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

/** 问卷字段中文标签映射 */
const SURVEY_DISPLAY_LABELS: Record<string, string> = {
  nickname: '昵称',
  gender: '性别',
  age: '年龄',
  education_school: '院校',
  education_degree: '学历',
  education_major: '专业',
  city: '城市',
  career_status: '职业状态',
  industry: '行业',
  position: '岗位',
  work_years_total: '工作年限',
  salary_level: '薪资水平',
};

/**
 * 从问卷数据中提取关键展示字段（最多显示 6 个非空项）。
 * 优先级：昵称 > 职业状态 > 行业 > 学历 > 城市 > 岗位。
 */
function extractSurveyDisplayItems(data: SurveyData): { label: string; value: string }[] {
  const priorityKeys = ['nickname', 'career_status', 'industry', 'education_degree', 'city', 'position'];
  const items: { label: string; value: string }[] = [];

  for (const key of priorityKeys) {
    const val = data[key as keyof SurveyData];
    if (!val || (Array.isArray(val) && val.length === 0)) continue;
    const displayVal = Array.isArray(val) ? val.join('、') : String(val);
    if (!displayVal.trim()) continue;
    items.push({ label: SURVEY_DISPLAY_LABELS[key] || key, value: displayVal });
    if (items.length >= 6) break;
  }
  return items;
}

/** 用户档案卡片：展示问卷基本信息 */
function UserSurveyCard({
  survey,
  t,
}: {
  survey: UserSurveyInfo;
  t: (k: string) => string;
}) {
  const items = extractSurveyDisplayItems(survey.survey_data);
  if (items.length === 0) return null;

  return (
    <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-6">
      <div className="flex items-center gap-2 mb-4">
        <User className="h-5 w-5 text-bd-muted" />
        <h2 className="font-medium text-bd-fg text-base">{t('dashboard.profileInfo') || '个人信息'}</h2>
        {survey.completed && (
          <span className="ml-auto rounded-full border border-green-200 bg-green-50 px-2 py-0.5 text-[10px] text-green-700 dark:border-green-800 dark:bg-green-900/30 dark:text-green-400">
            已填写
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {items.map((item) => (
          <div key={item.label} className="space-y-0.5">
            <p className="text-[10px] text-bd-muted">{item.label}</p>
            <p className="text-sm font-medium text-bd-fg truncate">{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
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
  const nodePx = featured ? 52 : 40;
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

      {/* pt-3 预留 badge 上溢空间，防止 overflow 裁切 */}
      <div className="overflow-x-auto overflow-y-visible [-webkit-overflow-scrolling:touch] pb-1 pt-3">
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
                    className={`relative flex shrink-0 flex-col items-center justify-center border border-amber-900/20 bg-gradient-to-br from-[#fffdf7] via-[#fef3c7] to-[#fbbf24] text-amber-950 shadow-[inset_3px_0_10px_rgba(146,64,14,0.14),inset_0_1px_0_rgba(255,255,255,0.88)] transition-[border-color,box-shadow] duration-200 dark:border-amber-700/35 dark:from-amber-950/90 dark:via-amber-900/85 dark:to-amber-800/70 dark:text-amber-100 dark:shadow-[inset_3px_0_10px_rgba(0,0,0,0.35),inset_0_1px_0_rgba(255,255,255,0.06)] ${
                      featured
                        ? 'h-[52px] w-[2.15rem] rounded-l-md rounded-r-lg'
                        : 'h-[40px] w-[1.7rem] rounded-l rounded-r-md'
                    } ${
                      node.status !== 'incomplete'
                        ? 'cursor-pointer hover:border-amber-700/50 hover:shadow-[inset_3px_0_10px_rgba(146,64,14,0.12),0_4px_12px_-2px_rgba(180,83,9,0.3)]'
                        : 'cursor-not-allowed opacity-[0.58]'
                    }`}
                    style={{
                      filter: node.status === 'incomplete' ? 'grayscale(0.35) brightness(0.97)' : undefined,
                    }}
                  >
                    {node.status !== 'incomplete' && (
                      <span className="absolute -right-0.5 -top-0.5 z-[2] flex h-3.5 w-3.5 items-center justify-center rounded-full border-2 border-amber-50 bg-green-600 shadow-sm dark:border-amber-900">
                        {node.status === 'completed' ? (
                          <Check className="h-1.5 w-1.5 text-white" strokeWidth={3.5} />
                        ) : (
                          <span className="h-1 w-1 animate-pulse rounded-full bg-white" />
                        )}
                      </span>
                    )}
                    {node.status === 'incomplete' ? (
                      <Lock
                        className={`${featured ? 'h-4 w-4' : 'h-3 w-3'} text-amber-900/45 dark:text-amber-200/50`}
                        aria-hidden
                      />
                    ) : (
                      <BookOpen
                        className={featured ? 'h-5.5 w-5.5' : 'h-4 w-4'}
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
                    className={`relative flex shrink-0 items-center justify-center rounded-full text-white transition-[box-shadow,border-color] duration-200 ${
                      featured ? 'h-[52px] w-[52px]' : 'h-[40px] w-[40px]'
                    } ${
                      node.status !== 'incomplete'
                        ? 'cursor-pointer border-2 border-white/60 hover:border-white hover:shadow-[0_4px_14px_-2px_rgba(0,0,0,0.25)]'
                        : 'cursor-not-allowed opacity-55'
                    }`}
                    style={{
                      backgroundColor: node.color,
                      filter: node.status === 'incomplete' ? 'grayscale(1) brightness(0.92)' : 'none',
                    }}
                  >
                    {node.status !== 'incomplete' && (
                      <span className="absolute -right-0.5 -top-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full border-2 border-white bg-green-500">
                        {node.status === 'completed' ? (
                          <Check className="h-1.5 w-1.5 text-white" strokeWidth={3.5} />
                        ) : (
                          <span className="h-1 w-1 animate-pulse rounded-full bg-white" />
                        )}
                      </span>
                    )}
                    {node.status === 'incomplete' && (
                      <Lock
                        className={`${featured ? 'h-4 w-4' : 'h-3 w-3'} text-white/85`}
                        aria-hidden
                      />
                    )}
                  </button>
                )}
                <span
                  className={`mt-1 max-w-[4rem] text-center font-medium leading-tight text-bd-fg ${
                    featured ? 'text-[11px]' : 'text-[10px]'
                  }`}
                >
                  {node.label}
                </span>
              </div>
              {index < nodes.length - 1 && (
                <div
                  className="flex shrink-0 items-center justify-center text-bd-muted"
                  style={{ width: featured ? 20 : 14, height: nodePx }}
                  aria-hidden
                >
                  <ChevronRight className={featured ? 'h-4 w-4' : 'h-3 w-3'} strokeWidth={2} />
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
  const [userSurvey, setUserSurvey] = useState<UserSurveyInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchJourneys = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await apiClient.get('/simple-auth/journeys');
      const resp = (res.data ?? {}) as JourneysResponse;
      const list = (resp.journeys ?? []) as JourneyItem[];
      setJourneys(list);
      // 用户级问卷直读：登录后即可获取，不依赖激活码
      if (resp.user_survey) {
        setUserSurvey(resp.user_survey);
      }
      setFetchError(null);

      // ── 后端为准：同步所有旅程的阶段进度到 localStorage ──
      // 跨设备登录或清缓存后，确保本地 session 与后端一致
      for (const journey of list) {
        if (!journey.explore_resume?.resume_phase) continue;
        try {
          const local = loadSession(journey.activation_code);
          const updated = applyExploreResumeToSession(local, journey.explore_resume);
          // 仅在本地与后端不一致时更新（减少不必要的写入）
          if (
            updated.currentPhase !== local.currentPhase ||
            JSON.stringify(updated.unlockedPhases) !== JSON.stringify(local.unlockedPhases)
          ) {
            saveSession({ ...updated, activationCode: journey.activation_code });
          }
        } catch {
          // 单个旅程同步失败不影响其他
        }
      }

      // 清理已不存在的旅程的本地缓存（跨设备或旅程被删除后避免幽灵数据）
      try {
        const activeCodes = new Set(list.map((j) => j.activation_code));
        const lastCode = localStorage.getItem('explore_last_code');
        if (lastCode && !activeCodes.has(lastCode)) {
          // 最后使用的激活码已不存在，清除其缓存并重置
          clearThreadCache(lastCode);
          localStorage.removeItem(`explore_session_${lastCode}`);
          if (list.length > 0) {
            setLastActivationCode(list[0].activation_code);
          }
        }
      } catch {}
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
    // 清除线程缓存，确保进入聊天页时从后端拉取最新数据（跨设备一致性）
    clearThreadCache(code);
    if (phase === 'report') {
      router.push('/explore/report');
      return;
    }
    // 校验目标 phase 是否已解锁：优先跳用户点击的 phase，未解锁则降级到 resume_phase
    const effective = effectiveResumeForNodes(resume);
    if (phase !== 'report' && !effective.unlocked_phases.includes(phase as PhaseKey)) {
      router.push(`/explore/chat/${effective.resume_phase}`);
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
          {/* 用户级问卷信息：登录后即可见 */}
          {userSurvey && userSurvey.completed && (
            <UserSurveyCard survey={userSurvey} t={t} />
          )}
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
        <div className="space-y-4">
          {/* 无旅程时仍显示用户问卷信息 */}
          {userSurvey && userSurvey.completed && (
            <UserSurveyCard survey={userSurvey} t={t} />
          )}
          <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
            <p className="text-bd-muted mb-6">尚未开始探索，或未激活当前会话</p>
            <Link
              href="/explore/intro"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
            >
              {t('common.startExplore')}
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
