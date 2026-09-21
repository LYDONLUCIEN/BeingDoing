'use client';

import { useState, useEffect, useCallback, type CSSProperties } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, Lock, BookOpen, ShoppingCart } from 'lucide-react';
import { PHASES, loadSession, saveSession, setLastActivationCode, applyExploreResumeToSession, setUserSurveyCompleted, type PhaseKey } from '@/lib/explore/session';
import { clearThreadCache } from '@/lib/explore/threads';
import { useLocale } from '@/hooks/useLocale';
import { apiClient } from '@/lib/api/client';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';
import { formatUTC } from '@/lib/utils/formatTime';
import { useAuthStore } from '@/stores/authStore';
import type { SurveyData } from '@/lib/survey/schema';
import PurchaseModal from '@/components/payment/PurchaseModal';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';

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
  /** P-A：码类型（trial 试用 / full 完整），老后端无此字段时不展示 badge */
  code_type?: 'trial' | 'full';
  /** P-A：完整码有效期；试用码为 null（不过期） */
  expires_at?: string | null;
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
  // 委托 formatUTC，确保 tz-aware 字符串按浏览器本地时区显示
  const formatted = formatUTC(iso, 'zh-CN');
  return formatted === '-' ? iso : formatted;
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
  onViewReport,
  t,
}: {
  journey: JourneyItem;
  featured?: boolean;
  onNavigate: (code: string, phase: string) => void;
  onViewReport: (code: string) => void;
  t: (k: string) => string;
}) {
  const nodes = buildNodes(journey.explore_resume);
  const resumePhase = effectiveResumeForNodes(journey.explore_resume).resume_phase;
  const reportUnlocked = Boolean(journey.explore_resume?.report_unlocked);

  return (
    <article className={`ol-profile-journey-card ol-profile-surface ${featured ? 'is-featured' : ''}`}>
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <p className="ol-profile-journey-eyebrow">{reportUnlocked ? '历史归档' : featured ? '正在探索' : '职业旅程'}</p>
          <h2 className={`font-medium text-bd-fg ${featured ? 'text-xl' : 'text-base'}`}>
            {featured ? t('dashboard.journeyTitle') : `旅程 ${journey.activation_code.slice(-6)}`}
          </h2>
        </div>
        <span className={`ol-profile-status ${reportUnlocked ? 'is-complete' : ''}`}>
          {journeyStatusLabel(journey)}
        </span>
      </div>

      <div className="mb-4 space-y-0.5 text-xs text-bd-muted">
        <p className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-bd-fg/80">{journey.activation_code}</span>
          {journey.code_type && (
            <span
              className={`ol-pill ${
                journey.code_type === 'trial'
                  ? 'ol-pill--blue'
                  : 'ol-pill--amber'
              }`}
            >
              {t(`dashboard.codeType.${journey.code_type}`)}
            </span>
          )}
        </p>
        <p>开始时间：{formatJourneyDateTime(journey.created_at)}</p>
        <p>最后编辑：{formatJourneyDateTime(journey.last_activity_at)}</p>
      </div>

      {/* 阶段轨道：HTML .profile-stage-track——6 列等分 grid + 轨道线，无箭头 */}
      <div className="ol-profile-stage-scroll overflow-x-auto overflow-y-visible [-webkit-overflow-scrolling:touch]">
        <div className={`ol-profile-stage-track ${featured ? 'is-featured' : ''}`} role="list" aria-label="旅程进度">
          {nodes.map((node) => (
            <div key={node.id} className="ol-profile-stage" role="listitem">
                {node.id === 'report' ? (
                  <button
                    type="button"
                    onClick={() =>
                      node.status !== 'incomplete' && onNavigate(journey.activation_code, node.id)
                    }
                    disabled={node.status === 'incomplete'}
                    aria-label="报告"
                    className={`ol-report-book ${featured ? 'is-featured' : ''} ${
                      node.status === 'incomplete' ? 'is-locked' : 'is-ready'
                    }`}
                  >
                    {node.status === 'incomplete' ? (
                      <Lock className="ol-report-book-lock" aria-hidden />
                    ) : (
                      <BookOpen className="ol-report-book-icon" aria-hidden />
                    )}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      node.status !== 'incomplete' && onNavigate(journey.activation_code, node.id)
                    }
                    disabled={node.status === 'incomplete'}
                    aria-label={node.label}
                    className={`ol-stage-mark ${featured ? 'is-featured' : ''} is-${node.status}`}
                    style={{ '--stage': node.color } as CSSProperties}
                  >
                    {node.status === 'incomplete' ? (
                      <Lock className="ol-stage-lock" aria-hidden />
                    ) : node.status === 'in-progress' ? (
                      <span className="ol-stage-dot" aria-hidden />
                    ) : null}
                    {node.status === 'completed' && (
                      <span className="ol-stage-badge" aria-hidden>
                        <Check strokeWidth={3.5} />
                      </span>
                    )}
                  </button>
                )}
                <b>{node.label}</b>
                <small>
                  {node.status === 'completed'
                    ? node.id === 'report'
                      ? '已生成'
                      : '已完成'
                    : node.status === 'in-progress'
                      ? '进行中'
                      : '未开始'}
                </small>
            </div>
          ))}
        </div>
      </div>

      {/* 主按钮：所有旅程卡常驻；报告已解锁时变为「查看报告」 */}
      <footer className={`flex gap-3 ${featured ? 'mt-6' : 'mt-4'}`}>
        {reportUnlocked ? (
          <button
            type="button"
            onClick={() => onViewReport(journey.activation_code)}
            className="ol-profile-primary"
          >
            {t('dashboard.viewReport')} →
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onNavigate(journey.activation_code, resumePhase)}
            className="ol-profile-primary"
          >
            继续探索 →
          </button>
        )}
      </footer>
    </article>
  );
}

/** 购买套餐卡片：展示季度/年度价格入口，点击打开购买弹窗 */
function PurchaseCard({ onBuy, t }: { onBuy: () => void; t: (k: string) => string }) {
  return (
    <div className="ol-profile-purchase-card ol-profile-surface">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-bd-overlay-md">
            <ShoppingCart className="h-5 w-5 text-bd-muted" />
          </div>
          <div className="min-w-0">
            <h2 className="font-medium text-bd-fg text-base">{t('dashboard.purchaseCard.title')}</h2>
            <p className="text-xs text-bd-muted mt-0.5">{t('dashboard.purchaseCard.desc')}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-left text-xs text-bd-muted leading-tight">
            <div>{t('dashboard.purchaseCard.quarterly')} <span className="font-semibold text-bd-fg">¥69</span> · {t('dashboard.purchaseCard.popular')}</div>
            <div>{t('dashboard.purchaseCard.annual')} <span className="font-semibold text-bd-fg">¥159</span></div>
          </div>
          <button
            type="button"
            onClick={onBuy}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-bd-ui-accent text-bd-ui-accent-fg hover:opacity-90"
          >
            {t('dashboard.purchaseCard.buy')}
          </button>
        </div>
      </div>
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
  const [purchaseOpen, setPurchaseOpen] = useState(false);

  const fetchJourneys = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const isUiPreview =
        process.env.NODE_ENV === 'development' &&
        typeof window !== 'undefined' &&
        new URLSearchParams(window.location.search).get('ui_preview') === '1';
      if (isUiPreview) {
        const previewJourneys: JourneyItem[] = [
          {
            activation_code: 'OPENLIFE-2026',
            code_type: 'full',
            expires_at: '2027-06-18T08:30:00Z',
            mode: 'simple',
            status: 'active',
            created_at: '2026-08-25T09:06:00Z',
            last_activity_at: new Date().toISOString(),
            explore_resume: {
              resume_phase: 'interests',
              unlocked_phases: ['values', 'strengths', 'interests'],
              report_unlocked: false,
            },
            is_latest: true,
          },
          {
            activation_code: 'ARCHIVE-0915',
            code_type: 'full',
            expires_at: '2027-03-15T08:30:00Z',
            mode: 'simple',
            status: 'active',
            created_at: '2026-08-24T09:06:00Z',
            last_activity_at: '2026-09-15T10:20:00Z',
            explore_resume: {
              resume_phase: 'rumination',
              unlocked_phases: ['values', 'strengths', 'interests', 'purpose', 'rumination'],
              report_unlocked: true,
            },
          },
        ];
        setJourneys(previewJourneys);
        setUserSurvey({
          completed: true,
          survey_data: {
            nickname: '小路',
            career_status: '职业转型中',
            industry: '互联网与人工智能',
            education_degree: '硕士学历',
            city: '北京',
            position: '产品经理',
          } as SurveyData,
        });
        setFetchError(null);
        return;
      }
      const res = await apiClient.get('/simple-auth/journeys');
      const resp = (res.data ?? {}) as JourneysResponse;
      const list = (resp.journeys ?? []) as JourneyItem[];
      setJourneys(list);
      // 用户级问卷直读：登录后即可获取，不依赖激活码
      if (resp.user_survey) {
        setUserSurvey(resp.user_survey);
        // 后端为准回填本地完成标记：登出会清除 localStorage 中的问卷标记，
        // 而 chat 页问卷门控只认 localStorage，不回填会导致重新登录后每次进探索都被拉去填问卷
        if (resp.user_survey.completed) {
          const uid = useAuthStore.getState().user?.user_id;
          if (uid) setUserSurveyCompleted(uid, true);
        }
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
    const previewSuffix =
      process.env.NODE_ENV === 'development' &&
      typeof window !== 'undefined' &&
      new URLSearchParams(window.location.search).get('ui_preview') === '1'
        ? '?ui_preview=1'
        : '';
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
      router.push(`/explore/report${previewSuffix}`);
      return;
    }
    // 校验目标 phase 是否已解锁：优先跳用户点击的 phase，未解锁则降级到 resume_phase
    const effective = effectiveResumeForNodes(resume);
    if (phase !== 'report' && !effective.unlocked_phases.includes(phase as PhaseKey)) {
      router.push(`/explore/chat/${effective.resume_phase}${previewSuffix}`);
      return;
    }
    router.push(`/explore/chat/${phase}${previewSuffix}`);
  };

  /** 查看报告：写入「上次激活码」并走 /explore/report 中枢页（保留其埋点与状态检查） */
  const handleViewReport = (code: string) => {
    setLastActivationCode(code);
    router.push(`/explore/report?code=${encodeURIComponent(code)}`);
  };

  const featured = journeys[0]; // 最近使用的排第一
  const others = journeys.slice(1);
  const reportCount = journeys.filter((journey) => journey.explore_resume?.report_unlocked).length;

  return (
    <div className="ol-profile-content">
      <DashboardPageHeader
        kicker="YOUR JOURNEY"
        title={t('dashboard.currentProgress')}
        description="你的每一次对话，都会在这里留下可以继续的线索。"
      />

      {!loading && (
        <div className="ol-profile-overview" aria-label="探索概览">
          <article>
            <span>{String(journeys.length).padStart(2, '0')}</span>
            <p>职业旅程<small>{journeys.length ? '正在记录你的探索路径' : '从第一次探索开始'}</small></p>
          </article>
          <article>
            <span>05</span>
            <p>探索阶段<small>从认识自己到沉淀方向</small></p>
          </article>
          <article>
            <span>{String(reportCount).padStart(2, '0')}</span>
            <p>已生成报告<small>{reportCount ? '可以随时回看' : '完成旅程后生成'}</small></p>
          </article>
        </div>
      )}

      {loading ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl p-8 text-center">
          <p className="text-bd-muted">加载中...</p>
        </div>
      ) : featured ? (
        <div className="ol-profile-journey-list">
          <JourneyCard journey={featured} featured onNavigate={handleNavigate} onViewReport={handleViewReport} t={t} />
          {others.map((j) => (
            <JourneyCard key={j.activation_code} journey={j} onNavigate={handleNavigate} onViewReport={handleViewReport} t={t} />
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
        <div className="ol-profile-journey-list">
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

      {/* 购买激活码卡片：所有状态下常驻 */}
      {!loading && (
        <div className="mt-4">
          <PurchaseCard onBuy={() => setPurchaseOpen(true)} t={t} />
        </div>
      )}

      <PurchaseModal open={purchaseOpen} onClose={() => setPurchaseOpen(false)} />
    </div>
  );
}
