'use client';

import { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from 'react';
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
} from 'lucide-react';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import DimensionConclusionCard, { type DimensionConclusionData } from '@/components/explore/DimensionConclusionCard';
import ChatPhaseBackground from '@/components/explore/ChatPhaseBackground';
import ExploreLandingMeshLayers from '@/components/explore/ExploreLandingMeshLayers';
import ChatPhaseSidebar from '@/components/explore/ChatPhaseSidebar';
import RuminationSectionProgress from '@/components/explore/RuminationSectionProgress';
import RuminationTableWidget from '@/components/explore/RuminationTableWidget';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
import { authApi } from '@/lib/api/auth';
import {
  PHASES,
  loadSession,
  saveSession,
  unlockNextPhase,
  getLastActivationCode,
  type PhaseKey,
  type ExploreSession,
} from '@/lib/explore/session';
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
  type ChatThread,
  type ThreadMessage,
} from '@/lib/explore/threads';
import {
  loadRuminationStepBoundaries,
  saveRuminationStepBoundaries,
  ensureDefaultStepOne,
  sliceMessagesForRuminationStep,
} from '@/lib/explore/ruminationStepBoundaries';
import {
  ruminationApi,
  type RuminationProgress,
  type RuminationSubmitData,
} from '@/lib/api/rumination';
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

function computeMaxReachedFromSnapshots(p: RuminationProgress | null): number {
  if (!p?.filter_step_snapshots) return 0;
  let m = 0;
  for (const [key, snap] of Object.entries(p.filter_step_snapshots)) {
    const n = parseInt(key, 10);
    if (Number.isNaN(n)) continue;
    if (snap?.submitted != null) m = Math.max(m, n);
  }
  return m;
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
  const [backendSyncedThreadId, setBackendSyncedThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
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
  /** 与后端 filter_step（1–9）对齐：当前查看的筛选子步、已提交到的最远步、完整 progress（含快照） */
  const [ruminationProgressState, setRuminationProgressState] =
    useState<RuminationProgress | null>(null);
  const [ruminationViewStep, setRuminationViewStep] = useState(1);
  const [ruminationMaxReached, setRuminationMaxReached] = useState(0);
  const [ruminationStepBoundaries, setRuminationStepBoundaries] = useState<Record<string, number>>(
    {}
  );
  const [ruminationWorkbenchStacked, setRuminationWorkbenchStacked] = useState(false);
  const [ruminationTableSubmitting, setRuminationTableSubmitting] = useState(false);
  const [ruminationRowContext, setRuminationRowContext] = useState<{
    rowIndex: number;
    label: string;
  } | null>(null);
  const ruminationWorkbenchRef = useRef<HTMLDivElement>(null);
  const { user, setTokens } = useAuthStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);
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
      ruminationProgressState?.main_section === 'filter' && fs > 0;
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
          thinkContent: m.think_content ?? undefined,
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
            const msgs = mapHistoryToThreadMessages(history, meta);
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
        // 网络失败时回退到 localStorage（离线兜底）
        let list = getThreads(activationCode, phase);
        if (phase === 'rumination' && list.length > 1) {
          list = collapseRuminationThreadsToOne(list);
          setThreadsForPhase(activationCode, phase, list);
        }
        setThreads(list);
        const activeId = getActiveThreadId(activationCode, phase);
        setActiveThreadIdState(activeId);
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
            setThreadsForPhase(activationCode, phase, syncedThreads);
            setThreads(syncedThreads);
            const first = syncedThreads[0];
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
            const msgs = mapHistoryToThreadMessages(history, meta);
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

  const checkScrollPosition = useCallback(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    setShowScrollBottom(el.scrollHeight - el.scrollTop - el.clientHeight > 80);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, displayMessages]);

  useEffect(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    el.addEventListener('scroll', checkScrollPosition);
    checkScrollPosition();
    return () => el.removeEventListener('scroll', checkScrollPosition);
  }, [checkScrollPosition, messages]);

  const scrollToBottom = useCallback(() => {
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

  useEffect(() => {
    if (phase !== 'rumination') return;
    const last = [...messages]
      .reverse()
      .find((m) => m.type === 'table_widget' && m.tablePayload);
    if (last?.tablePayload) setRuminationTablePayload(last.tablePayload);
  }, [phase, messages]);

  const loadRuminationTableStep = useCallback(
    async (step: number, opts?: { resetInitial?: boolean }) => {
      if (!activationCode || phase !== 'rumination') return;
      try {
        setChatError(null);
        const res = await ruminationApi.getTable(activationCode, step, {
          resetInitial: opts?.resetInitial,
        });
        const p = res.data?.progress;
        const mr = res.data?.max_reached_filter_step;
        if (p) setRuminationProgressState(p);
        if (typeof mr === 'number') setRuminationMaxReached(mr);
        else if (p) setRuminationMaxReached(computeMaxReachedFromSnapshots(p));
        const w = res.data?.table_widget;
        if (w) {
          setRuminationTablePayload(w as ThreadMessage['tablePayload']);
          setRuminationViewStep(w.step ?? step);
          const stepKey = String(w.step ?? step);
          queueMicrotask(() => {
            setRuminationStepBoundaries((b) => {
              if (b[stepKey] !== undefined) return b;
              const len = messagesRef.current.length;
              const nb = { ...b, [stepKey]: len };
              if (activationCode && activeThreadId) {
                saveRuminationStepBoundaries(activationCode, activeThreadId, nb);
              }
              return nb;
            });
          });
        } else {
          setChatError(
            opts?.resetInitial
              ? t('explore.chat.ruminationTableRefillEmpty')
              : t('explore.chat.ruminationTableMissing')
          );
        }
      } catch {
        setChatError(t('explore.chat.ruminationTableLoadError'));
      }
    },
    [activationCode, activeThreadId, phase, t]
  );

  /**
   * 沉淀：单次 GET rumination-progress 更新进度与 max_reached；必要时再 GET get-table 补左栏表。
   * 原实现拆成两个 effect 会对同一接口连打多次；标题区 RuminationSectionProgress 已 externalProgressOnly，不再重复请求。
   */
  useEffect(() => {
    if (phase !== 'rumination' || !activationCode || initLoading) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await ruminationApi.get(activationCode);
        if (cancelled) return;
        const p = res?.data?.progress;
        const mr =
          res?.data?.max_reached_filter_step ?? computeMaxReachedFromSnapshots(p ?? null);
        if (p) setRuminationProgressState(p);
        setRuminationMaxReached(mr);

        if (
          !p ||
          p.main_section !== 'filter' ||
          !(p.filter_step > 0) ||
          p.filter_early_terminated
        ) {
          return;
        }
        if (messagesRef.current.some((m) => m.type === 'table_widget')) return;
        const stepToLoad = Math.min(9, Math.max(1, p.filter_step || 1));
        setRuminationViewStep(stepToLoad);
        const tb = await ruminationApi.getTable(activationCode, stepToLoad);
        if (cancelled || !tb?.data?.table_widget) return;
        if (tb.data.progress) setRuminationProgressState(tb.data.progress);
        if (typeof tb.data.max_reached_filter_step === 'number') {
          setRuminationMaxReached(tb.data.max_reached_filter_step);
        }
        const w = tb.data.table_widget;
        setRuminationTablePayload(w as ThreadMessage['tablePayload']);
        if (w?.step != null) setRuminationViewStep(w.step);
        if (w) {
          const stepKey = String(w.step ?? stepToLoad);
          queueMicrotask(() => {
            setRuminationStepBoundaries((b) => {
              if (b[stepKey] !== undefined) return b;
              const len = messagesRef.current.length;
              const nb = { ...b, [stepKey]: len };
              if (activationCode && activeThreadId) {
                saveRuminationStepBoundaries(activationCode, activeThreadId, nb);
              }
              return nb;
            });
          });
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [phase, activationCode, activeThreadId, initLoading, ruminationProgressNonce]);

  const handleSend = async (
    prefill?: string,
    skipAddUser?: boolean,
    /** 重新生成时沿用原用户消息的表格行摘要（避免闭包读到旧 messages） */
    regenerateRowLabel?: string
  ) => {
    const text = prefill ?? input.trim();
    if (!activationCode || !text || sending || isReadOnly) return;
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
              const thinkContent = typeof payload.think_end === 'string' ? payload.think_end : '';
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, thinkContent, thinkStreaming: false, thinkChunkContent: undefined }
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
                    ? { ...m, content: fullReply, thinkStreaming: false, createdAt: m.createdAt ?? doneAt }
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

  const handleRegenerate = useCallback(
    (aiIdx: number) => {
      if (sending || isReadOnly) return;
      const lastUser = messages.slice(0, aiIdx).filter((m) => m.role === 'user').pop();
      if (!lastUser) return;
      setMessages((prev) => prev.slice(0, aiIdx));
      setChatError(null);
      handleSend(lastUser.content, true, lastUser.ruminationRowLabel);
    },
    [messages, sending, isReadOnly]
  );

  const handleSelectThread = (thread: ChatThread) => {
    setActiveThreadId(activationCode!, phase, thread.id);
    setActiveThreadIdState(thread.id);
    setMessages(thread.messages);
    setBackendSyncedThreadId(thread.id);
  };

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
  };

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

  const handleStopStream = () => abortControllerRef.current?.abort();

  const handleTableConfirm = useCallback(
    async (
      _msgId: string,
      payload: NonNullable<ThreadMessage['tablePayload']>,
      rows: Record<string, unknown>[]
    ) => {
      if (!activationCode || !activeThreadId || phase !== 'rumination' || sending) return;
      setRuminationTableSubmitting(true);
      try {
        const single = Boolean(payload.singleRowMode && rows.length === 1);
        const patch: Record<string, unknown> = {};
        if (single) {
          for (const k of payload.editableCols || []) {
            patch[k] = rows[0][k];
          }
        }
        const res = await ruminationApi.submitTable(
          activationCode,
          activeThreadId,
          payload.step ?? 1,
          single ? null : rows,
          {
            mode: single ? 'single_row' : 'full_step',
            rowId: single ? String(rows[0].id ?? '') : undefined,
            patch: single ? patch : undefined,
            preferSingleRow: single,
          }
        );
        const data = res?.data as RuminationSubmitData | undefined;
        if (data?.early_terminated || data?.next_action === 'early_terminated') {
          setChatError(t('explore.chat.ruminationUi.tableEarlyTerminated'));
          return;
        }
        const nextTable = data?.next_table_widget;
        if (data?.progress) setRuminationProgressState(data.progress);
        if (typeof data?.max_reached_filter_step === 'number') {
          setRuminationMaxReached(data.max_reached_filter_step);
        }
        if (nextTable) {
          const newStep = nextTable.step ?? (payload.step ?? 1) + 1;
          const filtered = messages.filter((m) => m.type !== 'table_widget');
          setRuminationStepBoundaries((b) => {
            const nb = ensureDefaultStepOne({ ...b, [String(newStep)]: filtered.length });
            saveRuminationStepBoundaries(activationCode, activeThreadId, nb);
            return nb;
          });
          setRuminationTablePayload(nextTable as ThreadMessage['tablePayload']);
          setRuminationViewStep(newStep);
          setMessages(filtered);
        } else if (data?.progress?.filter_step != null && data.progress.filter_step >= 1) {
          setRuminationViewStep(Math.min(9, Math.max(1, data.progress.filter_step)));
        }
        setRuminationProgressNonce((n) => n + 1);
        /* 整表确认后由左侧表格直接进入下一步，不再自动往对话区插入跟进句，避免「一条条弹出」 */
      } catch {
        setChatError(t('explore.chat.ruminationUi.tableSubmitError'));
      } finally {
        setRuminationTableSubmitting(false);
      }
    },
    [activationCode, activeThreadId, phase, sending, messages, t]
  );

  const ruminationStepHasSubmitted = useMemo(() => {
    const k = String(ruminationViewStep);
    const ent = ruminationProgressState?.filter_step_snapshots?.[k];
    return ent != null && ent.submitted != null;
  }, [ruminationViewStep, ruminationProgressState]);

  const handleRuminationFilterPrev = useCallback(() => {
    if (ruminationViewStep <= 1) return;
    void loadRuminationTableStep(ruminationViewStep - 1);
  }, [ruminationViewStep, loadRuminationTableStep]);

  const handleRuminationFilterNext = useCallback(() => {
    const fs = ruminationProgressState?.filter_step ?? 0;
    const furthest = Math.max(ruminationMaxReached, fs, 1);
    if (ruminationViewStep >= furthest) return;
    void loadRuminationTableStep(ruminationViewStep + 1);
  }, [
    ruminationViewStep,
    ruminationMaxReached,
    ruminationProgressState?.filter_step,
    loadRuminationTableStep,
  ]);

  const handleRuminationRefill = useCallback(() => {
    void loadRuminationTableStep(ruminationViewStep, { resetInitial: true });
  }, [ruminationViewStep, loadRuminationTableStep]);

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

  /** 筛选子步可浏览上界：已提交到的最远步 与 当前工作 filter_step 的较大者 */
  const ruminationFurthestNavigableStep = useMemo(() => {
    const fs = ruminationProgressState?.filter_step ?? 0;
    return Math.max(ruminationMaxReached, fs, 1);
  }, [ruminationMaxReached, ruminationProgressState?.filter_step]);

  if (!session || !phaseMeta || !phaseInfo) return null;

  return (
    <div
      className={
        phase === 'rumination'
          ? 'rumination-beautiful-root flow-light relative h-screen flex flex-col overflow-hidden'
          : 'flow-light h-screen flex flex-col overflow-hidden'
      }
      data-phase={phase}
    >
      {phase === 'rumination' ? (
        <ExploreLandingMeshLayers />
      ) : (
        <ChatPhaseBackground phase={phase} />
      )}
      <div className="flex-1 flex min-h-0 relative z-10 pt-14 overflow-hidden">
        {phase !== 'rumination' && (
          <ChatPhaseSidebar
            phase={phase}
            phaseLabel={phaseLabel}
            threads={threadsForSidebar}
            activeThreadId={activeThreadId}
            onSelectThread={handleSelectThread}
            onNewChat={handleNewChat}
            onDeleteThread={handleDeleteThread}
            canNewChat={canCreateMoreThreads}
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
              </header>
              {activationCode && (
                <div className="shrink-0 px-4 pb-3 pt-0 sm:px-8">
                  <RuminationSectionProgress
                    variant="beautiful"
                    activationCode={activationCode}
                    refreshNonce={ruminationProgressNonce}
                    externalProgressOnly
                    serverProgress={ruminationProgressState}
                    filterStepNav={
                      ruminationProgressState?.main_section === 'filter' &&
                      ruminationTablePayload
                        ? {
                            onPrev: handleRuminationFilterPrev,
                            onNext: handleRuminationFilterNext,
                            prevDisabled: ruminationViewStep <= 1 || sending,
                            nextDisabled:
                              sending || ruminationViewStep >= ruminationFurthestNavigableStep,
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
                ? `rumination-workbench flex w-full min-h-0 gap-4 px-3 pb-3 sm:gap-6 sm:px-6 ${ruminationWorkbenchStacked ? 'flex-col' : 'flex-row'}`
                : 'flex-col'
            }`}
          >
            {phase === 'rumination' && (
              <aside
                className={`rumination-beautiful-card flex min-h-0 min-w-0 flex-col py-4 pl-4 pr-3 sm:min-h-[min(52vh,560px)] sm:py-5 sm:pl-5 sm:pr-4 ${
                  ruminationWorkbenchStacked ? 'w-full flex-none' : 'w-full flex-1 sm:w-auto'
                }`}
              >
                {ruminationTablePayload ? (
                  <RuminationTableWidget
                    uiVariant="glass"
                    cardTitle={t('explore.chat.ruminationUi.tableCardTitle')}
                    payload={ruminationTablePayload}
                    confirmLabel={t('explore.chat.ruminationTable.confirm')}
                    refillLabel={t('explore.chat.ruminationTable.refill')}
                    selectPlaceholder={t('explore.chat.ruminationUi.tableSelectPlaceholder')}
                    inputPlaceholder={t('explore.chat.ruminationUi.tableInputPlaceholder')}
                    loadingLabel={t('explore.chat.ruminationUi.tableSubmitting')}
                    tableRefillMode={ruminationStepHasSubmitted}
                    onRefill={handleRuminationRefill}
                    onRowContextChange={setRuminationRowContext}
                    submitting={ruminationTableSubmitting}
                    onConfirm={(rows) =>
                      handleTableConfirm(
                        'rumination_left_panel',
                        ruminationTablePayload,
                        rows
                      )
                    }
                    disabled={sending || ruminationTableSubmitting}
                  />
                ) : (
                  <div className="flex flex-1 flex-col items-center justify-center py-10 text-center">
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
                <header className="flex-shrink-0 border-b border-black/[0.05] bg-white/70 px-6 py-4 backdrop-blur">
                  <div className="mx-auto flex max-w-4xl items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <h1 className={`text-lg font-semibold ${phaseMeta.color}`}>
                        {phaseInfo.num} {phaseLabel}
                      </h1>
                      <p className="mt-1 text-sm leading-relaxed text-neutral-600">
                        {phaseMeta.desc} {phaseMeta.hint}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleCompleteAndContinue}
                      disabled={!canContinue}
                      title={!canContinue ? t('explore.chat.selectCompletedHint') : ''}
                      className={`flex-shrink-0 rounded-full px-5 py-2 text-sm font-medium transition-all ${
                        canContinue
                          ? 'bg-bd-ui-accent text-white'
                          : 'cursor-not-allowed bg-neutral-300 opacity-50'
                      }`}
                    >
                      {t('explore.chat.completeAndContinue')}{' '}
                      <ChevronRight size={14} className="inline" />
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
                    phase === 'rumination' ? 'py-1' : 'px-6 py-4'
                  }`}
                >
                  {/* 对话区：沉淀阶段表格在左侧栏，此处仅文本与结论卡 */}
                  <div
                    className={`flow-chat-box relative flex min-h-0 min-w-0 flex-1 flex-col ${
                      phase === 'rumination'
                        ? 'rumination-beautiful-chat-panel w-full max-w-none'
                        : 'mx-auto w-full max-w-3xl'
                    }`}
                  >
              <div ref={chatBodyRef} className="flow-chat-body flex-1 min-h-0 overflow-y-auto">
                <div className="flow-dimension-label">
                  <span className="flow-dimension-dot" />
                  {t('explore.chat.exploringWithDim', { dim: phaseLabel })}
                </div>

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
                  <p className="flow-progress-text text-center py-8 text-sm">{t('explore.chat.preparingFirstQuestion')}</p>
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
                          {m.createdAt !== undefined && (
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
                                  className="flow-msg-user-context-icon shrink-0 text-violet-700"
                                  aria-hidden
                                />
                                <span className="flow-msg-user-context-text">
                                  {m.ruminationRowLabel}
                                </span>
                              </div>
                            ) : null}
                            <div className="flow-msg-user-content">
                              {(() => {
                                const s = m.content || '';
                                const lines = s.split(/\r?\n/);
                                const display =
                                  lines.length > 1 && lines.every((l) => l.length <= 2)
                                    ? lines.join('')
                                    : s;
                                const charCount = [...display].length;
                                const hasManualBreak = /\r|\n/.test(display);
                                const compact =
                                  charCount > 0 && charCount < 25 && !hasManualBreak;
                                return (
                                  <span
                                    className={`flow-msg-user-text${compact ? ' flow-msg-user-text--compact' : ''}`}
                                  >
                                    {display}
                                  </span>
                                );
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
                          variant={phase === 'rumination' ? 'ruminationWorkbench' : undefined}
                          streaming={sending && idx === displayMessages.length - 1}
                          thinkContent={m.thinkContent}
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
                          thinkLabel={t('explore.chat.thinkProcess')}
                          timestamp={m.createdAt}
                          toolbarCopyTitle={t('explore.chat.messageToolbar.copy')}
                          toolbarRegenerateTitle={t('explore.chat.messageToolbar.regenerate')}
                          toolbarLikeTitle={t('explore.chat.messageToolbar.like')}
                          onRegenerate={() => handleRegenerate(aiIndexForHandlers)}
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
          <div
            className={
              phase === 'rumination'
                ? 'rumination-beautiful-input-shell w-full flex-shrink-0 px-1 pb-2 pt-1'
                : 'flex-shrink-0 w-full border-t border-black/[0.05] bg-bd-bg/95 px-6 pb-5 pt-3 backdrop-blur-sm'
            }
          >
            <div
              className={`flow-input-area${phase === 'rumination' && ruminationRowContext ? ' rumination-input-focused-context' : ''}`}
            >
              <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="w-full">
                <div className="flow-input-box">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (!sending && !isReadOnly) handleSend();
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
                            : t('explore.chat.placeholder')
                    }
                    rows={1}
                    disabled={sending || isReadOnly}
                    className="flow-input-field"
                  />
                  <div className="flow-send-btn-wrap">
                    {sending && <div className="flow-send-glow" aria-hidden />}
                    <button
                      type="button"
                      onClick={sending ? handleStopStream : () => handleSend()}
                      disabled={((!sending && !input.trim()) || isReadOnly) as boolean}
                      className={`flow-send-btn ${sending ? 'is-stop' : ''}`}
                    >
                      {sending ? <Square size={16} strokeWidth={0} fill="white" /> : <ArrowUp size={16} strokeWidth={2.2} />}
                    </button>
                  </div>
                </div>
              </form>
            </div>
            <div className="pt-2">
              <p className="text-xs text-neutral-500">{t('explore.chat.autoSave')}</p>
            </div>
          </div>
          </div>
        </div>
        </div>
      </div>
      </div>
    </div>
  );
}
