'use client';

import { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useRouter, useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import {
  ChevronRight,
  ChevronDown,
  ArrowUp,
  Square,
  Copy,
  FileText,
  ListFilter,
  Loader2,
} from 'lucide-react';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import DimensionConclusionCard, { type DimensionConclusionData } from '@/components/explore/DimensionConclusionCard';
import ChatPhaseBackground from '@/components/explore/ChatPhaseBackground';
import ExploreLandingMeshLayers from '@/components/explore/ExploreLandingMeshLayers';
import ChatPhaseSidebar from '@/components/explore/ChatPhaseSidebar';
import RuminationSectionProgress from '@/components/explore/RuminationSectionProgress';
import RuminationTableWidget, {
  HYP_CONFIRM_KEY,
  OTHER_SELECT_VALUE,
} from '@/components/explore/RuminationTableWidget';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
import { authApi } from '@/lib/api/auth';
import {
  PHASES,
  loadSession,
  saveSession,
  unlockNextPhase,
  getLastActivationCode,
  applyExploreResumeToSession,
  type PhaseKey,
  type ExploreSession,
} from '@/lib/explore/session';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';
import {
  getThreads,
  setThreadsForPhase,
  saveThread,
  addThread,
  removeThread,
  getActiveThreadId,
  setActiveThreadId,
  createThreadId,
  collapseRuminationThreadsToOne,
  pickCanonicalRuminationThread,
  isCacheStale,
  type ChatThread,
  type RuminationTablePayload,
  type ThreadMessage,
} from '@/lib/explore/threads';
import {
  loadRuminationStepBoundaries,
  saveRuminationStepBoundaries,
  ensureDefaultStepOne,
  cutMessagesForRuminationStepRefill,
  sliceMessagesForRuminationStep,
} from '@/lib/explore/ruminationStepBoundaries';
import {
  computeMaxReachedFromSnapshots,
  isRuminationFilterStepReachable,
  RUMINATION_FILTER_STEP_MAX,
} from '@/lib/explore/ruminationProgressNav';
import {
  ruminationApi,
  type RuminationProgress,
  type RuminationSubmitData,
} from '@/lib/api/rumination';
import {
  simulateFixedRuminationOpening,
  streamRuminationStepOpening,
} from '@/lib/explore/ruminationStepOpening';
import { useLocale } from '@/hooks/useLocale';
import { useAuthStore } from '@/stores/authStore';
import { fetchAdminSystemSettings } from '@/lib/api/admin';

// Phase metadata (color only; desc/hint come from i18n)
const PHASE_COLORS: Record<PhaseKey, string> = {
  values: 'text-bd-phase-values',
  strengths: 'text-bd-phase-strengths',
  interests: 'text-bd-phase-interests',
  purpose: 'text-bd-phase-purpose',
  rumination: 'text-bd-phase-rumination',
};

const BACKEND_PHASE: Record<PhaseKey, string> = {
  values: 'values',
  strengths: 'strengths',
  interests: 'interests',
  purpose: 'purpose',
  rumination: 'rumination',
};

/** 待确认结论仅存 metadata、无 conclusion_card 消息行时，从历史 meta 补一条卡，避免必须刷新才看见 */
function mergePendingDraftIntoMessagesFromMeta(
  msgs: ThreadMessage[],
  meta: Record<string, unknown> | undefined
): ThreadMessage[] {
  if (!meta) return msgs;
  const state = String(meta.conclusion_state ?? '').toLowerCase();
  const draft = meta.conclusion_draft;
  if (state !== 'pending' || draft === null || draft === undefined || typeof draft !== 'object') {
    return msgs;
  }
  if (msgs.some((m) => m.type === 'dimension_conclusion')) return msgs;
  const now = Date.now();
  return [
    ...msgs,
    {
      id: `h_pending_${now}`,
      role: 'assistant',
      content: '',
      type: 'dimension_conclusion',
      conclusionData: draft as DimensionConclusionData,
      conclusionCollapsed: false,
      conclusionConfirmed: false,
      createdAt: now,
    },
  ];
}

/** 重新生成假设后按「槽位」写回确认列，避免新文案导致选中丢失 */
function mapRuminationHypConfirmAfterRegen(
  prevRow: Record<string, unknown>,
  nextRow: Record<string, unknown>,
  pendingLabel: string
): string {
  const pv = String(prevRow[HYP_CONFIRM_KEY] ?? '');
  const o1 = String(prevRow['假设1'] ?? '').trim();
  const o2 = String(prevRow['假设2'] ?? '').trim();
  const o3 = String(prevRow['假设3'] ?? '').trim();
  const n1 = String(nextRow['假设1'] ?? '').trim();
  const n2 = String(nextRow['假设2'] ?? '').trim();
  const n3 = String(nextRow['假设3'] ?? '').trim();

  type Slot = 'h1' | 'h2' | 'h3' | 'pending' | 'other_empty' | 'other_custom';
  let slot: Slot;
  if (pv === OTHER_SELECT_VALUE || !pv.trim()) {
    slot = 'other_empty';
  } else if (pendingLabel && (pv === pendingLabel || pv === '待定')) {
    slot = 'pending';
  } else if (o1 && pv === o1) {
    slot = 'h1';
  } else if (o2 && pv === o2) {
    slot = 'h2';
  } else if (o3 && pv === o3) {
    slot = 'h3';
  } else {
    slot = 'other_custom';
  }

  if (slot === 'h1' && n1) return n1;
  if (slot === 'h2' && n2) return n2;
  if (slot === 'h3' && n3) return n3;
  if (slot === 'pending') return pendingLabel;
  if (slot === 'other_custom') {
    if (pv && pv !== OTHER_SELECT_VALUE && ![n1, n2, n3].includes(pv)) return pv;
    return OTHER_SELECT_VALUE;
  }
  return OTHER_SELECT_VALUE;
}

/** 表格提交：全屏遮罩 + 动态省略号（Portal 挂到 body） */
function RuminationTableSubmitPortal({
  open,
  lineBefore,
  lineAfter,
}: {
  open: boolean;
  lineBefore: string;
  lineAfter: string;
}) {
  const [mounted, setMounted] = useState(false);
  const [dots, setDots] = useState('');
  useEffect(() => {
    setMounted(true);
  }, []);
  useEffect(() => {
    if (!open) {
      setDots('');
      return;
    }
    let i = 0;
    const id = window.setInterval(() => {
      i = (i + 1) % 4;
      setDots('.'.repeat(i));
    }, 400);
    return () => window.clearInterval(id);
  }, [open]);
  if (!mounted || !open) return null;
  return createPortal(
    <motion.div
      className="fixed left-0 right-0 top-14 bottom-0 z-40 flex items-center justify-center bg-black/50 px-4 backdrop-blur-[3px]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <motion.div
        className="flex w-full max-w-[20rem] flex-col items-center gap-6 rounded-2xl bg-white px-8 py-10 shadow-[0_25px_80px_-12px_rgba(0,0,0,0.4)] ring-1 ring-neutral-200/90 sm:max-w-[22rem] sm:px-10"
        role="status"
        aria-live="polite"
        aria-busy="true"
        initial={{ scale: 0.94, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      >
        <Loader2
          className="h-12 w-12 animate-spin text-sky-600 drop-shadow-sm motion-reduce:animate-none"
          aria-hidden
        />
        <p className="text-balance text-center text-[0.95rem] font-semibold leading-relaxed text-neutral-800 sm:text-base">
          <span>{lineBefore}</span>
          <span className="inline-block min-w-[1.15em] text-left font-bold tabular-nums tracking-tight text-sky-700">
            {dots}
          </span>
          <span>{lineAfter}</span>
        </p>
      </motion.div>
    </motion.div>,
    document.body
  );
}

export default function ChatPhasePage() {
  const router = useRouter();
  const params = useParams();
  const { t } = useLocale();
  const phase = (params.phase as string) as PhaseKey;

  const [session, setSession] = useState<ExploreSession | null>(null);
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadIdState] = useState<string | null>(null);
  const activeThreadIdRef = useRef<string | null>(null);
  activeThreadIdRef.current = activeThreadId;
  const [backendSyncedThreadId, setBackendSyncedThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [requestConclusionDraftBusy, setRequestConclusionDraftBusy] = useState(false);
  /** 流式进行中点其它会话：先确认再切换 */
  const [threadSwitchDialogOpen, setThreadSwitchDialogOpen] = useState(false);
  const [pendingSwitchThread, setPendingSwitchThread] = useState<ChatThread | null>(null);
  /** 沉淀：表格确认后自动插入的子步引导语（固定模拟流 / LLM 流）进行中 */
  const [ruminationGuideBusy, setRuminationGuideBusy] = useState(false);
  const ruminationGuideAbortRef = useRef<AbortController | null>(null);
  const [initLoading, setInitLoading] = useState(true);
  const [threadsFetched, setThreadsFetched] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);
  const [conclusionLoading, setConclusionLoading] = useState(false);
  const [adminDebugBypass, setAdminDebugBypass] = useState(false);
  const [adminPolicyLoaded, setAdminPolicyLoaded] = useState(false);
  const [stepLocked, setStepLocked] = useState(false);
  /** 沉淀阶段：表格固定在左栏，与右侧消息流解耦 */
  const [ruminationTablePayload, setRuminationTablePayload] = useState<
    ThreadMessage['tablePayload'] | null
  >(null);
  /** 表格提交等操作后递增，驱动标题区六段进度条重新拉取 */
  const [ruminationProgressNonce, setRuminationProgressNonce] = useState(0);
  /** 与后端 filter_step（1–7）对齐：当前查看的筛选子步、已提交到的最远步、完整 progress（含快照） */
  const [ruminationProgressState, setRuminationProgressState] =
    useState<RuminationProgress | null>(null);
  const [ruminationViewStep, setRuminationViewStep] = useState(1);
  const [ruminationMaxReached, setRuminationMaxReached] = useState(0);
  const [ruminationStepBoundaries, setRuminationStepBoundaries] = useState<Record<string, number>>(
    {}
  );
  const ruminationStepBoundariesRef = useRef<Record<string, number>>({});
  ruminationStepBoundariesRef.current = ruminationStepBoundaries;
  const [ruminationWorkbenchStacked, setRuminationWorkbenchStacked] = useState(false);
  const [ruminationTableSubmitting, setRuminationTableSubmitting] = useState(false);
  const [ruminationTableNavLoading, setRuminationTableNavLoading] = useState(false);
  const [hypothesisRegeneratingRowIndex, setHypothesisRegeneratingRowIndex] = useState<number | null>(
    null
  );
  const [ruminationRefillConfirmOpen, setRuminationRefillConfirmOpen] = useState(false);
  const [ruminationStep7FinalizeOpen, setRuminationStep7FinalizeOpen] = useState(false);
  const pendingStep7SubmitRef = useRef<{
    rows: Record<string, unknown>[];
    payload: NonNullable<ThreadMessage['tablePayload']>;
    submitThreadId: string;
  } | null>(null);
  const [ruminationRowContext, setRuminationRowContext] = useState<{
    rowIndex: number;
    label: string;
  } | null>(null);
  const ruminationWorkbenchRef = useRef<HTMLDivElement>(null);
  const { user, setTokens } = useAuthStore();
  const userChatAvatarInitials = (user?.username || user?.email || 'U').slice(0, 2).toUpperCase();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);
  /** 为 true 时流式输出会滚到底部；用户上滑后为 false，点「回到底」再置 true */
  const stickToBottomRef = useRef(true);
  const messagesRef = useRef<ThreadMessage[]>([]);
  messagesRef.current = messages;
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const phaseMeta = {
    color: PHASE_COLORS[phase],
    desc: t(`explore.chat.phaseMeta.${phase}.desc`),
    hint: t(`explore.chat.phaseMeta.${phase}.hint`),
  };
  const phaseInfo = PHASES.find((p) => p.key === phase);
  const phaseLabel = t(`explore.chat.phaseLabels.${phase}`);
  const canCreateMoreThreads =
    phase === 'rumination'
      ? false
      : !stepLocked && (adminDebugBypass || threads.length < 5);

  /** 仅在线程 id 集合变化时触发「加载消息」effect，避免因 threads 引用反复变（persist / save 后 getThreads）而重复 init */
  const threadListSignature = useMemo(() => threads.map((t) => t.id).join('|'), [threads]);

  /** 侧栏预览：当前选中线程的消息以 React state 为准（列表里的 thread 可能仍是 messages:[]） */
  const threadsForSidebar = useMemo(() => {
    if (!activeThreadId) return threads;
    return threads.map((th) => (th.id === activeThreadId ? { ...th, messages } : th));
  }, [threads, activeThreadId, messages]);

  /** 沉淀：按筛选子步切片同一线程消息（localStorage 持久化下标，见 ruminationStepBoundaries） */
  const displayMessages = useMemo(() => {
    if (phase !== 'rumination') return messages;
    const fs = ruminationProgressState?.filter_step ?? 0;
    const inFilterSection =
      (ruminationProgressState?.main_section === 'filter' && fs > 0) ||
      /** 管理员：筛选表已结束后仍可回看/改表，聊天区继续按子步切片 */
      (adminDebugBypass && ruminationProgressState?.main_section === 'final_choice');
    return sliceMessagesForRuminationStep(
      messages,
      ruminationViewStep,
      ruminationStepBoundaries,
      {
        inFilterSection,
        activeFilterStep: inFilterSection ? fs : null,
      }
    );
  }, [
    phase,
    messages,
    ruminationViewStep,
    ruminationStepBoundaries,
    ruminationProgressState?.main_section,
    ruminationProgressState?.filter_step,
    adminDebugBypass,
  ]);

  const mapHistoryToThreadMessages = useCallback(
    (history: any[], meta: any): ThreadMessage[] =>
      history.map((m, i) => {
        const id = `h_${i}_${m.id ?? i}`;
        const createdAt = m.created_at ? new Date(m.created_at).getTime() : undefined;
        if (m.role === 'conclusion_card') {
          let conclusionData: DimensionConclusionData | undefined = undefined;
          if (m.card_payload && typeof m.card_payload === 'object') {
            conclusionData = m.card_payload as DimensionConclusionData;
          } else if (typeof m.content === 'string' && m.content.trim()) {
            try {
              conclusionData = JSON.parse(m.content) as DimensionConclusionData;
            } catch {
              conclusionData = undefined;
            }
          }
          return {
            id,
            role: 'assistant',
            content: '',
            type: 'dimension_conclusion',
            conclusionData,
            conclusionCollapsed: false,
            conclusionConfirmed: !!meta?.thread_completed,
            createdAt,
          } satisfies ThreadMessage;
        }

        const role = (m.role === 'table_widget' ? 'assistant' : m.role) as 'user' | 'assistant';
        const base: ThreadMessage = {
          id,
          role,
          content: m.content ?? '',
          createdAt,
        };
        if (m.role === 'table_widget' && m.card_payload) {
          base.type = 'table_widget';
          base.tablePayload = m.card_payload as ThreadMessage['tablePayload'];
        }
        return base;
      }),
    []
  );

  // 管理员调试策略（仅 super_admin 尝试读取）
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!user?.is_super_admin) {
        if (!cancelled) {
          setAdminDebugBypass(false);
          setAdminPolicyLoaded(true);
        }
        return;
      }
      try {
        const sys = await fetchAdminSystemSettings();
        const enabled =
          Boolean((sys as any)?.ADMIN_DEBUG_POLICY_ENABLED) &&
          Boolean((sys as any)?.ADMIN_DEBUG_WORKSPACE_ENABLED);
        if (!cancelled) setAdminDebugBypass(enabled);
      } catch {
        if (!cancelled) setAdminDebugBypass(false);
      } finally {
        if (!cancelled) setAdminPolicyLoaded(true);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [user?.is_super_admin]);

  /** 沉淀页 mesh 背景与激活页一致时，统一顶栏/布局底色 */
  useEffect(() => {
    if (phase !== 'rumination') return;
    document.documentElement.setAttribute('data-rumination-mesh-page', 'true');
    return () => document.documentElement.removeAttribute('data-rumination-mesh-page');
  }, [phase]);

  /** 子步与消息下标映射：按激活码 + thread 持久化 */
  useEffect(() => {
    if (phase !== 'rumination' || !activationCode || !activeThreadId) return;
    const loaded = ensureDefaultStepOne(
      loadRuminationStepBoundaries(activationCode, activeThreadId)
    );
    setRuminationStepBoundaries(loaded);
  }, [phase, activationCode, activeThreadId]);

  /** 工作台宽度 < 视口 2/3 时改为上下堆叠（上表下聊） */
  useLayoutEffect(() => {
    if (phase !== 'rumination') return;
    let ro: ResizeObserver | null = null;
    let update: (() => void) | undefined;
    const t = window.setTimeout(() => {
      const el = ruminationWorkbenchRef.current;
      if (!el) return;
      update = () => {
        const vw = window.innerWidth;
        const w = el.getBoundingClientRect().width;
        setRuminationWorkbenchStacked(w < (vw * 2) / 3);
      };
      update();
      ro = new ResizeObserver(update);
      ro.observe(el);
      window.addEventListener('resize', update);
    }, 0);
    return () => {
      window.clearTimeout(t);
      ro?.disconnect();
      if (update) window.removeEventListener('resize', update);
    };
  }, [phase, initLoading]);

  useEffect(() => {
    if (phase === 'rumination') setRuminationRowContext(null);
  }, [phase, ruminationTablePayload?.step, ruminationTablePayload?.rows]);

  // Auth & redirect
  useEffect(() => {
    if (!adminPolicyLoaded) return;
    if (!PHASES.find((p) => p.key === phase)) {
      router.replace('/explore/activate');
      return;
    }
    const code = getLastActivationCode();
    if (!code) {
      router.replace('/explore/activate');
      return;
    }
    setActivationCode(code);
    const s = loadSession(code);
    setSession(s);
    if (!s?.surveyCompleted) {
      router.replace('/explore/survey');
      return;
    }
    if (!adminDebugBypass && !s.unlockedPhases.includes(phase)) {
      router.replace(`/explore/chat/${s.currentPhase}`);
      return;
    }
  }, [phase, router, adminPolicyLoaded, adminDebugBypass]);

  // 从后端同步线程列表（主数据源，支持跨设备）
  useEffect(() => {
    if (!activationCode || !phase) return;
    setThreadsFetched(false);
    setStepLocked(false);
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.get('/simple-chat/threads', {
          params: { activation_code: activationCode, phase: BACKEND_PHASE[phase] },
        });
        setStepLocked(Boolean(res.data?.step_locked));
        const raw = (res.data?.threads ?? []) as Array<{
          id: string;
          title: string;
          status: string;
          createdAt: number;
          dimensionConclusion?: DimensionConclusionData;
          step_locked?: boolean;
        }>;
        const list: ChatThread[] = raw.map((t) => ({
          id: t.id,
          title: t.title,
          status: t.status as 'in-progress' | 'completed',
          messages: [],
          createdAt: t.createdAt,
          dimensionConclusion: t.dimensionConclusion,
        }));
        // 前四维：为每个会话预加载历史，侧栏显示首行与轮数。
        // 沉淀（rumination）：产品为单线程、无多会话侧栏，只拉「主线程」一条 history，与 collapse 规则一致。
        const sessionIdByThread: Record<string, string> = {};
        const hydrateThreadFromHistory = async (th: ChatThread): Promise<ChatThread> => {
          try {
            const h = await apiClient.get('/simple-chat/history', {
              params: { activation_code: activationCode, phase: BACKEND_PHASE[phase], thread_id: th.id },
            });
            const history: any[] = h.data.messages ?? [];
            const meta = h.data?.metadata ?? {};
            if (typeof meta?.step_locked === 'boolean') {
              setStepLocked(Boolean(meta.step_locked));
            }
            if (meta?.session_id) sessionIdByThread[th.id] = String(meta.session_id);
            const msgs = mergePendingDraftIntoMessagesFromMeta(
              mapHistoryToThreadMessages(history, meta),
              meta as Record<string, unknown>
            );
            const concl = meta.dimension_conclusion as DimensionConclusionData | undefined;
            return {
              ...th,
              messages: msgs,
              dimensionConclusion: concl ?? th.dimensionConclusion,
              ...(meta.thread_completed ? { status: 'completed' as const } : {}),
            };
          } catch {
            return th;
          }
        };

        let hydratedList: ChatThread[];
        if (phase === 'rumination') {
          if (list.length === 0) {
            hydratedList = [];
          } else {
            const canonical = pickCanonicalRuminationThread(list);
            hydratedList =
              canonical != null ? [await hydrateThreadFromHistory(canonical)] : [];
          }
        } else {
          hydratedList = await Promise.all(list.map((th) => hydrateThreadFromHistory(th)));
        }

        let mergedList = hydratedList;
        if (phase === 'rumination' && hydratedList.length > 1) {
          mergedList = collapseRuminationThreadsToOne(hydratedList);
        }
        setThreadsForPhase(activationCode, phase, mergedList);
        if (cancelled) return;
        setThreads(mergedList);
        const localActiveId = getActiveThreadId(activationCode, phase);
        const activeId =
          mergedList.length > 0
            ? (mergedList.some((x) => x.id === localActiveId) ? localActiveId : mergedList[0].id)
            : null;
        setActiveThreadIdState(activeId);
        if (activeId) setActiveThreadId(activationCode, phase, activeId);
        const activeThread = mergedList.find((x) => x.id === activeId) || null;
        if (activeThread) {
          setMessages(activeThread.messages);
          setBackendSyncedThreadId(activeThread.id);
          const sessId = sessionIdByThread[activeThread.id];
          if (sessId) {
            setBackendSessionId(sessId);
            const s = loadSession(activationCode);
            saveSession({ ...s, sessionId: sessId });
          }
        } else {
          setMessages([]);
          setBackendSyncedThreadId(null);
        }
      } catch (err: any) {
        if (cancelled) return;
        if (err?.code === 'ERR_NETWORK' || err?.message?.includes('Network')) {
          setChatError(t('explore.chat.networkError'));
        }
        // 网络失败时：仅在缓存未过期时回退到 localStorage（避免使用过期数据）
        if (!isCacheStale(activationCode)) {
          let list = getThreads(activationCode, phase);
          if (phase === 'rumination' && list.length > 1) {
            list = collapseRuminationThreadsToOne(list);
            setThreadsForPhase(activationCode, phase, list);
          }
          setThreads(list);
          const activeId = getActiveThreadId(activationCode, phase);
          setActiveThreadIdState(activeId);
        } else {
          // 缓存过期，显示空状态，不使用可能不一致的旧数据
          setThreads([]);
          setActiveThreadIdState(null);
        }
      }
      if (!cancelled) setThreadsFetched(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [activationCode, phase, mapHistoryToThreadMessages, t]);

  // 激活线程切换：优先直接使用已预加载内容；仅在“完全首次进入且无会话”时才触发 init。
  useEffect(() => {
    if (!activationCode || !phase || !threadsFetched) return;
    let cancelled = false;
    setInitLoading(true);

    const list = threads;
    const activeId = activeThreadId;

    if (list.length === 0) {
      // 若该 step 已有历史（无 thread_id 默认会话），优先恢复，不主动 init 创建新会话
      (async () => {
        try {
          // 防止刷新竞态导致误判为空：先再次确认后端 threads。
          const threadsRes = await apiClient.get('/simple-chat/threads', {
            params: { activation_code: activationCode, phase: BACKEND_PHASE[phase] },
          });
          const backendThreads = (threadsRes.data?.threads ?? []) as Array<{
            id: string;
            title: string;
            status: string;
            createdAt: number;
            dimensionConclusion?: DimensionConclusionData;
          }>;
          if (!cancelled && backendThreads.length > 0) {
            let syncedThreads: ChatThread[] = backendThreads.map((t) => ({
              id: t.id,
              title: t.title,
              status: t.status as 'in-progress' | 'completed',
              messages: [],
              createdAt: t.createdAt,
              dimensionConclusion: t.dimensionConclusion,
            }));
            if (phase === 'rumination' && syncedThreads.length > 1) {
              syncedThreads = collapseRuminationThreadsToOne(syncedThreads);
            }
            const first =
              phase === 'rumination'
                ? pickCanonicalRuminationThread(syncedThreads) ?? syncedThreads[0]
                : syncedThreads[0];
            /** 沉淀：本地 threads 为空但后端已有会话时，必须拉 history + 必要时 init，否则 activeThreadId 无消息、表格提交 thread 不同步 */
            if (phase === 'rumination') {
              let msgs: ThreadMessage[] = [];
              try {
                const h = await apiClient.get('/simple-chat/history', {
                  params: {
                    activation_code: activationCode,
                    phase: BACKEND_PHASE[phase],
                    thread_id: first.id,
                  },
                });
                const history: any[] = h.data.messages ?? [];
                const meta = h.data?.metadata ?? {};
                if (typeof meta?.step_locked === 'boolean') {
                  setStepLocked(Boolean(meta.step_locked));
                }
                const sessId = h.data?.activation?.session_id || meta?.session_id;
                if (sessId && !cancelled) {
                  setBackendSessionId(sessId);
                  const s = loadSession(activationCode);
                  saveSession({ ...s, sessionId: sessId });
                }
                msgs = mergePendingDraftIntoMessagesFromMeta(
                  mapHistoryToThreadMessages(history, meta),
                  meta as Record<string, unknown>
                );
              } catch {
                /* ignore */
              }
              if (!cancelled && msgs.length === 0) {
                try {
                  const initRes = await apiClient.post('/simple-chat/init', {
                    activation_code: activationCode,
                    phase: BACKEND_PHASE[phase],
                    thread_id: first.id,
                  });
                  const initMsgs: any[] = initRes.data.messages ?? [];
                  const now = Date.now();
                  msgs = initMsgs.map((m, i) => ({
                    id: `init_rum_sync_${now}_${i}`,
                    role: m.role as 'user' | 'assistant',
                    content: m.content ?? '',
                    createdAt: now,
                  }));
                  const sid = initRes.data?.activation?.session_id;
                  if (sid && !cancelled) {
                    setBackendSessionId(String(sid));
                    const s = loadSession(activationCode);
                    saveSession({ ...s, sessionId: String(sid) });
                  }
                } catch {
                  /* ignore */
                }
              }
              const merged: ChatThread = { ...first, messages: msgs };
              setThreadsForPhase(activationCode, phase, [merged]);
              setThreads([merged]);
              setActiveThreadIdState(merged.id);
              setActiveThreadId(activationCode, phase, merged.id);
              setBackendSyncedThreadId(merged.id);
              setMessages(msgs);
              setInitLoading(false);
              return;
            }
            setThreadsForPhase(activationCode, phase, syncedThreads);
            setThreads(syncedThreads);
            setActiveThreadIdState(first.id);
            setActiveThreadId(activationCode, phase, first.id);
            setBackendSyncedThreadId(first.id);
            setMessages([]);
            setInitLoading(false);
            return;
          }

          const historyRes = await apiClient.get('/simple-chat/history', {
            params: { activation_code: activationCode, phase: BACKEND_PHASE[phase] },
          });
          const history: any[] = historyRes.data.messages ?? [];
          const meta = historyRes.data?.metadata ?? {};
          if (typeof meta?.step_locked === 'boolean') {
            setStepLocked(Boolean(meta.step_locked));
          }
          const sessId = historyRes.data?.activation?.session_id || meta?.session_id;
          if (sessId && !cancelled) {
            setBackendSessionId(sessId);
            const s = loadSession(activationCode);
            saveSession({ ...s, sessionId: sessId });
          }
          if (!cancelled && history.length > 0) {
            // 仅用于前端展示历史，不绑定后端 thread_id，避免刷新时误创建新会话
            const recoveredId = getActiveThreadId(activationCode, phase) || `__history_fallback__${phase}`;
            const msgs = mergePendingDraftIntoMessagesFromMeta(
              mapHistoryToThreadMessages(history, meta),
              meta as Record<string, unknown>
            );
            const recoveredThread: ChatThread = {
              id: recoveredId,
              title: '对话 1',
              status: meta.thread_completed ? 'completed' : 'in-progress',
              messages: msgs,
              createdAt: Date.now(),
              dimensionConclusion: (meta.dimension_conclusion as DimensionConclusionData | undefined) || undefined,
            };
            addThread(activationCode, phase, recoveredThread);
            const merged = getThreads(activationCode, phase);
            setThreads(merged);
            setActiveThreadIdState(recoveredId);
            setActiveThreadId(activationCode, phase, recoveredId);
            setBackendSyncedThreadId(null);
            setMessages(msgs);
          } else {
            // 仅首次且无历史时才触发 init 生成首轮问题
            const tid = createThreadId();
            const initRes = await apiClient.post('/simple-chat/init', {
              activation_code: activationCode,
              phase: BACKEND_PHASE[phase],
              thread_id: tid,
            });
            const initMsgs: any[] = initRes.data.messages ?? [];
            const now = Date.now();
            const msgs: ThreadMessage[] = initMsgs.map((m, i) => ({
              id: `init_${i}`,
              role: m.role as 'user' | 'assistant',
              content: m.content ?? '',
              createdAt: now,
            }));
            const thread: ChatThread = {
              id: tid,
              title: '对话 1',
              status: 'in-progress',
              messages: msgs,
              createdAt: Date.now(),
            };
            addThread(activationCode, phase, thread);
            setThreads(getThreads(activationCode, phase));
            setActiveThreadId(activationCode, phase, tid);
            setActiveThreadIdState(tid);
            setBackendSyncedThreadId(tid);
            setMessages(msgs);
          }
        } catch (err: any) {
          if (!cancelled && (err?.code === 'ERR_NETWORK' || err?.message?.includes('Network'))) {
            setChatError(t('explore.chat.networkError'));
          }
        }
        if (!cancelled) setInitLoading(false);
      })();
      return;
    }

    if (activeId) {
      const thread = list.find((t) => t.id === activeId);
      if (thread) {
        // 兜底：若后端线程已存在但消息为空（常见于首次激活被预绑定空会话），
        // 则对该线程补一次 init，确保首轮问题可见。
        if ((thread.messages || []).length === 0) {
          (async () => {
            try {
              const initRes = await apiClient.post('/simple-chat/init', {
                activation_code: activationCode,
                phase: BACKEND_PHASE[phase],
                thread_id: activeId,
              });
              const initMsgs: any[] = initRes.data.messages ?? [];
              const now = Date.now();
              const msgs: ThreadMessage[] = initMsgs.map((m, i) => ({
                id: `init_existing_${now}_${i}`,
                role: m.role as 'user' | 'assistant',
                content: m.content ?? '',
                createdAt: now,
              }));
              if (!cancelled) {
                const mergedThread: ChatThread = { ...thread, messages: msgs };
                saveThread(activationCode, phase, mergedThread);
                setThreads(getThreads(activationCode, phase));
                setMessages(msgs);
                setBackendSyncedThreadId(activeId);
              }
            } catch (err: any) {
              if (!cancelled) {
                setChatError(getApiErrorMessage(err, '初始化失败，请刷新后重试'));
                setMessages(thread.messages || []);
                setBackendSyncedThreadId(activeId);
              }
            } finally {
              if (!cancelled) setInitLoading(false);
            }
          })();
        } else {
          setMessages(thread.messages);
          setBackendSyncedThreadId(activeId);
          setInitLoading(false);
        }
      } else {
        setMessages([]);
        setInitLoading(false);
      }
    } else {
      const first = list[0];
      const firstId = first?.id ?? null;
      setActiveThreadIdState(firstId);
      setActiveThreadId(activationCode, phase, firstId);
      setBackendSyncedThreadId(firstId);
      if (first) setMessages(first.messages);
      setInitLoading(false);
    }

    return () => { cancelled = true; };
  }, [activationCode, phase, threadsFetched, threadListSignature, activeThreadId, mapHistoryToThreadMessages, t]);

  // Persist messages + dimensionConclusion to active (backend-synced) thread when they change
  // 注意：不要在此调用 setThreads(getThreads())，否则会改变 threads 引用并触发上方加载 effect，造成 initLoading 反复与界面闪烁
  useEffect(() => {
    if (!activationCode || !phase || !activeThreadId || initLoading || activeThreadId !== backendSyncedThreadId) return;
    const t = threads.find((x) => x.id === activeThreadId);
    if (t && messages.length > 0) {
      if (t.status === 'completed') return;
      const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
      const toSave: ChatThread = { ...t, messages };
      if (lastConcl?.conclusionData) toSave.dimensionConclusion = lastConcl.conclusionData;
      saveThread(activationCode, phase, toSave);
    }
  }, [messages, activeThreadId, backendSyncedThreadId, initLoading, activationCode, phase, threads]);

  const selectedThread = threads.find((t) => t.id === activeThreadId);
  // 输入锁定规则：1) 从未出现过结论卡 → 可输入；2) 结论卡出现且用户已确认完成 → 锁定；
  // 3) 用户选择「继续完善」后 → 折叠结论卡，可输入
  const isSelectedCompleted = selectedThread?.status === 'completed';
  const isBackendSynced =
    !activeThreadId || !backendSyncedThreadId || activeThreadId === backendSyncedThreadId;
  const hasCollapsedConclusion = messages.some(
    (m) => m.type === 'dimension_conclusion' && m.conclusionCollapsed
  );
  const isReadOnly =
    isSelectedCompleted || // 用户已确认完成，锁定
    (stepLocked && !adminDebugBypass) || // 阶段已锁定，普通用户只读
    (!isBackendSynced && !!activeThreadId); // 切到其它 thread 时暂不输入（未同步）
  const canContinue =
    !!selectedThread && (isSelectedCompleted || (stepLocked && !adminDebugBypass));

  /** 沉淀终步：表格确认后进过渡页；筛选第 7 子步或 final_choice 未完结时隐藏顶栏「完成并继续」 */
  const hideRuminationHeaderComplete =
    phase === 'rumination' &&
    ((!isSelectedCompleted &&
      ruminationProgressState?.main_section === 'final_choice') ||
      ruminationViewStep === RUMINATION_FILTER_STEP_MAX);

  /** 本阶段已提交：普通用户仅可点「完成并继续」，主输入区与侧栏新建等置灰 */
  const phaseInteractionLocked = stepLocked && !adminDebugBypass;

  const showRequestConclusionDraftControl =
    phase !== 'rumination' &&
    !isReadOnly &&
    !phaseInteractionLocked &&
    !!activationCode &&
    !!activeThreadId &&
    !messages.some((m) => m.type === 'dimension_conclusion' && !m.conclusionCollapsed);

  // 与激活页一致：用旅程列表中的 explore_resume 对齐「当前未完成 step」，避免书签/缓存仍停在已提交阶段
  useEffect(() => {
    if (!activationCode || adminDebugBypass || !adminPolicyLoaded) return;
    let cancelled = false;
    void (async () => {
      const resume = await fetchExploreResumeFromJourneys(activationCode);
      if (cancelled || !resume?.resume_phase) return;
      const rp = resume.resume_phase as PhaseKey;
      if (!PHASES.some((p) => p.key === rp)) return;
      const s = loadSession(activationCode);
      const next = applyExploreResumeToSession(s, resume);
      saveSession(next);
      setSession(next);
      if (phase !== rp) {
        router.replace(`/explore/chat/${rp}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activationCode, adminDebugBypass, adminPolicyLoaded, phase, router]);

  const checkScrollPosition = useCallback(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBottom(gap > 80);
    stickToBottomRef.current = gap <= 120;
  }, []);

  /** 进入某阶段 / 切换会话 / 线程列表首次就绪后：立即滚到底部（最新一条） */
  useLayoutEffect(() => {
    if (initLoading || !threadsFetched) return;
    const el = chatBodyRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    stickToBottomRef.current = true;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [phase, activeThreadId, initLoading, threadsFetched, threadListSignature]);

  /** 流式生成中：仅当用户仍在底部附近时才跟随，避免挡住上滑回看 */
  useEffect(() => {
    if (!sending) return;
    if (!stickToBottomRef.current) return;
    const el = chatBodyRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [messages, displayMessages, sending]);

  useEffect(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    el.addEventListener('scroll', checkScrollPosition);
    checkScrollPosition();
    return () => el.removeEventListener('scroll', checkScrollPosition);
  }, [checkScrollPosition, messages]);

  const scrollToBottom = useCallback(() => {
    stickToBottomRef.current = true;
    chatBodyRef.current?.scrollTo({ top: chatBodyRef.current.scrollHeight, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 24 * 7) + 'px';
    ta.style.overflowY = ta.scrollHeight > 24 * 7 ? 'auto' : 'hidden';
  }, [input]);

  // 兜底：避免初始化请求异常时长期停留在“正在准备中”
  useEffect(() => {
    if (!initLoading) return;
    const timer = window.setTimeout(() => {
      setInitLoading(false);
      setChatError((prev) => prev || t('explore.chat.initTimeout'));
    }, 45000);
    return () => window.clearTimeout(timer);
  }, [initLoading, t]);

  useEffect(() => {
    if (phase !== 'rumination') setRuminationTablePayload(null);
  }, [phase]);

  const loadRuminationTableStep = useCallback(
    async (step: number, opts?: { resetInitial?: boolean }): Promise<boolean> => {
      if (!activationCode || phase !== 'rumination') return false;
      if (
        !adminDebugBypass &&
        !isRuminationFilterStepReachable(step, ruminationProgressState)
      ) {
        return false;
      }
      setRuminationTableNavLoading(true);
      try {
        setChatError(null);
        const res = await ruminationApi.getTable(activationCode, step, {
          resetInitial: opts?.resetInitial,
        });
        if (res.code !== 200) {
          setChatError(res.message || t('explore.chat.ruminationTableLoadError'));
          return false;
        }
        const p = res.data?.progress;
        const mr = res.data?.max_reached_filter_step;
        if (p) setRuminationProgressState(p);
        if (typeof mr === 'number') setRuminationMaxReached(mr);
        else if (p) setRuminationMaxReached(computeMaxReachedFromSnapshots(p));
        const w = res.data?.table_widget;
        if (w) {
          const stepKey = String(w.step ?? step);
          const lenAtApply = messagesRef.current.length;
          setRuminationTablePayload(w as ThreadMessage['tablePayload']);
          setRuminationViewStep(w.step ?? step);
          setRuminationStepBoundaries((b) => {
            if (b[stepKey] !== undefined) return b;
            const nb = { ...b, [stepKey]: lenAtApply };
            if (activationCode && activeThreadId) {
              saveRuminationStepBoundaries(activationCode, activeThreadId, nb);
            }
            return nb;
          });
          return true;
        }
        setChatError(
          opts?.resetInitial
            ? t('explore.chat.ruminationTableRefillEmpty')
            : t('explore.chat.ruminationTableMissing')
        );
        return false;
      } catch {
        setChatError(t('explore.chat.ruminationTableLoadError'));
        return false;
      } finally {
        setRuminationTableNavLoading(false);
      }
    },
    [
      activationCode,
      activeThreadId,
      adminDebugBypass,
      phase,
      ruminationProgressState,
      t,
    ]
  );

  /**
   * 沉淀：单次 GET rumination-progress 更新进度与 max_reached；必要时再 GET get-table 补左栏表。
   * 原实现拆成两个 effect 会对同一接口连打多次；标题区 RuminationSectionProgress 已 externalProgressOnly，不再重复请求。
   *
   * 注意：不把 activeThreadId 列入依赖，避免切换/校正线程时误取消进行中的请求；边界保存用 activeThreadIdRef。
   * threadsFetched 与 initLoading 齐平后再拉表，避免与线程初始化竞态。
   * filter_step 与快照不一致时 get-table 可能返回空 widget，此时回退拉第 1 步表。
   */
  useEffect(() => {
    if (
      phase !== 'rumination' ||
      !activationCode ||
      initLoading ||
      !threadsFetched
    ) {
      return;
    }
    let cancelled = false;
    (async () => {
      type ApplyResult = 'ok' | 'error' | 'empty';
      const applyTableResponse = (
        tb: Awaited<ReturnType<typeof ruminationApi.getTable>>,
        defaultStep: number
      ): ApplyResult => {
        if (cancelled) return 'ok';
        if (tb.code !== 200) {
          setChatError(tb.message || t('explore.chat.ruminationTableLoadError'));
          return 'error';
        }
        const w = tb.data?.table_widget;
        if (!w) return 'empty';
        if (tb.data?.progress) setRuminationProgressState(tb.data.progress);
        if (typeof tb.data?.max_reached_filter_step === 'number') {
          setRuminationMaxReached(tb.data.max_reached_filter_step);
        } else if (tb.data?.progress) {
          setRuminationMaxReached(computeMaxReachedFromSnapshots(tb.data.progress));
        }
        const stepKey = String(w.step ?? defaultStep);
        const lenAtApply = messagesRef.current.length;
        setRuminationTablePayload(w as ThreadMessage['tablePayload']);
        if (w.step != null) setRuminationViewStep(w.step);
        setRuminationStepBoundaries((b) => {
          if (b[stepKey] !== undefined) return b;
          const nb = { ...b, [stepKey]: lenAtApply };
          const tid = activeThreadIdRef.current;
          if (activationCode && tid) {
            saveRuminationStepBoundaries(activationCode, tid, nb);
          }
          return nb;
        });
        return 'ok';
      };

      try {
        const res = await ruminationApi.get(activationCode);
        if (cancelled) return;
        if (res.code !== 200) {
          setChatError(res.message || t('explore.chat.ruminationTableLoadError'));
          return;
        }
        const p = res.data?.progress;
        if (!p) {
          setChatError(t('explore.chat.ruminationTableLoadError'));
          return;
        }
        const mr =
          res.data?.max_reached_filter_step ?? computeMaxReachedFromSnapshots(p);
        setRuminationProgressState(p);
        setRuminationMaxReached(mr);

        /** 终态不再自动拉表；final_choice 下普通用户用结论卡，管理员走 adminFilterTableAfterDone */
        const terminalNoTable = ['recommend', 'end'];
        const userFilterTableFlow =
          !terminalNoTable.includes(p.main_section ?? '') &&
          p.main_section !== 'final_choice' &&
          ((p.filter_step ?? 0) > 0 ||
            p.main_section === 'opening' ||
            p.main_section === 'review' ||
            (p.main_section === 'filter' && (p.filter_step ?? 0) === 0));
        /** 管理员在筛选表提交进入 final_choice 后仍应能加载左栏表做调试 */
        const adminFilterTableAfterDone =
          adminDebugBypass && p.main_section === 'final_choice';
        if (!userFilterTableFlow && !adminFilterTableAfterDone) {
          return;
        }

        setChatError(null);
        /** 历史里可能仍有旧 table_widget；不能以「消息里有没有表」跳过 getTable，否则会永远停在错误子步 */
        const stepToLoad = Math.min(
          RUMINATION_FILTER_STEP_MAX,
          Math.max(1, p.filter_step || 1)
        );
        setRuminationViewStep(stepToLoad);

        let tb = await ruminationApi.getTable(activationCode, stepToLoad);
        if (cancelled) return;

        let r = applyTableResponse(tb, stepToLoad);
        if (r === 'empty' && stepToLoad !== 1) {
          tb = await ruminationApi.getTable(activationCode, 1);
          if (cancelled) return;
          r = applyTableResponse(tb, 1);
        }
        if (r === 'empty') {
          setChatError(t('explore.chat.ruminationTableMissing'));
        }
      } catch {
        if (!cancelled) {
          setChatError(t('explore.chat.ruminationTableLoadError'));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    phase,
    activationCode,
    initLoading,
    threadsFetched,
    ruminationProgressNonce,
    adminDebugBypass,
    t,
  ]);

  const handleRequestConclusionDraft = useCallback(async () => {
    if (
      !activationCode ||
      !activeThreadId ||
      phase === 'rumination' ||
      requestConclusionDraftBusy
    ) {
      return;
    }
    setRequestConclusionDraftBusy(true);
    setChatError(null);
    try {
      const res = await apiClient.post<{ draft: DimensionConclusionData }>(
        '/simple-chat/conclusion-draft/request',
        {
          activation_code: activationCode,
          phase: BACKEND_PHASE[phase],
          thread_id: activeThreadId,
        }
      );
      const draft = res.data?.draft;
      if (draft) {
        setMessages((prev) => {
          const lastIdx = [...prev].map((x) => x.type).lastIndexOf('dimension_conclusion');
          if (lastIdx >= 0) {
            const next = [...prev];
            next[lastIdx] = {
              ...next[lastIdx],
              conclusionData: draft,
              createdAt: Date.now(),
              conclusionCollapsed: false,
              conclusionConfirmed: false,
            };
            return next;
          }
          return [
            ...prev,
            {
              id: `concl_${Date.now()}`,
              role: 'assistant',
              content: '',
              type: 'dimension_conclusion',
              conclusionData: draft,
              conclusionCollapsed: false,
              conclusionConfirmed: false,
              createdAt: Date.now(),
            },
          ];
        });
      }
    } catch (e: unknown) {
      setChatError(getApiErrorMessage(e, t('explore.chat.requestConclusionDraftFail')));
    } finally {
      setRequestConclusionDraftBusy(false);
    }
  }, [
    activationCode,
    activeThreadId,
    phase,
    requestConclusionDraftBusy,
    t,
  ]);

  const handleSend = async (
    prefill?: string,
    skipAddUser?: boolean,
    /** 重新生成时沿用原用户消息的表格行摘要（避免闭包读到旧 messages） */
    regenerateRowLabel?: string
  ) => {
    const text = prefill ?? input.trim();
    if (!activationCode || !text || sending || ruminationGuideBusy || isReadOnly) return;
    if (phase === 'rumination' && ruminationTableNavLoading) return;
    if (!prefill) setInput('');
    const now = Date.now();
    const rowSnap =
      phase === 'rumination'
        ? skipAddUser
          ? regenerateRowLabel != null && regenerateRowLabel !== ''
            ? { label: regenerateRowLabel }
            : null
          : ruminationRowContext
        : null;
    const messageForApi =
      phase === 'rumination' && rowSnap
        ? `${t('explore.chat.ruminationUi.messageRowContextPrefix', { label: rowSnap.label })}\n\n${text}`
        : text;
    const userMsg: ThreadMessage = {
      id: `u_${now}`,
      role: 'user',
      content: text,
      createdAt: now,
      ...(rowSnap ? { ruminationRowLabel: rowSnap.label } : {}),
    };
    const assistantId = `a_${now}`;
    const toAdd = skipAddUser
      ? [{ id: assistantId, role: 'assistant' as const, content: '', createdAt: now }]
      : [userMsg, { id: assistantId, role: 'assistant' as const, content: '', createdAt: now }];
    setMessages((prev) => [...prev, ...toAdd]);
    setChatError(null);
    setConclusionLoading(false);
    setSending(true);
    stickToBottomRef.current = true;

    const controller = new AbortController();
    abortControllerRef.current = controller;
    let assistantHasVisibleOutput = false;
    try {
      const apiBase = (process.env.NEXT_PUBLIC_API_URL || '').trim();
      const streamUrl = `${apiBase ? apiBase.replace(/\/+$/, '') : ''}/api/v1/simple-chat/message/stream`;
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      const effectiveThreadId =
        activeThreadId && backendSyncedThreadId && activeThreadId === backendSyncedThreadId
          ? activeThreadId
          : undefined;
      const doStreamFetch = async (accessToken: string | null) =>
        fetch(streamUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify({
            activation_code: activationCode,
            message: messageForApi,
            phase: BACKEND_PHASE[phase],
            thread_id: effectiveThreadId,
          }),
          signal: controller.signal,
        });

      let res = await doStreamFetch(token);
      if (res.status === 401) {
        try {
          const refreshed = await authApi.refresh();
          const nextToken = refreshed?.data?.token || null;
          if (nextToken) {
            apiClient.setToken(nextToken);
            setTokens(nextToken);
            res = await doStreamFetch(nextToken);
          }
        } catch {
          // refresh 失败后继续走统一 401 提示
        }
      }

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error(t('explore.chat.streamAuthExpired'));
        }
        let detail = '';
        try {
          const errPayload = await res.json();
          detail = errPayload?.detail || errPayload?.message || '';
        } catch {}
        throw new Error(detail || `请求失败（${res.status}）`);
      }
      if (!res.body) throw new Error('流式接口返回为空');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullReply = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.error) {
              setChatError(String(payload.error));
              reader.cancel();
              break;
            }
            if (payload.think_start) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, thinkStreaming: true, thinkChunkContent: '' } : m
                )
              );
            }
            if (payload.think_chunk) {
              const chunk = typeof payload.think_chunk === 'string' ? payload.think_chunk : '';
              if (chunk) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, thinkChunkContent: chunk }
                      : m
                  )
                );
              }
            }
            if (payload.think_end != null) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, thinkStreaming: false, thinkChunkContent: undefined }
                    : m
                )
              );
            }
            if (payload.chunk) {
              fullReply += payload.chunk;
              if (String(payload.chunk || '').trim()) assistantHasVisibleOutput = true;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: (m.content || '') + payload.chunk } : m
                )
              );
            }
            if (payload.conclusion_loading) {
              setConclusionLoading(true);
            }
            if (payload.dimension_conclusion) {
              assistantHasVisibleOutput = true;
              setConclusionLoading(false);
              const concl = payload.dimension_conclusion as DimensionConclusionData;
              const conclMsg: ThreadMessage = {
                id: `concl_${Date.now()}`,
                role: 'assistant',
                content: '',
                type: 'dimension_conclusion',
                conclusionData: concl,
                conclusionCollapsed: false,
                conclusionConfirmed: false,
                createdAt: Date.now(),
              };
              // pending 草案已有一张卡时，确认流会再次推送：替换同一张，避免双卡
              setMessages((prev) => {
                const lastIdx = [...prev].map((x) => x.type).lastIndexOf('dimension_conclusion');
                if (lastIdx >= 0) {
                  const next = [...prev];
                  next[lastIdx] = { ...next[lastIdx], conclusionData: concl, createdAt: Date.now() };
                  return next;
                }
                return [...prev, conclMsg];
              });
            }
            if (payload.table_widget) {
              assistantHasVisibleOutput = true;
              const tw = payload.table_widget as ThreadMessage['tablePayload'];
              if (phase === 'rumination') {
                setRuminationTablePayload(tw ?? null);
              } else {
                const tableMsg: ThreadMessage = {
                  id: `table_${Date.now()}`,
                  role: 'assistant',
                  content: '',
                  type: 'table_widget',
                  tablePayload: tw ?? undefined,
                  createdAt: Date.now(),
                };
                setMessages((prev) => [...prev, tableMsg]);
              }
            }
            if (payload.done && payload.response != null) {
              fullReply = payload.response;
              if (String(payload.response || '').trim()) assistantHasVisibleOutput = true;
              const doneAt = Date.now();
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content: fullReply,
                        thinkStreaming: false,
                        thinkChunkContent: undefined,
                        thinkContent: undefined,
                        createdAt: m.createdAt ?? doneAt,
                      }
                    : m
                )
              );
              break;
            }
          } catch {}
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') setChatError(err?.message || '发送失败，请重试');
    } finally {
      setSending(false);
      setConclusionLoading(false);
      setMessages((prev) => {
        const normalized = prev.map((m) =>
          m.id === assistantId && m.thinkStreaming
            ? { ...m, thinkStreaming: false, thinkChunkContent: undefined }
            : m
        );
        // 避免后端失败时遗留空 assistant 气泡
        if (!assistantHasVisibleOutput) {
          return normalized.filter(
            (m) =>
              !(
                m.id === assistantId &&
                !(m.content || '').trim() &&
                !m.thinkContent &&
                !m.thinkChunkContent
              )
          );
        }
        return normalized;
      });
      abortControllerRef.current = null;
      // 发送完成后将焦点还给输入框，支持连续 Enter 对话无需再点鼠标。
      requestAnimationFrame(() => {
        if (!isReadOnly) inputRef.current?.focus();
      });
    }
  };

  const performThreadSwitch = useCallback(
    (
      targetThread: ChatThread,
      opts?: { messagesSnapshot?: ThreadMessage[]; threadsSnapshot?: ChatThread[] }
    ) => {
      if (!activationCode || !phase) return;
      const msgs = opts?.messagesSnapshot ?? messages;
      let list: ChatThread[] = opts?.threadsSnapshot ?? threads;
      const leavingId = activeThreadId;

      if (leavingId && leavingId !== targetThread.id) {
        const prev = list.find((x) => x.id === leavingId);
        if (prev && prev.status !== 'completed' && msgs.length > 0) {
          const lastConcl = msgs.filter((m) => m.type === 'dimension_conclusion').pop();
          const updated: ChatThread = { ...prev, messages: msgs };
          if (lastConcl?.conclusionData) updated.dimensionConclusion = lastConcl.conclusionData;
          saveThread(activationCode, phase, updated);
          list = list.map((t) => (t.id === leavingId ? updated : t));
        }
        abortControllerRef.current?.abort();
        ruminationGuideAbortRef.current?.abort();
      }

      const resolved = list.find((t) => t.id === targetThread.id) ?? targetThread;
      setThreads(list);
      setActiveThreadId(activationCode, phase, targetThread.id);
      setActiveThreadIdState(targetThread.id);
      setMessages(resolved.messages);
      setBackendSyncedThreadId(targetThread.id);
    },
    [activationCode, phase, activeThreadId, threads, messages]
  );

  const handleSelectThread = useCallback(
    (thread: ChatThread) => {
      if (!activationCode || !phase) return;
      if (thread.id === activeThreadId) return;
      if (sending || ruminationGuideBusy) {
        setPendingSwitchThread(thread);
        setThreadSwitchDialogOpen(true);
        return;
      }
      performThreadSwitch(thread);
    },
    [activationCode, phase, activeThreadId, sending, ruminationGuideBusy, performThreadSwitch]
  );

  const handleCancelThreadSwitchWhileStreaming = useCallback(() => {
    setThreadSwitchDialogOpen(false);
    setPendingSwitchThread(null);
  }, []);

  const handleConfirmThreadSwitchWhileStreaming = useCallback(() => {
    if (!pendingSwitchThread || !activationCode || !phase) {
      setThreadSwitchDialogOpen(false);
      setPendingSwitchThread(null);
      return;
    }
    const target = pendingSwitchThread;
    const snapMessages = messages;
    const snapThreads = threads;
    abortControllerRef.current?.abort();
    ruminationGuideAbortRef.current?.abort();
    performThreadSwitch(target, {
      messagesSnapshot: snapMessages,
      threadsSnapshot: snapThreads,
    });
    setThreadSwitchDialogOpen(false);
    setPendingSwitchThread(null);
  }, [pendingSwitchThread, activationCode, phase, messages, threads, performThreadSwitch]);

  const handleNewChat = async () => {
    if (!activationCode || !phase) return;
    if (phase === 'rumination') return;
    if (stepLocked && !adminDebugBypass) return;
    const list = getThreads(activationCode, phase);
    if (!adminDebugBypass && list.length >= 5) return;

    // Save current thread if has messages
    if (selectedThread && messages.length > 0) {
      saveThread(activationCode, phase, { ...selectedThread, messages });
    }

    setInitLoading(true);
    const tid = createThreadId();
    try {
      const initRes = await apiClient.post('/simple-chat/init', {
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: tid,
      });
      const initMsgs: any[] = initRes.data.messages ?? [];
      const now = Date.now();
      const msgs: ThreadMessage[] = initMsgs.map((m, i) => ({
        id: `init_${now}_${i}`,
        role: m.role as 'user' | 'assistant',
        content: m.content ?? '',
        createdAt: now,
      }));
      const thread: ChatThread = {
        id: tid,
        title: `对话 ${list.length + 1}`,
        status: 'in-progress',
        messages: msgs,
        createdAt: Date.now(),
      };
      addThread(activationCode, phase, thread);
      setActiveThreadId(activationCode, phase, tid);
      setBackendSyncedThreadId(tid);
      setThreads(getThreads(activationCode, phase));
      setActiveThreadIdState(tid);
      setMessages(msgs);
    } catch {}
    setInitLoading(false);
  };

  const handleConfirmConclusion = async () => {
    if (!activationCode || !phase) return;
    const targetThreadId = activeThreadId || backendSyncedThreadId;
    if (!targetThreadId) return;
    const th = threads.find((t) => t.id === targetThreadId) || selectedThread;
    if (!th) return;
    const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
    if (!lastConcl?.conclusionData) return;
    try {
      await apiClient.post('/simple-chat/thread/complete', {
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: targetThreadId,
      });
    } catch (e) {
      console.warn('thread/complete API failed:', e);
    }
    const confirmedMessages = messages.map((m) =>
      m.type === 'dimension_conclusion'
        ? { ...m, conclusionConfirmed: true, conclusionCollapsed: false }
        : m
    );
    setMessages(confirmedMessages);
    const updated: ChatThread = {
      ...th,
      status: 'completed',
      messages: confirmedMessages,
      dimensionConclusion: lastConcl.conclusionData,
    };
    saveThread(activationCode, phase, updated);
    // 使用 functional update 直接更新 state，避免依赖 getThreads 被 persist effect 覆盖
    setThreads((prev) => {
      const idx = prev.findIndex((t) => t.id === targetThreadId);
      if (idx < 0) return [...prev, updated];
      return prev.map((t) => (t.id === targetThreadId ? updated : t));
    });

    if (phase === 'rumination' && activationCode && session) {
      const nextSession = unlockNextPhase({ ...session, currentPhase: phase });
      saveSession(nextSession);
      setSession(nextSession);
      router.push('/explore/transition?from=rumination');
    }
  };

  /** 终步表格在弹窗确认后提交，并进过渡页（无结论卡） */
  const handleRuminationStep7FinalizeConfirmed = useCallback(async () => {
    const p = pendingStep7SubmitRef.current;
    if (!p || !activationCode || phase !== 'rumination') return;
    setRuminationStep7FinalizeOpen(false);
    pendingStep7SubmitRef.current = null;
    setRuminationTableSubmitting(true);
    setChatError(null);
    try {
      const res = await ruminationApi.submitTable(
        activationCode,
        p.submitThreadId,
        RUMINATION_FILTER_STEP_MAX,
        p.rows,
        { mode: 'full_step' }
      );
      if (res.code !== 200) {
        setChatError(res.message || t('explore.chat.ruminationUi.tableSubmitError'));
        return;
      }
      const data = res.data as RuminationSubmitData | undefined;
      if (data?.early_terminated || data?.next_action === 'early_terminated') {
        setChatError(t('explore.chat.ruminationUi.tableEarlyTerminated'));
        return;
      }
      if (data?.next_action !== 'rumination_finalize_transition') {
        if (data?.progress) setRuminationProgressState(data.progress);
        if (typeof data?.max_reached_filter_step === 'number') {
          setRuminationMaxReached(data.max_reached_filter_step);
        } else if (data?.progress) {
          setRuminationMaxReached(computeMaxReachedFromSnapshots(data.progress));
        }
        setChatError(t('explore.chat.ruminationUi.tableSubmitError'));
        return;
      }
      /** 不在进过渡页前更新进度条 state：否则 main_section 变为 final_choice 时会闪一帧约 82% */
      const targetThreadId = p.submitThreadId;
      const th = threads.find((t) => t.id === targetThreadId) || selectedThread;
      try {
        await apiClient.post('/simple-chat/thread/complete', {
          activation_code: activationCode,
          phase: BACKEND_PHASE[phase],
          thread_id: targetThreadId,
        });
      } catch (e) {
        console.warn('thread/complete API failed:', e);
      }
      if (th) {
        const updated: ChatThread = {
          ...th,
          status: 'completed',
          messages,
        };
        saveThread(activationCode, phase, updated);
        setThreads((prev) => {
          const idx = prev.findIndex((t) => t.id === targetThreadId);
          if (idx < 0) return [...prev, updated];
          return prev.map((t) => (t.id === targetThreadId ? updated : t));
        });
      }
      if (session) {
        const nextSession = unlockNextPhase({ ...session, currentPhase: phase });
        saveSession(nextSession);
        setSession(nextSession);
      }
      router.push('/explore/transition?from=rumination');
    } catch (err) {
      setChatError(getApiErrorMessage(err, t('explore.chat.ruminationUi.tableSubmitError')));
    } finally {
      setRuminationTableSubmitting(false);
    }
  }, [
    activationCode,
    phase,
    messages,
    router,
    session,
    setChatError,
    setRuminationMaxReached,
    setRuminationProgressNonce,
    setRuminationProgressState,
    setRuminationTablePayload,
    setRuminationViewStep,
    setSession,
    setThreads,
    t,
    threads,
    selectedThread,
  ]);

  const handleContinueChat = async (conclusionMsg?: ThreadMessage) => {
    const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
    const toCollapse = conclusionMsg ?? lastConcl;
    if (toCollapse && toCollapse.type === 'dimension_conclusion') {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === toCollapse.id ? { ...m, conclusionCollapsed: true, conclusionConfirmed: false } : m
        )
      );
    }
    if (activationCode && phase && activeThreadId) {
      try {
        await apiClient.post('/simple-chat/thread/reopen', {
          activation_code: activationCode,
          phase: BACKEND_PHASE[phase],
          thread_id: activeThreadId,
        });
      } catch (err: any) {
        if (err?.response?.status === 401 || err?.message?.includes('401')) {
          setChatError(t('explore.chat.tokenExpired') || '登录已失效，请重新登录后刷新页面');
          return;
        }
        if (err?.response?.status === 400) {
          setChatError(getApiErrorMessage(err, '无法继续对话，请刷新页面后重试'));
          return;
        }
        setChatError(getApiErrorMessage(err, '网络异常，请稍后重试'));
        return;
      }
      if (selectedThread) {
        const updated: ChatThread = { ...selectedThread, status: 'in-progress' };
        saveThread(activationCode, phase, updated);
        setThreads(getThreads(activationCode, phase));
      }
    }
  };

  const handleCompleteAndContinue = () => {
    if (!activationCode || !session || !canContinue) return;
    const updated = unlockNextPhase({ ...session, currentPhase: phase });
    saveSession(updated);
    setSession(updated);
    router.push(`/explore/transition?from=${phase}`);
  };

  const handleDeleteThread = (thread: ChatThread) => {
    if (!activationCode || !phase) return;
    if (stepLocked && !adminDebugBypass) return;
    void (async () => {
      try {
        await apiClient.post('/simple-chat/thread/delete', {
          activation_code: activationCode,
          phase: BACKEND_PHASE[phase],
          thread_id: thread.id,
        });
      } catch (err: any) {
        setChatError(getApiErrorMessage(err, '删除失败，请稍后重试'));
        return;
      }
      const list = removeThread(activationCode, phase, thread.id);
      setThreads(list);
      if (thread.id === activeThreadId) {
        if (list.length > 0) {
          const next = list[0];
          setActiveThreadIdState(next.id);
          setActiveThreadId(activationCode, phase, next.id);
          setMessages(next.messages);
          setBackendSyncedThreadId(next.id);
        } else {
          setActiveThreadIdState(null);
          setMessages([]);
          setBackendSyncedThreadId(null);
          // A 方案：不在删除回调里主动创建，统一交给「list.length===0」初始化 effect 处理，
          // 避免删除后与 effect 同时触发造成重复创建会话。
        }
      }
    })();
  };

  const handleStopStream = () => {
    abortControllerRef.current?.abort();
    ruminationGuideAbortRef.current?.abort();
  };

  /** 沉淀表格提交依赖后端 thread_id；历史恢复占位 id 或竞态时需回退到真实会话 id */
  const resolveRuminationTableThreadId = useCallback((): string => {
    if (activeThreadId && !activeThreadId.startsWith('__history_fallback__')) {
      return activeThreadId;
    }
    if (backendSyncedThreadId) return backendSyncedThreadId;
    const fid = threads[0]?.id;
    if (fid && !fid.startsWith('__history_fallback__')) return fid;
    return activeThreadId || '';
  }, [activeThreadId, backendSyncedThreadId, threads]);

  /** 表格确认成功后：拉取子步引导配置，固定文案前端模拟流式，LLM 走专用流式接口 */
  const playRuminationStepOpeningAfterSubmit = useCallback(
    async (newStep: number, threadId: string) => {
      if (!activationCode || phase !== 'rumination') return;
      ruminationGuideAbortRef.current?.abort();
      const ac = new AbortController();
      ruminationGuideAbortRef.current = ac;
      const assistantId = `rum_open_${Date.now()}_${newStep}`;
      let assistantHasVisibleOutput = false;

      let openingRes;
      try {
        openingRes = await ruminationApi.getStepOpening(activationCode, newStep);
      } catch {
        return;
      }
      if (openingRes.code !== 200 || !openingRes.data) return;

      const cfg = openingRes.data;
      const shouldStreamLlm = cfg.mode === 'llm';
      const fixedText = cfg.mode === 'fixed' ? (cfg.text || '').trim() : '';
      if (!shouldStreamLlm && !fixedText) return;

      const now = Date.now();
      setRuminationGuideBusy(true);
      setMessages((prev) => [
        ...prev,
        { id: assistantId, role: 'assistant', content: '', createdAt: now },
      ]);

      try {
        if (cfg.mode === 'fixed' && fixedText) {
          assistantHasVisibleOutput = true;
          await simulateFixedRuminationOpening(fixedText, ac.signal, (acc) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: acc } : m))
            );
          });
        } else if (shouldStreamLlm) {
          await streamRuminationStepOpening(
            activationCode,
            newStep,
            threadId,
            ac.signal,
            {
              onChunk: (delta) => {
                if (String(delta).trim()) assistantHasVisibleOutput = true;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: (m.content || '') + delta } : m
                  )
                );
              },
              onThinkStart: () => {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, thinkStreaming: true, thinkChunkContent: '' }
                      : m
                  )
                );
              },
              onThinkChunk: (chunk) => {
                if (chunk) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId ? { ...m, thinkChunkContent: chunk } : m
                    )
                  );
                }
              },
              onThinkEnd: () => {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, thinkStreaming: false, thinkChunkContent: undefined }
                      : m
                  )
                );
              },
              onDone: (full) => {
                const trimmed = (full || '').trim();
                if (trimmed) assistantHasVisibleOutput = true;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          content: trimmed || m.content,
                          thinkStreaming: false,
                          thinkChunkContent: undefined,
                        }
                      : m
                  )
                );
              },
              onError: (msg) => setChatError(msg),
            },
            t('explore.chat.streamAuthExpired')
          );
        }
      } catch (e: unknown) {
        const err = e as { name?: string; message?: string };
        if (err?.name !== 'AbortError') {
          setChatError(err?.message || t('explore.chat.ruminationUi.openingGuideError'));
        }
      } finally {
        setRuminationGuideBusy(false);
        ruminationGuideAbortRef.current = null;
        if (!assistantHasVisibleOutput) {
          setMessages((prev) => prev.filter((m) => m.id !== assistantId));
        } else {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && m.thinkStreaming
                ? { ...m, thinkStreaming: false, thinkChunkContent: undefined }
                : m
            )
          );
        }
      }
    },
    [activationCode, phase, setChatError, setMessages, t]
  );

  const handleTableConfirm = useCallback(
    async (
      _msgId: string,
      payload: NonNullable<ThreadMessage['tablePayload']>,
      rows: Record<string, unknown>[]
    ) => {
      if (!activationCode || phase !== 'rumination' || sending || ruminationGuideBusy) return;
      const submitThreadId = resolveRuminationTableThreadId();
      if (!submitThreadId.trim()) {
        setChatError(t('explore.chat.ruminationUi.tableSubmitNoThread'));
        return;
      }
      const rawStep = payload.step;
      /** 以 payload 为准；缺失时回退当前查看子步，避免闭包/竞态导致误按第 1 步提交 */
      const stepNum =
        typeof rawStep === 'number' &&
        rawStep >= 1 &&
        rawStep <= RUMINATION_FILTER_STEP_MAX
          ? rawStep
          : Math.min(RUMINATION_FILTER_STEP_MAX, Math.max(1, ruminationViewStep || 1));
      if (stepNum === RUMINATION_FILTER_STEP_MAX) {
        pendingStep7SubmitRef.current = { rows, payload, submitThreadId };
        setChatError(null);
        setRuminationStep7FinalizeOpen(true);
        return;
      }
      setRuminationTableSubmitting(true);
      try {
        /** 必须始终传完整 table_data：后端 RuminationTableSubmitRequest 未实现 single_row/patch，
         * 若 single 行模式传 null，服务端不会进入任一步的递进分支，表现为「确认后卡住不前进」。 */
        const res = await ruminationApi.submitTable(
          activationCode,
          submitThreadId,
          stepNum,
          rows,
          { mode: 'full_step' }
        );
        if (res.code !== 200) {
          setChatError(res.message || t('explore.chat.ruminationUi.tableSubmitError'));
          return;
        }
        const data = res.data as RuminationSubmitData | undefined;
        if (data?.early_terminated || data?.next_action === 'early_terminated') {
          setChatError(t('explore.chat.ruminationUi.tableEarlyTerminated'));
          return;
        }
        const nextTable = data?.next_table_widget;
        if (data?.progress) setRuminationProgressState(data.progress);
        if (typeof data?.max_reached_filter_step === 'number') {
          setRuminationMaxReached(data.max_reached_filter_step);
        }
        if (data?.next_action === 'rumination_conclusion_insert' && data.dimension_conclusion) {
          const concl = data.dimension_conclusion as DimensionConclusionData;
          const newId = `rumination_concl_${Date.now()}`;
          setMessages((prev) => {
            const filtered = prev.filter((m) => m.type !== 'table_widget');
            const boundarySnap = filtered.length;
            queueMicrotask(() => {
              setRuminationStepBoundaries((b) => {
                const nb = ensureDefaultStepOne({
                  ...b,
                  [String(RUMINATION_FILTER_STEP_MAX)]: boundarySnap,
                });
                if (activationCode && submitThreadId) {
                  saveRuminationStepBoundaries(activationCode, submitThreadId, nb);
                }
                return nb;
              });
            });
            return [
              ...filtered,
              {
                id: newId,
                role: 'assistant',
                type: 'dimension_conclusion',
                content: JSON.stringify(concl),
                createdAt: Date.now(),
                conclusionData: concl,
                conclusionCollapsed: false,
                conclusionConfirmed: false,
              },
            ];
          });
          setRuminationTablePayload(null);
          setRuminationViewStep(RUMINATION_FILTER_STEP_MAX);
          if (data.progress) setRuminationProgressState(data.progress);
          if (typeof data?.max_reached_filter_step === 'number') {
            setRuminationMaxReached(data.max_reached_filter_step);
          }
          setRuminationProgressNonce((n) => n + 1);
          return;
        }
        if (nextTable) {
          const newStep = nextTable.step ?? (payload.step ?? 1) + 1;
          const filtered = messages.filter((m) => m.type !== 'table_widget');
          setRuminationStepBoundaries((b) => {
            const nb = ensureDefaultStepOne({ ...b, [String(newStep)]: filtered.length });
            if (activationCode && submitThreadId) {
              saveRuminationStepBoundaries(activationCode, submitThreadId, nb);
            }
            return nb;
          });
          setRuminationTablePayload(nextTable as ThreadMessage['tablePayload']);
          setRuminationViewStep(newStep);
          setMessages(filtered);
          queueMicrotask(() => {
            void playRuminationStepOpeningAfterSubmit(newStep, submitThreadId);
          });
        } else if (data?.progress?.filter_step != null && data.progress.filter_step >= 1) {
          setRuminationViewStep(
            Math.min(RUMINATION_FILTER_STEP_MAX, Math.max(1, data.progress.filter_step))
          );
        }
        setRuminationProgressNonce((n) => n + 1);
      } catch (err) {
        setChatError(getApiErrorMessage(err, t('explore.chat.ruminationUi.tableSubmitError')));
      } finally {
        setRuminationTableSubmitting(false);
      }
    },
    [
      activationCode,
      phase,
      sending,
      messages,
      router,
      adminDebugBypass,
      resolveRuminationTableThreadId,
      ruminationViewStep,
      ruminationGuideBusy,
      playRuminationStepOpeningAfterSubmit,
      t,
    ]
  );

  const ruminationStepHasSubmitted = useMemo(() => {
    const k = String(ruminationViewStep);
    const ent = ruminationProgressState?.filter_step_snapshots?.[k];
    return ent != null && ent.submitted != null;
  }, [ruminationViewStep, ruminationProgressState]);

  const handleRuminationFilterPrev = useCallback(() => {
    if (
      ruminationViewStep <= 1 ||
      ruminationGuideBusy ||
      ruminationTableNavLoading ||
      hypothesisRegeneratingRowIndex !== null
    ) {
      return;
    }
    let t = ruminationViewStep - 1;
    while (t >= 1 && !isRuminationFilterStepReachable(t, ruminationProgressState)) {
      t -= 1;
    }
    if (t < 1) return;
    void loadRuminationTableStep(t);
  }, [
    ruminationViewStep,
    ruminationProgressState,
    loadRuminationTableStep,
    ruminationGuideBusy,
    ruminationTableNavLoading,
    hypothesisRegeneratingRowIndex,
  ]);

  const handleRuminationFilterNext = useCallback(() => {
    if (
      ruminationGuideBusy ||
      ruminationTableNavLoading ||
      hypothesisRegeneratingRowIndex !== null
    ) {
      return;
    }
    const next = ruminationViewStep + 1;
    if (next > RUMINATION_FILTER_STEP_MAX) return;
    if (!isRuminationFilterStepReachable(next, ruminationProgressState)) return;
    void loadRuminationTableStep(next);
  }, [
    ruminationViewStep,
    ruminationProgressState,
    loadRuminationTableStep,
    ruminationGuideBusy,
    ruminationTableNavLoading,
    hypothesisRegeneratingRowIndex,
  ]);

  const handleHypothesisRegenerateRow = useCallback(
    async (
      rowIdx: number,
      rowId: string,
      liveRowsFromWidget?: Record<string, unknown>[]
    ) => {
      if (!activationCode || phase !== 'rumination') return;
      const filterStep = ruminationTablePayload?.step ?? ruminationViewStep;
      if (filterStep !== 3) return;
      setHypothesisRegeneratingRowIndex(rowIdx);
      setChatError(null);
      try {
        const res = await ruminationApi.regenerateHypotheses(activationCode, filterStep, rowId);
        const rawTw = res.data?.table_widget;
        if (res.code !== 200 || !rawTw) {
          setChatError(
            res.message || t('explore.chat.ruminationUi.hypothesisRegenerateError')
          );
          return;
        }
        const tw = rawTw as NonNullable<ThreadMessage['tablePayload']>;
        const pendingLabel = t('explore.chat.ruminationUi.hypothesisPendingOption');
        const payloadRows = (ruminationTablePayload?.rows ?? []) as Record<string, unknown>[];
        const prevRows =
          liveRowsFromWidget && liveRowsFromWidget.length > 0
            ? liveRowsFromWidget
            : payloadRows;
        const prevRow = prevRows[rowIdx];
        let nextPayload: NonNullable<ThreadMessage['tablePayload']> = tw;
        if (Array.isArray(tw.rows) && rowIdx >= 0 && rowIdx < tw.rows.length) {
          const incoming = tw.rows as Record<string, unknown>[];
          const hypCols = ['假设1', '假设2', '假设3'] as const;
          const newRows = incoming.map((r, i) => {
            const pr = prevRows[i];
            if (i === rowIdx && prevRow) {
              const mapped = mapRuminationHypConfirmAfterRegen(prevRow, r, pendingLabel);
              return { ...r, [HYP_CONFIRM_KEY]: mapped };
            }
            if (!pr) return r;
            const merged = { ...r };
            for (const k of hypCols) {
              const nextS = String(r[k] ?? '').trim();
              const prevS = String(pr[k] ?? '').trim();
              if (!nextS && prevS) merged[k] = pr[k];
            }
            if (Object.prototype.hasOwnProperty.call(pr, HYP_CONFIRM_KEY)) {
              merged[HYP_CONFIRM_KEY] = pr[HYP_CONFIRM_KEY];
            }
            return merged;
          });
          nextPayload = { ...tw, rows: newRows } as NonNullable<ThreadMessage['tablePayload']>;
        }
        setRuminationTablePayload(nextPayload);
        if (res.data.progress) setRuminationProgressState(res.data.progress);
        if (typeof res.data.max_reached_filter_step === 'number') {
          setRuminationMaxReached(res.data.max_reached_filter_step);
        } else if (res.data.progress) {
          setRuminationMaxReached(computeMaxReachedFromSnapshots(res.data.progress));
        }
        // 勿递增 ruminationProgressNonce：会触发全量 get-table effect，用服务端表覆盖本地，导致其它行未提交的选项被清空
      } catch (err) {
        setChatError(
          getApiErrorMessage(err, t('explore.chat.ruminationUi.hypothesisRegenerateError'))
        );
      } finally {
        setHypothesisRegeneratingRowIndex(null);
      }
    },
    [
      activationCode,
      phase,
      ruminationTablePayload?.rows,
      ruminationTablePayload?.step,
      ruminationViewStep,
      t,
    ]
  );

  const handleRuminationRefillRequest = useCallback(() => {
    if (!activationCode || phase !== 'rumination' || !activeThreadId) return;
    if (
      ruminationTableNavLoading ||
      ruminationTableSubmitting ||
      hypothesisRegeneratingRowIndex !== null
    ) {
      return;
    }
    setRuminationRefillConfirmOpen(true);
  }, [
    activationCode,
    activeThreadId,
    phase,
    ruminationTableNavLoading,
    ruminationTableSubmitting,
    hypothesisRegeneratingRowIndex,
  ]);

  const handleRuminationRefillConfirm = useCallback(() => {
    if (!activationCode || phase !== 'rumination' || !activeThreadId) return;
    setRuminationRefillConfirmOpen(false);
    ruminationGuideAbortRef.current?.abort();
    ruminationGuideAbortRef.current = null;
    setRuminationGuideBusy(false);
    setInput('');
    setChatError(null);
    void (async () => {
      const ok = await loadRuminationTableStep(ruminationViewStep, { resetInitial: true });
      if (!ok) return;
      const cut = cutMessagesForRuminationStepRefill(
        messagesRef.current,
        ruminationViewStep,
        ruminationStepBoundariesRef.current
      );
      setMessages(cut.messages);
      setRuminationStepBoundaries(cut.boundaries);
      saveRuminationStepBoundaries(activationCode, activeThreadId, cut.boundaries);
      const th = threads.find((t) => t.id === activeThreadId);
      if (th) {
        try {
          await apiClient.post('/simple-chat/thread/reopen', {
            activation_code: activationCode,
            phase: BACKEND_PHASE[phase],
            thread_id: activeThreadId,
          });
        } catch {
          /* 与「继续完善」一致：失败不阻断本地状态 */
        }
        const updated: ChatThread = {
          ...th,
          status: 'in-progress',
          messages: cut.messages,
        };
        saveThread(activationCode, phase, updated);
        setThreads((prev) =>
          prev.map((t) => (t.id === activeThreadId ? updated : t))
        );
      }
      setRuminationProgressNonce((n) => n + 1);
    })();
  }, [
    activationCode,
    activeThreadId,
    loadRuminationTableStep,
    phase,
    ruminationViewStep,
    threads,
  ]);

  const phaseClass =
    phase === 'values'
      ? 'values'
      : phase === 'strengths'
        ? 'strength'
        : phase === 'interests'
          ? 'interest'
          : phase === 'purpose'
            ? 'purpose'
            : 'rumination';

  /** 沉淀对话区：助手气泡样式与前四步一致（values 蓝条白底），用户气泡仍用紫色主题 */
  const flowAiPhaseClass = phase === 'rumination' ? 'values' : phaseClass;

  /** 筛选子步导航：普通用户仅在 filter 段；管理员在 final_choice 仍可上一步/下一步/改表 */
  const ruminationShowFilterStepNav =
    !!ruminationTablePayload &&
    (ruminationProgressState?.main_section === 'filter' ||
      (adminDebugBypass && ruminationProgressState?.main_section === 'final_choice'));

  if (!session || !phaseMeta || !phaseInfo) return null;

  const useCareeringMatte = phase !== 'rumination';

  return (
    <div
      className={
        phase === 'rumination'
          ? 'rumination-beautiful-root flow-light relative flex min-h-0 flex-col overflow-hidden h-[calc(100dvh-3.5rem)] max-h-[calc(100dvh-3.5rem)]'
          : 'flow-light careering-matte flex min-h-0 flex-col overflow-hidden h-[calc(100dvh-3.5rem)] max-h-[calc(100dvh-3.5rem)]'
      }
      data-phase={phase}
    >
      {phase === 'rumination' ? (
        <ExploreLandingMeshLayers />
      ) : (
        <ChatPhaseBackground phase={phase} engine="silk" />
      )}
      {/* 顶栏留白由 (main)/layout.tsx 的 pt-14 承担，此处勿再 pt-14，否则侧栏与主区会出现双倍空白 */}
      <div className="flex min-h-0 flex-1 overflow-hidden relative z-10">
        {phase !== 'rumination' && (
          <ChatPhaseSidebar
            threads={threadsForSidebar}
            activeThreadId={activeThreadId}
            onSelectThread={handleSelectThread}
            onNewChat={handleNewChat}
            onDeleteThread={handleDeleteThread}
            canNewChat={canCreateMoreThreads}
            phaseTitle={phaseLabel}
            phaseInteractionLocked={phaseInteractionLocked}
            careeringMatte
            streamBlocksSessionSwitch={sending || ruminationGuideBusy}
          />
        )}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {phase === 'rumination' && (
            <>
              <header className="relative shrink-0 px-4 pb-2 pt-3 text-center sm:px-8 sm:pb-3 sm:pt-4">
                <h1 className="pr-10 text-2xl font-bold text-bd-fg sm:pr-0 sm:text-3xl">
                  {phaseInfo.num} {phaseLabel}
                </h1>
                <p className="mx-auto mt-2 max-w-2xl text-sm leading-relaxed text-neutral-600">
                  {phaseMeta.desc} {phaseMeta.hint}
                </p>
                {!hideRuminationHeaderComplete && (
                  <button
                    type="button"
                    onClick={handleCompleteAndContinue}
                    disabled={!canContinue}
                    title={!canContinue ? t('explore.chat.selectCompletedHint') : ''}
                    className="bd-btn-black absolute right-2 top-2 flex items-center gap-2 rounded-full px-3 py-2 text-xs font-semibold text-white sm:right-6 sm:top-3 sm:px-4 sm:py-2.5 sm:text-sm disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <FileText size={15} strokeWidth={2} className="hidden shrink-0 sm:inline" />
                    <span className="max-w-[9rem] truncate sm:max-w-none">
                      {t('explore.chat.completeAndContinue')}
                    </span>
                  </button>
                )}
              </header>
              {activationCode && (
                <div className="shrink-0 px-4 pb-3 pt-0 sm:px-8">
                  <RuminationSectionProgress
                    variant="beautiful"
                    activationCode={activationCode}
                    refreshNonce={ruminationProgressNonce}
                    externalProgressOnly
                    serverProgress={ruminationProgressState}
                    viewFilterStep={
                      ruminationShowFilterStepNav ? ruminationViewStep : null
                    }
                    filterStepNav={
                      ruminationShowFilterStepNav
                        ? {
                            onPrev: handleRuminationFilterPrev,
                            onNext: handleRuminationFilterNext,
                            prevDisabled:
                              ruminationViewStep <= 1 ||
                              sending ||
                              ruminationGuideBusy ||
                              ruminationTableNavLoading ||
                              hypothesisRegeneratingRowIndex !== null,
                            nextDisabled:
                              sending ||
                              ruminationGuideBusy ||
                              ruminationTableNavLoading ||
                              hypothesisRegeneratingRowIndex !== null ||
                              ruminationViewStep >= RUMINATION_FILTER_STEP_MAX ||
                              !isRuminationFilterStepReachable(
                                ruminationViewStep + 1,
                                ruminationProgressState
                              ),
                            hidePrev: ruminationViewStep <= 1,
                            hideNext: ruminationViewStep >= RUMINATION_FILTER_STEP_MAX,
                            segmentJump: {
                              jumpDisabled:
                                sending ||
                                ruminationGuideBusy ||
                                ruminationTableNavLoading ||
                                hypothesisRegeneratingRowIndex !== null,
                              onJump: (step) => {
                                if (step === ruminationViewStep) return;
                                void loadRuminationTableStep(step);
                              },
                            },
                          }
                        : undefined
                    }
                  />
                </div>
              )}
            </>
          )}
          <div
            ref={phase === 'rumination' ? ruminationWorkbenchRef : undefined}
            className={`flex min-h-0 min-w-0 flex-1 ${
              phase === 'rumination'
                ? `relative rumination-workbench flex w-full min-h-0 gap-4 px-3 pb-3 sm:gap-6 sm:px-6 ${ruminationWorkbenchStacked ? 'flex-col' : 'flex-row'}`
                : 'flex-col'
            }`}
          >
            {phase === 'rumination' && ruminationTableNavLoading && (
              <div
                className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-3 rounded-xl bg-white/45 px-4 text-center text-sm font-medium text-neutral-700 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.6)] backdrop-blur-sm"
                role="status"
                aria-live="polite"
                aria-busy="true"
              >
                <Loader2 className="h-8 w-8 shrink-0 animate-spin text-sky-600" aria-hidden />
                <span className="max-w-xs leading-snug">
                  {t('explore.chat.ruminationUi.tableNavLoading')}
                </span>
              </div>
            )}
            {phase === 'rumination' && (
              <aside
                className={`rumination-beautiful-card flex min-h-0 min-w-0 flex-col overflow-hidden py-4 pl-4 pr-3 sm:min-h-[min(52vh,560px)] sm:py-5 sm:pl-5 sm:pr-4 ${
                  ruminationWorkbenchStacked ? 'w-full flex-none' : 'w-full flex-1 sm:w-auto'
                }`}
              >
                {ruminationTablePayload ? (
                  <RuminationTableWidget
                    className="min-h-0 flex-1"
                    uiVariant="glass"
                    cardTitle={t('explore.chat.ruminationUi.tableCardTitle')}
                    payload={ruminationTablePayload}
                    hideConfirmButton={false}
                    confirmLabel={t('explore.chat.ruminationTable.confirm')}
                    refillLabel={t('explore.chat.ruminationTable.refill')}
                    selectPlaceholder={t('explore.chat.ruminationUi.tableSelectPlaceholder')}
                    inputPlaceholder={t('explore.chat.ruminationUi.tableInputPlaceholder')}
                    hypothesisRegenerateHint={t(
                      'explore.chat.ruminationUi.hypothesisRegenerateHint'
                    )}
                    hypothesisTagFreelanceLabel={t(
                      'explore.chat.ruminationUi.hypothesisTagFreelance'
                    )}
                    hypothesisTagCompanyLabel={t(
                      'explore.chat.ruminationUi.hypothesisTagCompany'
                    )}
                    hypothesisTagExtraLabel={t('explore.chat.ruminationUi.hypothesisTagExtra')}
                    hypothesisPendingLabel={t('explore.chat.ruminationUi.hypothesisPendingOption')}
                    confirmDisabledAfterCommit={ruminationStepHasSubmitted}
                    hypothesisRegenerateLabel={t('explore.chat.ruminationUi.hypothesisRegenerate')}
                    hypothesisRegeneratingLabel={t(
                      'explore.chat.ruminationUi.hypothesisRegenerating'
                    )}
                    hypothesisRegeneratingRowIndex={hypothesisRegeneratingRowIndex}
                    onHypothesisRegenerate={handleHypothesisRegenerateRow}
                    tableRefillMode={ruminationStepHasSubmitted}
                    onRefill={handleRuminationRefillRequest}
                    onRowContextChange={setRuminationRowContext}
                    submitting={ruminationTableSubmitting}
                    onConfirm={(rows) =>
                      handleTableConfirm('rumination_left_panel', ruminationTablePayload, rows)
                    }
                    disabled={
                      sending ||
                      ruminationTableSubmitting ||
                      ruminationGuideBusy ||
                      ruminationTableNavLoading ||
                      hypothesisRegeneratingRowIndex !== null
                    }
                  />
                ) : (
                  <div className="flex min-h-0 flex-1 flex-col items-center justify-center py-10 text-center">
                    <p className="px-2 text-sm text-neutral-500">
                      {t('explore.chat.ruminationUi.tableEmptyHint')}
                    </p>
                  </div>
                )}
              </aside>
            )}
            <div
              className={`flex min-h-0 min-w-0 flex-col overflow-hidden ${
                phase === 'rumination'
                  ? ruminationWorkbenchStacked
                    ? 'w-full flex-none min-h-[min(40vh,420px)]'
                    : 'w-full flex-1 sm:w-auto'
                  : 'flex-1'
              }`}
            >
              {phase !== 'rumination' && (
                <header className="careering-chat-header">
                  <h2 className="careering-chat-phase-title">
                    {phaseInfo.num} {phaseLabel}
                  </h2>
                  <div className="careering-chat-header-actions">
                    <button
                      type="button"
                      onClick={handleCompleteAndContinue}
                      disabled={!canContinue}
                      title={!canContinue ? t('explore.chat.selectCompletedHint') : ''}
                      className={`bd-btn-black inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white transition-all sm:px-5 ${
                        canContinue ? '' : 'cursor-not-allowed opacity-40'
                      }`}
                    >
                      <FileText size={15} strokeWidth={2} className="hidden sm:inline" aria-hidden />
                      <span>{t('explore.chat.completeAndContinue')}</span>
                      <ChevronRight size={16} strokeWidth={2} className="inline" aria-hidden />
                    </button>
                  </div>
                </header>
              )}

              <div
                className={
                  phase === 'rumination'
                    ? 'rumination-beautiful-card rumination-beautiful-card--chat flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden py-4 px-3 sm:px-5 sm:py-5'
                    : 'flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden'
                }
              >
                {phase === 'rumination' && (
                  <div className="mb-2 shrink-0 border-b border-black/[0.06] pb-2">
                    <h2 className="text-lg font-semibold text-bd-fg">
                      {t('explore.chat.ruminationUi.chatTitle')}
                    </h2>
                    <p className="mt-0.5 text-xs text-neutral-500">
                      {t('explore.chat.ruminationUi.chatSubtitle')}
                    </p>
                  </div>
                )}
                <div
                  className={`flex min-h-0 flex-1 flex-col overflow-hidden ${
                    phase === 'rumination' ? 'py-1' : useCareeringMatte ? 'py-4' : 'px-6 py-4'
                  }`}
                >
                  {/* 对话区：沉淀阶段表格在左侧栏，此处仅文本与结论卡 */}
                  <div
                    className={`flow-chat-box relative flex min-h-0 min-w-0 flex-1 flex-col ${
                      phase === 'rumination'
                        ? 'rumination-beautiful-chat-panel w-full max-w-none'
                        : useCareeringMatte
                          ? 'w-full max-w-none'
                          : 'mx-auto w-full max-w-3xl'
                    }`}
                  >
              <div
                ref={chatBodyRef}
                className={`flow-chat-body min-h-0 flex-1 overflow-y-auto ${
                  useCareeringMatte || phase === 'rumination' ? 'min-w-0 w-full' : ''
                } ${phase === 'rumination' ? 'rumination-chat-body-fade' : ''}`}
              >
                <div
                  className={
                    useCareeringMatte || phase === 'rumination'
                      ? 'careering-chat-messages-inner min-w-0 w-full max-w-none px-4 sm:px-6 lg:px-12'
                      : 'contents'
                  }
                >
                {!useCareeringMatte && phase !== 'rumination' && (
                  <div className="flow-dimension-label">
                    <span className="flow-dimension-dot" />
                    {t('explore.chat.exploringWithDim', { dim: phaseLabel })}
                  </div>
                )}

                {initLoading ? (
                  <div className="flex justify-center py-12">
                    <div className="flex gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <motion.div
                          key={i}
                          className="w-2 h-2 rounded-full bg-neutral-400"
                          animate={{ opacity: [0.3, 1, 0.3] }}
                          transition={{ duration: 1.2, delay: i * 0.2, repeat: Infinity }}
                        />
                      ))}
                    </div>
                  </div>
                ) : displayMessages.length === 0 ? (
                  <p className="flow-progress-text text-center py-8 text-sm">
                    {phase === 'rumination'
                      ? t('explore.chat.ruminationUi.chatEmptyHint')
                      : t('explore.chat.preparingFirstQuestion')}
                  </p>
                ) : (
                  displayMessages.map((m, idx) => {
                    const msgIdxInFull = messages.findIndex((x) => x.id === m.id);
                    const aiIndexForHandlers = msgIdxInFull >= 0 ? msgIdxInFull : idx;
                    return (
                    <div key={m.id} className={m.role === 'user' || m.type === 'dimension_conclusion' ? (m.role === 'user' ? 'flow-msg-user' : '') : ''}>
                      {m.type === 'dimension_conclusion' && m.conclusionData ? (
                        <div className="flow-msg-conclusion-wrap">
                          <DimensionConclusionCard
                            phase={phaseClass}
                            data={m.conclusionData}
                            isCompleted={isSelectedCompleted || !!m.conclusionConfirmed}
                            inline
                            collapsed={!!m.conclusionCollapsed}
                            onCollapsedChange={(collapsed) =>
                              setMessages((prev) =>
                                prev.map((msg) =>
                                  msg.id === m.id ? { ...msg, conclusionCollapsed: collapsed } : msg
                                )
                              )
                            }
                            showActions={
                              !m.conclusionCollapsed &&
                              m.id === displayMessages.filter((x) => x.type === 'dimension_conclusion').pop()?.id
                            }
                            onConfirm={handleConfirmConclusion}
                            onContinueChat={() => handleContinueChat(m)}
                          />
                        </div>
                      ) : m.role === 'user' ? (
                        <div className="flow-msg-user-wrap">
                          {(useCareeringMatte || phase === 'rumination') && m.createdAt !== undefined && (
                            <div className="flow-msg-careering-meta flow-msg-careering-meta--user">
                              <div
                                className="flow-msg-careering-avatar flow-msg-careering-avatar--user text-xs font-semibold text-white"
                                style={
                                  user?.avatar_url
                                    ? {
                                        background: `url(${user.avatar_url}) center/cover no-repeat`,
                                      }
                                    : {
                                        background:
                                          'linear-gradient(135deg, var(--bd-phase-values), var(--bd-phase-strengths))',
                                      }
                                }
                                aria-hidden
                              >
                                {!user?.avatar_url ? userChatAvatarInitials : null}
                              </div>
                              <span>
                                {t('explore.chat.careeringUser')} ·{' '}
                                {`${new Date(m.createdAt).getHours().toString().padStart(2, '0')}:${new Date(m.createdAt).getMinutes().toString().padStart(2, '0')}`}
                              </span>
                            </div>
                          )}
                          {!useCareeringMatte && phase !== 'rumination' && m.createdAt !== undefined && (
                            <span className="flow-msg-time text-[10px] text-[var(--flow-text-muted)] mb-1 block">
                              {`${new Date(m.createdAt).getHours().toString().padStart(2, '0')}:${new Date(m.createdAt).getMinutes().toString().padStart(2, '0')}`}
                            </span>
                          )}
                          <div
                            className={`flow-msg-user-anchor${m.ruminationRowLabel ? ' has-row-context' : ''}`}
                          >
                            {m.ruminationRowLabel ? (
                              <div
                                className="flow-msg-user-context-bar"
                                title={m.ruminationRowLabel}
                              >
                                <ListFilter
                                  size={14}
                                  strokeWidth={2}
                                  className="flow-msg-user-context-icon shrink-0"
                                  aria-hidden
                                />
                                <span className="flow-msg-user-context-text">
                                  {m.ruminationRowLabel}
                                </span>
                              </div>
                            ) : null}
                            <div className="flow-msg-user-content" lang="zh-CN">
                              {(() => {
                                const s = (m.content || '').replace(/\r\n/g, '\n');
                                const charCount = [...s].length;
                                const hasManualBreak = s.includes('\n');
                                const compact =
                                  charCount > 0 && charCount < 25 && !hasManualBreak;
                                const textClass =
                                  useCareeringMatte || phase === 'rumination'
                                    ? `flow-msg-user-text flow-msg-user-text--careering-plain${compact ? ' flow-msg-user-text--compact' : ''}`
                                    : `flow-msg-user-text${compact ? ' flow-msg-user-text--compact' : ''}`;
                                return <span className={textClass}>{s}</span>;
                              })()}
                            </div>
                          </div>
                          <div className="flow-msg-user-toolbar">
                            <button
                              type="button"
                              className="flow-toolbar-btn"
                              title={t('explore.chat.messageToolbar.copy')}
                              onClick={() => copyToClipboard(m.content)}
                            >
                              <Copy size={14} strokeWidth={1.6} />
                            </button>
                          </div>
                        </div>
                      ) : (
                        <FlowAiMessage
                          content={m.content}
                          phase={flowAiPhaseClass}
                          variant={
                            phase === 'rumination'
                              ? 'ruminationWorkbench'
                              : useCareeringMatte
                                ? 'careeringMatte'
                                : undefined
                          }
                          careeringAiRoleLabel={t('explore.chat.careeringAiRole')}
                          streaming={
                            (sending || ruminationGuideBusy) &&
                            idx === displayMessages.length - 1
                          }
                          thinkStreaming={m.thinkStreaming}
                          thinkChunkContent={m.thinkChunkContent}
                          thinkPlaceholders={[
                            t('explore.chat.thinkInProgress1'),
                            t('explore.chat.thinkInProgress2'),
                            t('explore.chat.thinkInProgress3'),
                            t('explore.chat.thinkInProgress4'),
                            t('explore.chat.thinkInProgress5'),
                            t('explore.chat.thinkInProgress6'),
                          ]}
                          timestamp={m.createdAt}
                          toolbarCopyTitle={t('explore.chat.messageToolbar.copy')}
                          toolbarLikeTitle={t('explore.chat.messageToolbar.like')}
                          sessionId={backendSessionId ?? undefined}
                          logIndex={messages
                            .slice(0, aiIndexForHandlers)
                            .filter((x) => x.role === 'assistant' && x.type !== 'dimension_conclusion')
                            .length}
                          dimension={phase}
                        />
                      )}
                    </div>
                    );
                  })
                )}
                {conclusionLoading && (
                  <div className="flow-msg-conclusion-wrap my-3">
                    <div className="rounded-xl border border-[var(--flow-border)] bg-[var(--flow-card-bg)] p-4 flex items-center gap-3 text-[var(--flow-text-muted)] text-sm animate-pulse">
                      <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      <span>{t('explore.chat.conclusionLoading')}</span>
                    </div>
                  </div>
                )}
                {chatError && (
                  <div className="flow-msg-error">
                    <div className="flow-msg-error-text">{chatError}</div>
                    <button
                      type="button"
                      className="flow-retry-btn"
                      onClick={() => {
                        setChatError(null);
                        const lastUser = [...messages].filter((m) => m.role === 'user').pop();
                        if (lastUser) handleSend(lastUser.content, true);
                      }}
                    >
                      {t('explore.chat.retry')}
                    </button>
                  </div>
                )}
                <div ref={messagesEndRef} />
                </div>
              </div>

              <button
                type="button"
                aria-label={t('explore.chat.scrollToBottom')}
                className={`flow-scroll-bottom-btn ${showScrollBottom ? 'visible' : ''}`}
                onClick={scrollToBottom}
              >
                <ChevronDown size={22} strokeWidth={2.5} />
              </button>
            </div>
          </div>

          {/* 对话输入框：固定在最底部 */}
          <div className="careering-input-dock w-full flex-shrink-0">
            <div
              className={`flow-input-area${phase === 'rumination' && ruminationRowContext ? ' rumination-input-focused-context' : ''}`}
            >
              <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="w-full">
                <div
                  className={`flow-input-box${
                    (phaseInteractionLocked && !sending && !ruminationGuideBusy) ||
                    (phase === 'rumination' && ruminationTableNavLoading && !sending)
                      ? ' opacity-40 pointer-events-none'
                      : ''
                  }`}
                >
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (
                          !sending &&
                          !ruminationGuideBusy &&
                          !isReadOnly &&
                          !(phase === 'rumination' && ruminationTableNavLoading)
                        ) {
                          handleSend();
                        }
                      }
                    }}
                    placeholder={
                      isReadOnly
                        ? t('explore.chat.placeholderReadOnly')
                        : hasCollapsedConclusion
                          ? t('explore.chat.placeholderRefine')
                          : phase === 'rumination' && ruminationRowContext
                            ? t('explore.chat.ruminationUi.placeholderWithRow', {
                                label: ruminationRowContext.label,
                              })
                            : t('explore.chat.inputPlaceholderCareering')
                    }
                    rows={1}
                    disabled={
                      sending ||
                      ruminationGuideBusy ||
                      isReadOnly ||
                      (phase === 'rumination' && ruminationTableNavLoading)
                    }
                    className="flow-input-field"
                  />
                  {showRequestConclusionDraftControl && (
                    <button
                      type="button"
                      onClick={() => void handleRequestConclusionDraft()}
                      disabled={
                        sending || ruminationGuideBusy || requestConclusionDraftBusy
                      }
                      title={t('explore.chat.requestConclusionDraftTitle')}
                      className="flex shrink-0 items-center gap-1 rounded-xl border border-black/10 bg-white/80 px-2.5 py-1.5 text-xs font-medium text-[var(--flow-text-body)] transition-colors hover:bg-neutral-50 disabled:pointer-events-none disabled:opacity-40"
                    >
                      {requestConclusionDraftBusy ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                      ) : (
                        <FileText className="h-3.5 w-3.5 opacity-70" aria-hidden />
                      )}
                      <span className="max-[380px]:hidden">{t('explore.chat.requestConclusionDraft')}</span>
                    </button>
                  )}
                  <div className="flow-send-btn-wrap">
                    {(sending || ruminationGuideBusy) && (
                      <div className="flow-send-glow" aria-hidden />
                    )}
                    <button
                      type="button"
                      onClick={
                        sending || ruminationGuideBusy ? handleStopStream : () => handleSend()
                      }
                      disabled={
                        (isReadOnly ||
                          (!sending &&
                            !ruminationGuideBusy &&
                            (!input.trim() ||
                              (phase === 'rumination' && ruminationTableNavLoading)))) as boolean
                      }
                      className={`flow-send-btn ${sending || ruminationGuideBusy ? 'is-stop' : ''}`}
                    >
                      {sending || ruminationGuideBusy ? (
                        <Square size={16} strokeWidth={0} fill="white" />
                      ) : (
                        <ArrowUp size={16} strokeWidth={2.2} />
                      )}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          </div>
          </div>
        </div>
        </div>
      </div>
      </div>
      {threadSwitchDialogOpen && (
        <div
          className="fixed inset-0 z-[56] flex items-center justify-center bg-black/30 backdrop-blur-sm"
          onClick={handleCancelThreadSwitchWhileStreaming}
          role="presentation"
        >
          <div
            className="mx-4 max-w-md rounded-2xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="thread-switch-stream-title"
          >
            <h3
              id="thread-switch-stream-title"
              className="mb-2 text-lg font-semibold text-[var(--flow-text-body)]"
            >
              {t('explore.chat.threadSwitchWhileStreamingTitle')}
            </h3>
            <p className="mb-6 text-sm leading-relaxed text-[var(--flow-text-muted)]">
              {t('explore.chat.threadSwitchWhileStreamingMessage')}
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={handleCancelThreadSwitchWhileStreaming}
                className="rounded-xl px-4 py-2 text-sm font-medium text-[var(--flow-text-muted)] transition-colors hover:bg-neutral-100"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirmThreadSwitchWhileStreaming}
                className="rounded-xl bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-800"
              >
                {t('explore.chat.threadSwitchWhileStreamingConfirm')}
              </button>
            </div>
          </div>
        </div>
      )}
      {phase === 'rumination' && ruminationRefillConfirmOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 backdrop-blur-sm"
          onClick={() => setRuminationRefillConfirmOpen(false)}
          role="presentation"
        >
          <div
            className="mx-4 max-w-md rounded-2xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="rumination-refill-confirm-title"
          >
            <h3
              id="rumination-refill-confirm-title"
              className="mb-2 text-lg font-semibold text-[var(--flow-text-body)]"
            >
              {t('explore.chat.ruminationTable.refillConfirmTitle')}
            </h3>
            <p className="mb-6 text-sm leading-relaxed text-[var(--flow-text-muted)]">
              {t('explore.chat.ruminationTable.refillConfirmMessage', {
                from: String(ruminationViewStep),
              })}
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setRuminationRefillConfirmOpen(false)}
                className="rounded-xl px-4 py-2 text-sm font-medium text-[var(--flow-text-muted)] transition-colors hover:bg-neutral-100"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={handleRuminationRefillConfirm}
                className="rounded-xl bg-red-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-600"
              >
                {t('common.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
      {phase === 'rumination' && ruminationStep7FinalizeOpen && (
        <div
          className="fixed inset-0 z-[61] flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => {
            setRuminationStep7FinalizeOpen(false);
            pendingStep7SubmitRef.current = null;
          }}
          role="presentation"
        >
          <div
            className="mx-4 max-w-md rounded-2xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="rumination-step7-finalize-title"
          >
            <h3
              id="rumination-step7-finalize-title"
              className="mb-2 text-lg font-semibold text-[var(--flow-text-body)]"
            >
              {t('explore.chat.ruminationTable.step7FinalizeTitle')}
            </h3>
            <p className="mb-6 text-sm leading-relaxed text-[var(--flow-text-muted)]">
              {t('explore.chat.ruminationTable.step7FinalizeMessage')}
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setRuminationStep7FinalizeOpen(false);
                  pendingStep7SubmitRef.current = null;
                }}
                className="rounded-xl px-4 py-2 text-sm font-medium text-[var(--flow-text-muted)] transition-colors hover:bg-neutral-100"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={() => void handleRuminationStep7FinalizeConfirmed()}
                className="rounded-xl bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-800"
              >
                {t('common.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
      {phase === 'rumination' && (
        <RuminationTableSubmitPortal
          open={ruminationTableSubmitting}
          lineBefore={t('explore.chat.ruminationUi.tableSubmittingOrganizing')}
          lineAfter={t('explore.chat.ruminationUi.tableSubmittingWait')}
        />
      )}
    </div>
  );
}
