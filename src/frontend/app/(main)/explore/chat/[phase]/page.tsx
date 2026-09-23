'use client';

import { useState, useEffect, useLayoutEffect, useRef, useCallback, useMemo } from 'react';
import { useRouter, useParams, usePathname, useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import { motion } from 'framer-motion';
import {
  ChevronRight,
  ChevronDown,
  ArrowUp,
  Square,
  Copy,
  FileText,
} from 'lucide-react';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import DimensionConclusionCard, { type DimensionConclusionData } from '@/components/explore/DimensionConclusionCard';
import ConclusionRequestButton, { type ConclusionRequestState } from '@/components/explore/ConclusionRequestButton';
import PhaseCompleteWarmModal from '@/components/explore/PhaseCompleteWarmModal';
import PhaseWelcomeModal from '@/components/explore/PhaseWelcomeModal';
import TrialLimitModal from '@/components/explore/TrialLimitModal';
import ContinueConfirmModal from '@/components/explore/ContinueConfirmModal';
import UpgradeTrialModal from '@/components/payment/UpgradeTrialModal';
import PurchaseModal from '@/components/payment/PurchaseModal';
import ChatPhaseBackground from '@/components/explore/ChatPhaseBackground';
import LegacyBrowserNotice from '@/components/layout/LegacyBrowserNotice';
import { useChatAppearanceAttrs } from '@/lib/explore/useChatAppearanceAttrs';
const PhaseCelebrateBurst = dynamic(
  () => import('@/components/explore/PhaseCelebrateBurst'),
  { ssr: false },
);
const ChatPhaseSidebar = dynamic(
  () => import('@/components/explore/ChatPhaseSidebar'),
  { ssr: false },
);
// 沉淀阶段无条件走 v4 独立组件树（v3 前端已删除）
const RuminationV4Entry = dynamic(
  () => import('@/components/explore/RuminationV4Entry'),
  { ssr: false },
);
const ChatUiPreview = dynamic(
  () => import('@/components/explore/ChatUiPreview'),
  { ssr: false },
);
import { copyToClipboard } from '@/lib/utils/clipboard';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
import {
  PHASES,
  PHASE_ESTIMATE_MINUTES,
  loadSession,
  saveSession,
  getActivationSessionId,
  setActivationSessionId,
  readActivationSessionIdFromActivationApi,
  unlockNextPhase,
  getLastActivationCode,
  setLastActivationCode,
  applyExploreResumeToSession,
  getUserSurveyCompleted,
  setPhaseEnterTimestamp,
  getPhaseEnterTimestamp,
  clearPhaseEnterTimestamp,
  isPhaseWelcomeDismissed,
  setPhaseWelcomeDismissed,
  type PhaseKey,
  type ExploreSession,
} from '@/lib/explore/session';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';
import { deleteThreadBackendFirst } from '@/lib/explore/sessionRecovery';
import {
  getThreads,
  setThreadsForPhase,
  saveThread,
  addThread,
  removeThread,
  getActiveThreadId,
  setActiveThreadId,
  createThreadId,
  isCacheStale,
  type ChatThread,
  type ThreadMessage,
} from '@/lib/explore/threads';
import { useLocale } from '@/hooks/useLocale';
import { useAuthStore } from '@/stores/authStore';
import { createAdminSavepoint, fetchAdminSystemSettings } from '@/lib/api/admin';

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

function lastDimensionConclusionMessage<T extends { type?: string }>(msgs: T[]): T | undefined {
  const list = msgs.filter((m) => m.type === 'dimension_conclusion');
  return list.length ? list[list.length - 1] : undefined;
}

/** 试用拦截类型：limit=试用 10 轮用完；locked=试用码进非价值观阶段 */
type TrialBlockKind = 'limit' | 'locked';

/** 402 试用拦截信息：kind + 是否有可用来消耗升级的自购未绑定码（后端随 detail 下发） */
type TrialBlock = { kind: TrialBlockKind; hasUpgradeCodes: boolean };

/**
 * 解析 402 试用拦截错误。detail 可能是 JSON 字符串也可能是已解析对象，两种都兼容；
 * 非试用拦截返回 null。has_upgrade_codes 缺省（旧后端）按 false 处理，只引导购买。
 */
function parseTrialBlock(detail: unknown): TrialBlock | null {
  let obj: unknown = detail;
  if (typeof detail === 'string') {
    try {
      obj = JSON.parse(detail);
    } catch {
      return null;
    }
  }
  const rec = obj as { type?: unknown; has_upgrade_codes?: unknown } | null;
  const kind =
    rec?.type === 'trial_limit_reached' ? 'limit' : rec?.type === 'trial_phase_locked' ? 'locked' : null;
  if (!kind) return null;
  return { kind, hasUpgradeCodes: rec?.has_upgrade_codes === true };
}

/** 解析 403 邮箱未验证拦截（detail 兼容 JSON 字符串 / 已解析对象） */
function isEmailNotVerifiedBlock(detail: unknown): boolean {
  let obj: unknown = detail;
  if (typeof detail === 'string') {
    try {
      obj = JSON.parse(detail);
    } catch {
      return false;
    }
  }
  return (obj as { type?: unknown } | null)?.type === 'email_not_verified';
}

/**
 * 解析空回复失败（后端自动重试后仍空 content 下发的 error，2026-09-21 空回复事故修复）。
 * 兼容两种下发形态：payload 顶层带 type，或 payload.error 为 JSON 字符串/对象。
 */
function isEmptyResponseBlock(detail: unknown): boolean {
  const check = (obj: unknown): boolean => {
    let o = obj;
    if (typeof o === 'string') {
      try {
        o = JSON.parse(o);
      } catch {
        return false;
      }
    }
    return (o as { type?: unknown } | null)?.type === 'empty_response';
  };
  if (check(detail)) return true;
  const err = (detail as { error?: unknown } | null)?.error;
  return err !== undefined && err !== null ? check(err) : false;
}

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
      conclusionLocked: false,
      createdAt: now,
    },
  ];
}

export default function ChatPhasePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const phase = params.phase as PhaseKey;
  const uiPreviewEnabled =
    process.env.NODE_ENV === 'development' &&
    searchParams.get('ui_preview') === '1' &&
    PHASES.some((item) => item.key === phase);

  if (uiPreviewEnabled) {
    const previewState = searchParams.get('preview_state') || 'conversation';
    return <ChatUiPreview key={`${phase}:${previewState}`} phase={phase} previewState={previewState} />;
  }

  // 沉淀阶段：无条件走 v4 独立组件树（v3 实现已删除）
  if (phase === 'rumination') {
    return <RuminationV4Entry />;
  }

  return <LiveChatPhasePage />;
}

function LiveChatPhasePage() {
  const router = useRouter();
  const params = useParams();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { t, locale } = useLocale();
  // Chat 外观（背景/气泡/排版等 data 属性），全局配置见 admin「外观配置」+ openlife-chat-appearance.css
  const { dataAttrs: chatAppearanceAttrs, style: chatAppearanceStyle } = useChatAppearanceAttrs();
  const phase = (params.phase as string) as PhaseKey;
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

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
  /** 流式进行中点其它会话：先确认再切换 */
  const [threadSwitchDialogOpen, setThreadSwitchDialogOpen] = useState(false);
  const [pendingSwitchThread, setPendingSwitchThread] = useState<ChatThread | null>(null);
  /** 阶段已提交锁定：首次进入时说明弹窗（可勾选不再提醒） */
  const [phaseLockNoticeOpen, setPhaseLockNoticeOpen] = useState(false);
  const [phaseLockNoticeDontRemind, setPhaseLockNoticeDontRemind] = useState(false);
  /** 同一次停留在本页内关闭过说明后不再弹出；离开再进入本阶段对话路由时会清空（见 pathname 逻辑） */
  const phaseLockNoticeShownKeyRef = useRef<string | null>(null);
  const prevPathnameForLockModalRef = useRef<string | null>(null);
  const [initLoading, setInitLoading] = useState(true);
  /** 删除线程进行中：防止 "load messages" effect 在删除后竞态触发新建线程 */
  const deleteInProgressRef = useRef(false);
  const [threadsFetched, setThreadsFetched] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  /** 空回复自动重试告知（后端推 retrying 事件时显示，流结束/出错即清除） */
  const [autoRetryNotice, setAutoRetryNotice] = useState(false);
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);
  const [conclusionLoading, setConclusionLoading] = useState(false);
  /** 后端已推送 llm_stream_end：主模型流式输出结束，尚在同一条 SSE 内做落盘/埋点等 */
  const [postLlmTailActive, setPostLlmTailActive] = useState(false);
  /** 已收到 conclusion_loading、结论卡尚未推送（与消息区 spinner 一致） */
  const [waitingForConclusionCardUi, setWaitingForConclusionCardUi] = useState(false);
  /** 手动出卡按钮（「对话结束无法进行下一步？点击这里」）的请求状态 */
  const [conclusionReqState, setConclusionReqState] = useState<ConclusionRequestState>('idle');
  const [adminDebugBypass, setAdminDebugBypass] = useState(false);
  const [savepointBusy, setSavepointBusy] = useState(false);
  const [savepointModalOpen, setSavepointModalOpen] = useState(false);
  const [savepointDraftName, setSavepointDraftName] = useState('');
  const [savepointDraftHint, setSavepointDraftHint] = useState('');
  const [savepointDraftMsgIndex, setSavepointDraftMsgIndex] = useState<number | null>(null);
  const [adminPolicyLoaded, setAdminPolicyLoaded] = useState(false);
  /** 已从 /simple-auth/journeys 拉取并对齐 localStorage 后，才用 unlockedPhases 做路由校验，避免刷新时先用陈旧缓存误跳转 */
  const [exploreResumeSynced, setExploreResumeSynced] = useState(false);
  /** 报告已解锁（explore_resume.report_unlocked）：整页只读回看历史，顶部提示条引导查看报告 */
  const [reportUnlocked, setReportUnlocked] = useState(false);
  const [stepLocked, setStepLocked] = useState(false);
  /** 报告里该 step 的 selected_session_id（与 /threads 里 selected: true 对齐），用于已锁定阶段下限制「完成并继续」 */
  const [reportSelectedThreadId, setReportSelectedThreadId] = useState<string | null>(null);
  const [phaseCelebrateSignal, setPhaseCelebrateSignal] = useState(0);
  const [phaseCompleteModalOpen, setPhaseCompleteModalOpen] = useState(false);
  /** 前四阶段「完成并继续」二次确认弹层（进入下一阶段后本阶段锁定不可修改） */
  const [continueConfirmOpen, setContinueConfirmOpen] = useState(false);
  /** 试用拦截弹层（402 trial_limit_reached / trial_phase_locked），非 null 时展示 */
  const [trialBlock, setTrialBlock] = useState<TrialBlock | null>(null);
  /** 购买引导：试用拦截弹层点「去购买」后打开现有 PurchaseModal */
  const [trialPurchaseOpen, setTrialPurchaseOpen] = useState(false);
  /** 消耗升级弹窗（ADR-0014）：拦截点「使用已有激活码升级」入口 */
  const [trialUpgradeOpen, setTrialUpgradeOpen] = useState(false);
  /** 完成弹窗"已专注 N 分钟"——由 handleConfirmConclusion 在打开弹窗前计算；null 时使用通用文案 */
  const [fatigueMinutes, setFatigueMinutes] = useState<number | null>(null);
  /** 进入新 phase 的时间预估欢迎卡（首次进入且未 dismiss 时弹出） */
  const [phaseWelcomeOpen, setPhaseWelcomeOpen] = useState(false);
  /** 防止"完成并继续"连点 / 多处导航竞态：导航中置 true，跳转完成后置 false */
  const isNavigatingRef = useRef(false);
  /** 同步 canContinue 到 ref，供异步回调读取最新值 */
  const canContinueRef = useRef(false);
  const { user } = useAuthStore();
  const userChatAvatarInitials = (user?.username || user?.email || 'U').slice(0, 2).toUpperCase();

  // 邮箱未验证：禁止进入探索对话（后端写端点统一 403 email_not_verified），回问卷页做验证引导
  useEffect(() => {
    if (user?.email && user.email_verified === false) {
      router.replace('/explore/survey');
    }
  }, [user, router]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);
  /** 为 true 时流式输出会滚到底部；用户上滑后为 false，点「回到底」再置 true */
  const stickToBottomRef = useRef(true);
  const messagesRef = useRef<ThreadMessage[]>([]);
  messagesRef.current = messages;
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  /** 防止同一个 (activationCode, phase) 多次触发自动新建线程（竞态 / effect 重复执行） */
  const autoInitGuardRef = useRef<string>('');

  const phaseMeta = {
    color: PHASE_COLORS[phase],
    desc: t(`explore.chat.phaseMeta.${phase}.desc`),
    hint: t(`explore.chat.phaseMeta.${phase}.hint`),
  };
  const phaseInfo = PHASES.find((p) => p.key === phase);
  const phaseLabel = t(`explore.chat.phaseLabels.${phase}`);
  const canCreateMoreThreads = !stepLocked && (adminDebugBypass || threads.length < 5);

  /** 仅在线程 id 集合变化时触发「加载消息」effect，避免因 threads 引用反复变（persist / save 后 getThreads）而重复 init */
  const threadListSignature = useMemo(() => threads.map((t) => t.id).join('|'), [threads]);

  /** 侧栏预览：当前选中线程的消息以 React state 为准（列表里的 thread 可能仍是 messages:[]） */
  const threadsForSidebar = useMemo(() => {
    if (!activeThreadId) return threads;
    return threads.map((th) => (th.id === activeThreadId ? { ...th, messages } : th));
  }, [threads, activeThreadId, messages]);

  const latestConclusionMessageId = lastDimensionConclusionMessage(messages)?.id;

  const mapHistoryToThreadMessages = useCallback(
    (history: any[], meta: any): ThreadMessage[] =>
      history.flatMap((m, i) => {
        // 跳过内部协议消息（system 角色：兜底重试/协议注入），不展示给用户
        if (m.role === 'system' || m.internal === true) return [];
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

        const base: ThreadMessage = {
          id,
          role: m.role as 'user' | 'assistant',
          content: m.content ?? '',
          createdAt,
        };
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

  // Auth & redirect — 强制等待 exploreResume 对齐后再做路由准入判断
  // 清缓存后 localStorage 为默认值，必须以后端 resume 为准，避免闪到 values 再跳转
  useEffect(() => {
    if (!adminPolicyLoaded) return;
    if (!PHASES.find((p) => p.key === phase)) {
      router.replace('/explore/activate');
      return;
    }
    const forcedCode = searchParams.get('code')?.trim() || null;
    if (forcedCode) {
      setLastActivationCode(forcedCode);
    }
    const code = forcedCode || getLastActivationCode();
    if (!code) {
      router.replace('/explore/activate');
      return;
    }
    setActivationCode(code);
    const s = loadSession(code);
    setSession(s);
    // 用户维度 + 激活码维度双检查，防止清缓存后误跳问卷
    if (!s?.surveyCompleted && !getUserSurveyCompleted()) {
      router.replace('/explore/survey');
      return;
    }
    // 未完成 resume 同步时，不执行阶段准入校验（等待 exploreResumeSynced 变为 true）
    if (!exploreResumeSynced) return;
    // resume 同步后，若 URL phase 不在 unlockedPhases 中，重定向到 currentPhase
    if (!adminDebugBypass && !s.unlockedPhases.includes(phase)) {
      router.replace(`/explore/chat/${s.currentPhase}`);
    }
  }, [phase, router, adminPolicyLoaded, adminDebugBypass, exploreResumeSynced, searchParams]);

  useEffect(() => {
    if (!activationCode || !phase) return;
    const targetThreadId = searchParams.get('thread_id')?.trim();
    if (!targetThreadId) return;
    setActiveThreadId(activationCode, phase, targetThreadId);
  }, [activationCode, phase, searchParams]);

  /**
   * phase / 激活码切换时，在 useEffect 批处理前将 threadsFetched 置为 false，
   * 并重置自动新建守卫，防止旧 guard 阻止新阶段的首次 init。
   * 否则「同步线程」effect 与「init」effect 同一次提交内先后执行时，init 仍可能读到上一阶段的 threadsFetched===true
   * 与旧 threads，误判为空并 createThreadId 新建会话。
   */
  useLayoutEffect(() => {
    if (!activationCode || !phase) return;
    setThreadsFetched(false);
    autoInitGuardRef.current = '';
    // 切换阶段时重置导航锁
    isNavigatingRef.current = false;
    // 记录进入该 phase 的时间戳，用于完成弹窗的"已专注约 N 分钟"疲劳提醒
    setPhaseEnterTimestamp(activationCode, phase);
  }, [activationCode, phase]);

  // 从后端同步线程列表（主数据源，支持跨设备）
  useEffect(() => {
    if (!activationCode || !phase) return;
    setThreadsFetched(false);
    setStepLocked(false);
    setReportSelectedThreadId(null);
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
          selected?: boolean;
        }>;
        const selectedTid = raw.find((t) => t.selected)?.id ?? null;
        if (!cancelled) setReportSelectedThreadId(selectedTid);
        const list: ChatThread[] = raw.map((t) => ({
          id: t.id,
          title: t.title,
          status: t.status as 'in-progress' | 'completed',
          messages: [],
          createdAt: t.createdAt,
          dimensionConclusion: t.dimensionConclusion,
        }));
        // 为每个会话预加载历史，侧栏显示首行与轮数。
        let lastActivationSessionFromApi: string | undefined;
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
            const actSid = readActivationSessionIdFromActivationApi(h.data?.activation);
            if (actSid) lastActivationSessionFromApi = actSid;
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

        const mergedList = await Promise.all(list.map((th) => hydrateThreadFromHistory(th)));
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
          if (lastActivationSessionFromApi) {
            setBackendSessionId(lastActivationSessionFromApi);
            const s = loadSession(activationCode);
            saveSession(setActivationSessionId(s, lastActivationSessionFromApi));
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
          const list = getThreads(activationCode, phase);
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

  // 激活线程切换：优先直接使用已预加载内容；仅在”完全首次进入且无会话”时才触发 init。
  // autoInitGuardRef（声明在组件顶部）确保每组 (activationCode, phase) 只触发一次 init。
  useEffect(() => {
    if (!activationCode || !phase || !threadsFetched) return;
    // 删除线程期间不触发加载逻辑，避免竞态导致误建新线程
    if (deleteInProgressRef.current) return;
    let cancelled = false;
    setInitLoading(true);

    const list = threads;
    const activeId = activeThreadId;

    if (list.length === 0) {
      // 后端 /threads 已确认空：直接新建线程，禁止无 thread_id 的 history fallback（防 act_sid 幽灵恢复）
      const guardKey = `${activationCode}::${phase}`;
      if (autoInitGuardRef.current === guardKey) {
        setInitLoading(false);
        return;
      }
      autoInitGuardRef.current = guardKey;

      (async () => {
        try {
          const tid = createThreadId();
          const initRes = await apiClient.post('/simple-chat/init', {
            activation_code: activationCode,
            phase: BACKEND_PHASE[phase],
            thread_id: tid,
            locale: locale === 'en' ? 'en' : 'zh',
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
            title: '对话 1',
            status: 'in-progress',
            messages: msgs,
            createdAt: now,
          };
          if (!cancelled) {
            {
              addThread(activationCode, phase, thread);
              setThreads(getThreads(activationCode, phase));
              setActiveThreadId(activationCode, phase, tid);
              setActiveThreadIdState(tid);
              setBackendSyncedThreadId(tid);
              setMessages(msgs);
            }
            const sid = readActivationSessionIdFromActivationApi(initRes.data?.activation);
            if (sid) {
              setBackendSessionId(sid);
              const s = loadSession(activationCode);
              saveSession(setActivationSessionId(s, sid));
            }
          }
        } catch (initErr: any) {
          if (!cancelled) {
            // 试用码出卡确认后进入下一阶段：init 被 402 trial_phase_locked 拦截，
            // 与超 10 轮一样弹购买/升级引导层，而不是笼统的「初始化失败」
            const block = parseTrialBlock(
              initErr?.response?.data?.detail ?? initErr?.response?.data?.message
            );
            if (block) {
              setTrialBlock(block);
            } else {
              setChatError(getApiErrorMessage(initErr, '初始化失败，请刷新后重试'));
            }
          }
        } finally {
          if (!cancelled) setInitLoading(false);
        }
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
                locale: locale === 'en' ? 'en' : 'zh',
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
                // 同上：试用码进非价值观阶段 init 402 → 弹购买/升级引导层
                const block = parseTrialBlock(
                  err?.response?.data?.detail ?? err?.response?.data?.message
                );
                if (block) {
                  setTrialBlock(block);
                } else {
                  setChatError(getApiErrorMessage(err, '初始化失败，请刷新后重试'));
                }
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
  }, [
    activationCode,
    phase,
    threadsFetched,
    threadListSignature,
    activeThreadId,
    mapHistoryToThreadMessages,
    t,
    locale,
  ]);

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
  /** 末条结论卡未表态：须点「确认」或「再聊聊」；不区分是否管理员 */
  const pendingConclusionChoiceBlocksChat =
    !isSelectedCompleted &&
    (() => {
      const last = lastDimensionConclusionMessage(messages);
      return !!(last && !last.conclusionCollapsed && !last.conclusionConfirmed);
    })();
  /** 手动出卡按钮：四阶段、满 11 轮用户消息、当前无待表态结论卡（从未出过，或已「再聊聊」折叠）时显示 */
  const userTurnCount = useMemo(
    () => messages.filter((m) => m.role === 'user').length,
    [messages]
  );
  const showConclusionRequestButton =
    !isSelectedCompleted &&
    !reportUnlocked &&
    !pendingConclusionChoiceBlocksChat &&
    !lastDimensionConclusionMessage(messages)?.conclusionConfirmed &&
    userTurnCount >= 11;
  const isReadOnly =
    // 报告已解锁：探索收口，整页只读（顶部提示条引导查看报告）
    reportUnlocked ||
    isSelectedCompleted ||
    (stepLocked && !adminDebugBypass) || // 阶段已锁定，普通用户只读
    (!isBackendSynced && !!activeThreadId) || // 切到其它 thread 时暂不输入（未同步）
    pendingConclusionChoiceBlocksChat;
  const selectionMatchesReportForContinue = !stepLocked
    ? true
    : !!reportSelectedThreadId && activeThreadId === reportSelectedThreadId;

  /**
   * threadsFetched 未完成前，stepLocked/reportSelectedThreadId 尚未从后端同步，
   * 此时 canContinue 可能基于初始值（false/null）误判为 true。
   * 加上 threadsFetched 门控，确保后端状态已就绪后才允许"完成并继续"。
   */
  const canContinue =
    threadsFetched &&
    !!selectedThread &&
    (isSelectedCompleted || (stepLocked && selectionMatchesReportForContinue)) &&
    selectionMatchesReportForContinue;

  canContinueRef.current = canContinue;

  const continueDisabledHint = useMemo(() => {
    if (canContinue) return '';
    if (!threadsFetched) return '';
    if (!selectedThread) return t('explore.chat.selectCompletedHint');
    if (stepLocked && reportSelectedThreadId && activeThreadId !== reportSelectedThreadId) {
      return t('explore.chat.selectSubmittedThreadHint');
    }
    return t('explore.chat.selectCompletedHint');
  }, [
    canContinue,
    threadsFetched,
    selectedThread,
    stepLocked,
    adminDebugBypass,
    reportSelectedThreadId,
    activeThreadId,
    t,
  ]);

  /** 本阶段已提交：普通用户仅可点「完成并继续」，主输入区与侧栏新建等置灰 */
  const phaseInteractionLocked = stepLocked && !adminDebugBypass;
  const canUseAdminSavepoint =
    Boolean(user?.is_super_admin) &&
    adminDebugBypass &&
    Boolean(activationCode) &&
    Boolean(activeThreadId);

  const handleOpenSavepointModal = useCallback(
    (msg: ThreadMessage, fullMessageIndex: number) => {
      if (!canUseAdminSavepoint || !activationCode || !activeThreadId) return;
      const defaultName = `${phase}-sp-${new Date().toISOString().slice(0, 16).replace('T', ' ')}`;
      setSavepointDraftName(defaultName);
      setSavepointDraftHint((msg.content || '').trim().slice(0, 120));
      setSavepointDraftMsgIndex(Math.max(0, fullMessageIndex));
      setSavepointModalOpen(true);
    },
    [activationCode, activeThreadId, canUseAdminSavepoint, phase],
  );

  const handleCreateSavepoint = useCallback(async () => {
    if (!canUseAdminSavepoint || !activationCode || !activeThreadId) return;
    if (savepointBusy) return;
    if (savepointDraftMsgIndex == null) return;
    const displayName = savepointDraftName.trim();
    if (!displayName) {
      alert('请填写检查点名称');
      return;
    }
    setSavepointBusy(true);
    try {
      await createAdminSavepoint({
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: activeThreadId,
        target_message_index: savepointDraftMsgIndex,
        display_name: displayName,
        expected_hint: savepointDraftHint.trim() || undefined,
      });
      setSavepointModalOpen(false);
      alert(`Savepoint 已创建：${displayName}`);
    } catch (e: unknown) {
      alert(getApiErrorMessage(e, '创建 Savepoint 失败'));
    } finally {
      setSavepointBusy(false);
    }
  }, [
    activationCode,
    activeThreadId,
    canUseAdminSavepoint,
    phase,
    savepointBusy,
    savepointDraftHint,
    savepointDraftMsgIndex,
    savepointDraftName,
  ]);

  /** 流式请求中：仅在 LLM 段结束后的尾部阶段展示（与输入框上方 status 行文案一致、分结论卡/假设生成/其它） */
  const streamTailInputPlaceholder = useMemo(() => {
    if (!sending) return null;
    if (waitingForConclusionCardUi) return t('explore.chat.streamStatusConclusion');
    if (postLlmTailActive) return t('explore.chat.streamStatusGeneric');
    return null;
  }, [sending, waitingForConclusionCardUi, postLlmTailActive, t]);

  useLayoutEffect(() => {
    const prev = prevPathnameForLockModalRef.current;
    prevPathnameForLockModalRef.current = pathname;
    const chatPath = `/explore/chat/${phase}`;
    if (pathname === chatPath && prev !== chatPath && phaseInteractionLocked) {
      phaseLockNoticeShownKeyRef.current = null;
    }
  }, [pathname, phase, phaseInteractionLocked]);

  useEffect(() => {
    if (!phaseInteractionLocked) {
      setPhaseLockNoticeOpen(false);
      setPhaseLockNoticeDontRemind(false);
      return;
    }
    // 报告已解锁走只读提示条，不再弹「阶段已提交」说明窗
    if (reportUnlocked) return;
    if (user?.is_super_admin) return;
    if (!activationCode || !threadsFetched || initLoading) return;
    if (typeof window === 'undefined') return;
    try {
      if (localStorage.getItem(`bd_phase_lock_notice_hide_${activationCode}`) === '1') {
        return;
      }
    } catch {
      /* private mode */
    }
    const key = `${activationCode}::${phase}`;
    if (phaseLockNoticeShownKeyRef.current === key) return;
    phaseLockNoticeShownKeyRef.current = key;
    setPhaseLockNoticeOpen(true);
  }, [phaseInteractionLocked, reportUnlocked, activationCode, phase, threadsFetched, initLoading, user?.is_super_admin]);

  const dismissPhaseLockNotice = useCallback(
    (dontRemind: boolean, navigateNext: boolean) => {
      if (activationCode && dontRemind) {
        try {
          localStorage.setItem(`bd_phase_lock_notice_hide_${activationCode}`, '1');
        } catch {
          /* ignore */
        }
      }
      setPhaseLockNoticeOpen(false);
      setPhaseLockNoticeDontRemind(false);
      if (navigateNext) {
        if (!activationCode || !session) return;
        if (isNavigatingRef.current) {
          console.warn('[dismissPhaseLockNotice] 导航中，忽略重复导航');
          return;
        }
        if (!canContinueRef.current) return;
        // 去重保护：session 已前进则不再重复 push
        if (session.currentPhase !== phase) {
          console.warn('[dismissPhaseLockNotice] session 已前进，改为跳转到当前阶段', {
            sessionPhase: session.currentPhase,
            urlPhase: phase,
          });
          router.push(`/explore/chat/${session.currentPhase}`);
          return;
        }
        isNavigatingRef.current = true;
        console.log('[dismissPhaseLockNotice] 开始导航', { phase });
        try {
          const updated = unlockNextPhase({ ...session, currentPhase: phase });
          saveSession(updated);
          setSession(updated);
          router.push(`/explore/transition?from=${phase}`);
        } catch (err) {
          console.error('[dismissPhaseLockNotice] 导航异常', err);
          isNavigatingRef.current = false;
        }
      }
    },
    [activationCode, phase, session, router]
  );

  // ── 核心修复：清缓存后强制以 explore_resume 覆盖本地阶段 ──
  // 无论 localStorage 是否有数据，初始化时都从后端拉取真实进度，
  // 再做路由准入。已完成同步后 setExploreResumeSynced(true) 放行 Auth & redirect。
  useEffect(() => {
    if (!adminPolicyLoaded) return;
    if (adminDebugBypass) {
      setExploreResumeSynced(true);
      return;
    }
    if (!activationCode) return;

    let cancelled = false;
    setExploreResumeSynced(false);
    setReportUnlocked(false);

    void (async () => {
      try {
        const resume = await fetchExploreResumeFromJourneys(activationCode);
        if (cancelled) return;
        setReportUnlocked(Boolean(resume?.report_unlocked));
        // 始终用后端 resume 覆盖本地阶段（清缓存后本地为默认值 values）
        const s = loadSession(activationCode);
        const next = resume?.resume_phase
          ? applyExploreResumeToSession(s, resume)
          : s;
        saveSession(next);
        setSession(next);
        // 路由准入：若 URL phase 未解锁，重定向到 resume_phase
        if (resume?.resume_phase) {
          const rp = resume.resume_phase as PhaseKey;
          if (PHASES.some((p) => p.key === rp) && !next.unlockedPhases.includes(phaseRef.current)) {
            router.replace(`/explore/chat/${rp}`);
          }
        }
      } finally {
        if (!cancelled) setExploreResumeSynced(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activationCode, adminDebugBypass, adminPolicyLoaded, router]);

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
  }, [messages, sending]);

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

  // 发送完成后将焦点还给输入框，支持连续 Enter 对话无需再点鼠标。
  useEffect(() => {
    if (!sending && !isReadOnly) {
      inputRef.current?.focus();
    }
  }, [sending, isReadOnly]);

  // 兜底：避免初始化请求异常时长期停留在”正在准备中”
  useEffect(() => {
    if (!initLoading) return;
    const timer = window.setTimeout(() => {
      setInitLoading(false);
      setChatError((prev) => prev || t('explore.chat.initTimeout'));
    }, 45000);
    return () => window.clearTimeout(timer);
  }, [initLoading, t]);

  const handleSend = async (
    prefill?: string,
    skipAddUser?: boolean
  ) => {
    const text = prefill ?? input.trim();
    if (!activationCode || !text || sending || isReadOnly || conclusionReqState === 'loading')
      return;
    setMessages((prev) => {
      const lastIdx = [...prev].map((m) => m.type).lastIndexOf('dimension_conclusion');
      if (lastIdx < 0) return prev;
      const last = prev[lastIdx];
      if (!last || last.type !== 'dimension_conclusion' || last.conclusionLocked) return prev;
      const next = [...prev];
      next[lastIdx] = { ...last, conclusionLocked: true };
      return next;
    });
    if (!prefill) setInput('');
    const now = Date.now();
    const messageForApi = text;
    const userMsg: ThreadMessage = {
      id: `u_${now}`,
      role: 'user',
      content: text,
      createdAt: now,
    };
    const assistantId = `a_${now}`;
    const assistantMsg: ThreadMessage = {
      id: assistantId,
      role: 'assistant' as const,
      content: '',
      createdAt: now,
    };
    const toAdd = skipAddUser
      ? [assistantMsg]
      : [userMsg, assistantMsg];
    setMessages((prev) => [...prev, ...toAdd]);
    setChatError(null);
    setConclusionLoading(false);
    setPostLlmTailActive(false);
    setWaitingForConclusionCardUi(false);
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
      const uiSnap = (() => {
        const last = lastDimensionConclusionMessage(messages);
        if (!last) return undefined;
        return {
          latest_card_message_id: last.id,
          refine_active: !!last.conclusionCollapsed,
          confirmed: !!last.conclusionConfirmed,
        };
      })();
      const apiLocale = locale === 'en' ? 'en' : 'zh';
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
            activation_session_id: getActivationSessionId(session),
            locale: apiLocale,
            ...(uiSnap ? { client_conclusion_ui: uiSnap } : {}),
          }),
          signal: controller.signal,
        });

      let res = await doStreamFetch(token);
      if (res.status === 401) {
        try {
          // 统一走 single-flight，避免与拦截器并发 refresh 触发后端重放检测
          const nextToken = await apiClient.refreshAccessToken();
          if (nextToken) {
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
        let detail: unknown = '';
        try {
          const errPayload = await res.json();
          detail = errPayload?.detail || errPayload?.message || '';
        } catch {}
        // 试用拦截（402）：不落地错误气泡，直接弹购买引导层，终止本次发送
        if (res.status === 402) {
          const block = parseTrialBlock(detail);
          if (block) {
            setTrialBlock(block);
            return;
          }
        }
        // 邮箱未验证拦截（403）：回问卷页做验证引导
        if (res.status === 403 && isEmailNotVerifiedBlock(detail)) {
          router.replace('/explore/survey');
          return;
        }
        const detailMsg = typeof detail === 'string' ? detail : '';
        throw new Error(detailMsg || `请求失败（${res.status}）`);
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
              // SSE 内嵌试用拦截（防御：后端也可能以流内 error + type 下发）
              const block = parseTrialBlock(payload);
              if (block) {
                setTrialBlock(block);
              } else if (isEmailNotVerifiedBlock(payload)) {
                router.replace('/explore/survey');
              } else if (isEmptyResponseBlock(payload)) {
                // 后端自动重试后仍空回复：友好文案 + 手动重试按钮
                setChatError(t('explore.chat.emptyResponseError'));
              } else {
                setChatError(String(payload.error));
              }
              setAutoRetryNotice(false);
              reader.cancel();
              break;
            }
            if (payload.retrying) {
              // 空回复自动重试告知：重置当前气泡 + 显示「再想想」提示
              setAutoRetryNotice(true);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: '', thinkStreaming: false, thinkChunkContent: undefined }
                    : m
                )
              );
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
            if (payload.llm_stream_end) {
              setPostLlmTailActive(true);
            }
            if (payload.conclusion_loading) {
              setConclusionLoading(true);
              setWaitingForConclusionCardUi(true);
            }
            if (payload.dimension_conclusion) {
              assistantHasVisibleOutput = true;
              setConclusionLoading(false);
              setWaitingForConclusionCardUi(false);
              const concl = payload.dimension_conclusion as DimensionConclusionData;
              const conclMsg: ThreadMessage = {
                id: `concl_${Date.now()}`,
                role: 'assistant',
                content: '',
                type: 'dimension_conclusion',
                conclusionData: concl,
                conclusionCollapsed: false,
                conclusionConfirmed: false,
                conclusionLocked: false,
                createdAt: Date.now(),
              };
              setMessages((prev) => {
                const frozenHistory = prev.map((m) =>
                  m.type === 'dimension_conclusion' ? { ...m, conclusionLocked: true } : m
                );
                return [...frozenHistory, conclMsg];
              });
            }
            if (payload.done && payload.response != null) {
              fullReply = payload.response;
              if (String(payload.response || '').trim()) assistantHasVisibleOutput = true;
              const doneAt = Date.now();
              setAutoRetryNotice(false);
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
      setPostLlmTailActive(false);
      setWaitingForConclusionCardUi(false);
      setAutoRetryNotice(false);
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
      if (sending) {
        setPendingSwitchThread(thread);
        setThreadSwitchDialogOpen(true);
        return;
      }
      performThreadSwitch(thread);
    },
    [
      activationCode,
      phase,
      activeThreadId,
      sending,
      performThreadSwitch,
    ]
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
    performThreadSwitch(target, {
      messagesSnapshot: snapMessages,
      threadsSnapshot: snapThreads,
    });
    setThreadSwitchDialogOpen(false);
    setPendingSwitchThread(null);
  }, [pendingSwitchThread, activationCode, phase, messages, threads, performThreadSwitch]);

  const handleNewChat = async () => {
    if (!activationCode || !phase) return;
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
        locale: locale === 'en' ? 'en' : 'zh',
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

  const handlePhaseCompleteModalContinue = useCallback((dontRemind?: boolean) => {
    /** 按 activationCode 全局持久化"不再提醒"（五阶段均生效） */
    if (activationCode && dontRemind) {
      try {
        localStorage.setItem(`bd_phase_complete_dismiss_${activationCode}`, '1');
      } catch {
        /* private mode */
      }
    }
    setPhaseCompleteModalOpen(false);
    // 清除 phase 进入时间戳，避免下次进入误算
    if (activationCode && phase) {
      clearPhaseEnterTimestamp(activationCode, phase);
    }
  }, [activationCode, phase]);

  /** 手动出卡：「对话结束无法进行下一步？点击这里」按钮 → POST /simple-chat/conclusion/request */
  const handleRequestConclusion = async () => {
    if (conclusionReqState === 'loading' || sending) return;
    if (!activationCode || !phase) return;
    const targetThreadId = activeThreadId || backendSyncedThreadId;
    if (!targetThreadId) return;
    setConclusionReqState('loading');
    const insertConclusionCard = (concl: DimensionConclusionData) => {
      const conclMsg: ThreadMessage = {
        id: `concl_${Date.now()}`,
        role: 'assistant',
        content: '',
        type: 'dimension_conclusion',
        conclusionData: concl,
        conclusionCollapsed: false,
        conclusionConfirmed: false,
        conclusionLocked: false,
        createdAt: Date.now(),
      };
      setMessages((prev) => {
        // 防重：已存在未表态（未折叠/未确认）的卡则不再插入
        const last = lastDimensionConclusionMessage(prev);
        if (last && !last.conclusionCollapsed && !last.conclusionConfirmed) return prev;
        const frozenHistory = prev.map((m) =>
          m.type === 'dimension_conclusion' ? { ...m, conclusionLocked: true } : m
        );
        return [...frozenHistory, conclMsg];
      });
    };
    // 失败自愈：端点先写盘后响应，响应丢失（刷新/导航/代理中断）时卡其实已生成，
    // 拉一次 history 检查，已生成就直接补卡，避免误报「生成失败」
    const recoverFromHistory = async (): Promise<boolean> => {
      try {
        const h = await apiClient.get('/simple-chat/history', {
          params: { activation_code: activationCode, phase: BACKEND_PHASE[phase], thread_id: targetThreadId },
        });
        const meta = h.data?.metadata ?? {};
        const draft = meta?.conclusion_draft;
        if (meta?.conclusion_state === 'pending' && draft && typeof draft === 'object') {
          insertConclusionCard(draft as DimensionConclusionData);
          return true;
        }
      } catch {
        // 自愈失败按真失败处理
      }
      return false;
    };
    try {
      const res = await apiClient.post('/simple-chat/conclusion/request', {
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: targetThreadId,
      });
      const concl = res.data?.data?.dimension_conclusion as DimensionConclusionData | undefined;
      if (res.data?.code === 200 && concl) {
        insertConclusionCard(concl);
        setConclusionReqState('idle');
      } else {
        setConclusionReqState((await recoverFromHistory()) ? 'idle' : 'error');
      }
    } catch (e) {
      console.warn('[RequestConclusion] failed:', e);
      setConclusionReqState((await recoverFromHistory()) ? 'idle' : 'error');
    }
  };

  // 切换对话/阶段时复位手动出卡按钮状态
  useEffect(() => {
    setConclusionReqState('idle');
  }, [activeThreadId, phase]);

  const handleConfirmConclusion = async () => {
    if (stepLocked && !adminDebugBypass) return;
    if (!activationCode || !phase) return;
    const targetThreadId = activeThreadId || backendSyncedThreadId;
    if (!targetThreadId) return;
    const th = threads.find((t) => t.id === targetThreadId) || selectedThread;
    if (!th) return;
    const lastConcl = lastDimensionConclusionMessage(messages);
    if (!lastConcl?.conclusionData) return;
    console.log('[ConfirmConclusion] 调用 thread/complete API', { phase, threadId: targetThreadId });
    let threadCompleteOk = false;
    try {
      const res = await apiClient.post('/simple-chat/thread/complete', {
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: targetThreadId,
      });
      threadCompleteOk = res.data?.code === 200;
      console.log('[ConfirmConclusion] thread/complete API 返回', { ok: threadCompleteOk, phase, threadId: targetThreadId });
    } catch (e) {
      console.warn('[ConfirmConclusion] thread/complete API failed:', e);
    }
    const confirmedMessages = messages.map((m) =>
      m.type === 'dimension_conclusion'
        ? { ...m, conclusionConfirmed: true, conclusionCollapsed: false, conclusionLocked: true }
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

    setPhaseCelebrateSignal((n) => n + 1);

    /** 与庆祝粒子一致：本地确认后即弹出祝贺层 */
    let skipModal = false;
    if (!adminDebugBypass && activationCode) {
      try {
        skipModal = localStorage.getItem(`bd_phase_complete_dismiss_${activationCode}`) === '1';
      } catch {
        /* private mode */
      }
    }
    if (!skipModal) {
      // 在打开弹窗前计算"已专注约 N 分钟"（保守值，最低 1 分钟；时间戳缺失则 null 走通用文案）
      if (activationCode && phase) {
        const ts = getPhaseEnterTimestamp(activationCode, phase);
        if (ts) {
          const mins = Math.max(1, Math.round((Date.now() - ts) / 60000));
          setFatigueMinutes(Number.isFinite(mins) ? mins : null);
        } else {
          setFatigueMinutes(null);
        }
      }
      setPhaseCompleteModalOpen(true);
    }

  };

  /**
   * 进入新 phase 的时间预估欢迎卡：
   * 仅在 (a) 已有 activationCode/phase，(b) 初始化完成（!initLoading），
   * (c) 阶段未锁定（!phaseInteractionLocked），(d) 该 phase 尚未显示过欢迎卡（每个激活码+phase 只显示一次）时弹出。
   * 与 phaseLockNotice（z-57, locked 时弹）和 PhaseCompleteModal（确认结论卡触发）天然互斥。
   */
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!activationCode || !phase) return;
    if (initLoading) return;
    if (phaseInteractionLocked) return;
    if (isPhaseWelcomeDismissed(activationCode, phase)) return;
    setPhaseWelcomeOpen(true);
  }, [activationCode, phase, initLoading, phaseInteractionLocked]);

  /** 关闭欢迎卡即按 激活码+phase 持久化已读，之后重新进入该 phase 不再弹出 */
  const handlePhaseWelcomeClose = useCallback(() => {
    if (activationCode && phase) {
      setPhaseWelcomeDismissed(activationCode, phase, true);
    }
    setPhaseWelcomeOpen(false);
  }, [activationCode, phase]);

  const handleContinueChat = async (conclusionMsg?: ThreadMessage) => {
    if (stepLocked && !adminDebugBypass) return;
    const lastConcl = lastDimensionConclusionMessage(messages);
    const toCollapse = conclusionMsg ?? lastConcl;
    if (
      toCollapse &&
      toCollapse.type === 'dimension_conclusion' &&
      lastConcl &&
      toCollapse.id !== lastConcl.id
    ) {
      return;
    }
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

  /**
   * "完成并继续"统一入口：所有非沉淀阶段的导航汇聚在此。
   * 防护：isNavigatingRef 防连点 / 重复 push；canContinueRef 读取最新值避免闭包陈旧；
   * 日志：链路可追踪（点击→API→session 写入→跳转）。
   */
  const handleCompleteAndContinue = useCallback(() => {
    if (!activationCode) {
      setChatError('激活码上下文丢失，请返回激活页重新进入');
      return;
    }
    let sessionSnapshot = session;
    if (!sessionSnapshot) {
      // 防止极端情况下 session state 丢失导致“按钮可点但点击无响应”
      try {
        sessionSnapshot = loadSession(activationCode);
        setSession(sessionSnapshot);
      } catch {
        setChatError('会话状态读取失败，请刷新页面后重试');
        return;
      }
    }
    // 防连点：上一轮导航尚未完成时忽略
    if (isNavigatingRef.current) {
      console.warn('[CompleteAndContinue] 导航中，忽略重复点击');
      return;
    }
    // 兼容极端竞态：按钮状态来自 canContinue，而回调内优先读 ref；
    // 两者瞬时不一致时，允许按 canContinue 兜底继续，避免“可点击但无响应”。
    const canContinueNow = canContinueRef.current || canContinue;
    if (!canContinueNow) {
      console.warn('[CompleteAndContinue] canContinue 为 false，忽略点击', {
        canContinueRef: canContinueRef.current,
        canContinueState: canContinue,
        threadsFetched,
        selectedThreadId: selectedThread?.id || null,
        selectedThreadStatus: selectedThread?.status || null,
        stepLocked,
        reportSelectedThreadId,
        activeThreadId,
      });
      setChatError(continueDisabledHint || '当前线程尚未满足“完成并继续”条件');
      return;
    }
    // 去重保护：如果 session 的 currentPhase 已经不是当前 URL phase，说明已经前进过
    if (sessionSnapshot.currentPhase !== phase) {
      console.warn('[CompleteAndContinue] session.currentPhase !== url phase，改为跳转到当前阶段', {
        sessionPhase: sessionSnapshot.currentPhase,
        urlPhase: phase,
      });
      router.push(`/explore/chat/${sessionSnapshot.currentPhase}`);
      return;
    }
    isNavigatingRef.current = true;
    console.log('[CompleteAndContinue] 开始导航', { phase, sessionPhase: sessionSnapshot.currentPhase });
    try {
      // unlockNextPhase 内部会 saveSession
      const updated = unlockNextPhase({ ...sessionSnapshot, currentPhase: phase });
      setSession(updated);
      console.log('[CompleteAndContinue] session 已更新', {
        prevPhase: phase,
        nextPhase: updated.currentPhase,
        unlockedPhases: updated.unlockedPhases,
      });
      router.push(`/explore/transition?from=${phase}`);
      // App Router push 为异步且无 Promise，防止偶发未跳转时导航锁卡死。
      window.setTimeout(() => {
        isNavigatingRef.current = false;
      }, 1800);
    } catch (err) {
      console.error('[CompleteAndContinue] 导航异常', err);
      isNavigatingRef.current = false;
      setChatError('跳转失败，请刷新页面后重试');
    }
  }, [
    activationCode,
    session,
    phase,
    canContinue,
    threadsFetched,
    selectedThread,
    stepLocked,
    reportSelectedThreadId,
    activeThreadId,
    continueDisabledHint,
    setSession,
    router,
    setChatError,
  ]);

  /**
   * 前四阶段「完成并继续」点击入口：先弹二次确认（进入下一阶段后本阶段锁定、不可返回修改）。
   * 已提交锁定（stepLocked）的阶段本就已不可逆，跳过弹层直接导航。
   */
  const handleRequestCompleteAndContinue = useCallback(() => {
    if (stepLocked) {
      handleCompleteAndContinue();
      return;
    }
    if (!canContinueRef.current && !canContinue) return; // 与按钮 disabled 口径一致，防御性拦截
    setContinueConfirmOpen(true);
  }, [stepLocked, canContinue, handleCompleteAndContinue]);

  const handleDeleteThread = (thread: ChatThread) => {
    if (!activationCode || !phase) return;
    if (stepLocked && !adminDebugBypass) return;
    void (async () => {
      // 标记删除进行中，防止 "load messages" effect 竞态触发新建线程
      deleteInProgressRef.current = true;
      try {
        // 后端优先删除：先调后端 API，成功后再同步本地
        const result = await deleteThreadBackendFirst(activationCode, phase, thread.id);
        if (!result) {
          setChatError('删除失败，请稍后重试');
          return;
        }

        // 直接从当前 React state 过滤掉被删除的线程（不依赖 localStorage，避免竞态）
        const remaining = threads.filter((t) => t.id !== thread.id);
        setStepLocked(result.stepLocked);
        if (result.selectedThreadId !== null) {
          setReportSelectedThreadId(result.selectedThreadId);
        }

        if (thread.id === activeThreadId) {
          if (remaining.length > 0) {
            // 使用后端 selected 或本地第一个线程
            const nextActiveId =
              result.selectedThreadId && remaining.some((t) => t.id === result.selectedThreadId)
                ? result.selectedThreadId
                : remaining[0].id;
            const next = remaining.find((t) => t.id === nextActiveId) ?? remaining[0];
            setActiveThreadIdState(next.id);
            setActiveThreadId(activationCode, phase, next.id);
            setMessages(next.messages);
            setBackendSyncedThreadId(next.id);
          } else {
            // 删除后已无任何线程：重置自动初始化 guard，
            // 允许后续 effect 再次触发 /simple-chat/init，避免停在空白死状态
            autoInitGuardRef.current = '';
            setActiveThreadIdState(null);
            setMessages([]);
            setBackendSyncedThreadId(null);
          }
        }

        setThreads(remaining);
      } finally {
        deleteInProgressRef.current = false;
      }
    })();
  };

  const handleStopStream = () => {
    abortControllerRef.current?.abort();
  };

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

  if (!session || !phaseMeta || !phaseInfo) return null;

  return (
    <div
      className="flow-light careering-matte chat-shell-h flex min-h-0 flex-col overflow-hidden"
      data-phase={phase}
      {...chatAppearanceAttrs}
      style={chatAppearanceStyle}
    >
      {/* 旧内核浏览器提示（ADR-0020）：「不再提示」前每个 phase 页都弹 */}
      <LegacyBrowserNotice />
      <ChatPhaseBackground phase={phase} engine="silk" />
      {/* 顶栏留白由 (main)/layout.tsx 的 pt-14 承担，此处勿再 pt-14，否则侧栏与主区会出现双倍空白 */}
      <div className="flex min-h-0 flex-1 overflow-hidden relative z-10">
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
            phaseStickerSrc={`/assets/openlife-journey/sticker-${phase}.webp`}
            streamBlocksSessionSwitch={sending}
            threadsLoading={!threadsFetched || initLoading}
          />
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {/* 报告已解锁：只读历史模式提示条 + 查看报告入口 */}
          {reportUnlocked && activationCode && (
            <div
              className="shrink-0 border-y border-emerald-200/70 bg-emerald-50/80 px-4 py-2.5 sm:px-8"
              role="status"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs leading-relaxed text-emerald-800 sm:text-sm">
                  {t('explore.chat.reportDoneBanner')}
                </p>
                <button
                  type="button"
                  onClick={() =>
                    router.push(`/explore/report?code=${encodeURIComponent(activationCode)}`)
                  }
                  className="shrink-0 rounded-full bg-bd-ui-accent px-3 py-1.5 text-xs font-medium text-bd-ui-accent-fg transition hover:opacity-90 sm:text-sm"
                >
                  {t('explore.chat.reportDoneViewReport')}
                </button>
              </div>
            </div>
          )}
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">

                <header className="careering-chat-header">
                  <h2 className="careering-chat-phase-title">
                    {phaseInfo.num} {phaseLabel}
                  </h2>
                  <div className="careering-chat-header-actions">
                    <button
                      type="button"
                      onClick={handleRequestCompleteAndContinue}
                      disabled={!canContinue}
                      title={continueDisabledHint}
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
              <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden py-4">
                  {/* 对话区 */}
                  <div className="flow-chat-box relative flex min-h-0 min-w-0 flex-1 flex-col w-full max-w-none">
              <div
                ref={chatBodyRef}
                className="flow-chat-body min-h-0 min-w-0 w-full flex-1 overflow-y-auto"
              >
                <div className="careering-chat-messages-inner min-w-0 w-full max-w-none px-4 sm:px-6 lg:px-12">
                {initLoading || !exploreResumeSynced ? (
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
                ) : messages.length === 0 ? (
                  <p className="flow-progress-text text-center py-8 text-sm">
                    {t('explore.chat.preparingFirstQuestion')}
                  </p>
                ) : (
                  messages.map((m, idx) => {
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
                            interactionLocked={
                              phaseInteractionLocked ||
                              !!m.conclusionLocked ||
                              m.id !== latestConclusionMessageId
                            }
                            onCollapsedChange={(collapsed) =>
                              setMessages((prev) =>
                                prev.map((msg) =>
                                  msg.id === m.id ? { ...msg, conclusionCollapsed: collapsed } : msg
                                )
                              )
                            }
                            showActions={
                              !phaseInteractionLocked &&
                              !m.conclusionLocked &&
                              !m.conclusionCollapsed &&
                              m.id === latestConclusionMessageId
                            }
                            forbidHeaderCollapseWhileActions={
                              !phaseInteractionLocked &&
                              !m.conclusionLocked &&
                              !m.conclusionCollapsed &&
                              m.id === latestConclusionMessageId
                            }
                            onConfirm={handleConfirmConclusion}
                            onContinueChat={() => handleContinueChat(m)}
                          />
                        </div>
                      ) : m.role === 'user' ? (
                        <div className="flow-msg-user-wrap">
                          {m.createdAt !== undefined && (
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
                          <div className="flow-msg-user-anchor">
                            <div className="flow-msg-user-content" lang="zh-CN">
                              {(() => {
                                const s = (m.content || '').replace(/\r\n/g, '\n');
                                const charCount = [...s].length;
                                const hasManualBreak = s.includes('\n');
                                // 仅超短文本保留单行；稍长句子必须允许自动换行，避免窄屏溢出。
                                const compactSingleLineThreshold = 8;
                                const compact =
                                  charCount > 0 &&
                                  charCount <= compactSingleLineThreshold &&
                                  !hasManualBreak;
                                const textClass = `flow-msg-user-text flow-msg-user-text--careering-plain${compact ? ' flow-msg-user-text--compact' : ''}`;
                                return <span className={textClass}>{s}</span>;
                              })()}
                            </div>
                          </div>
                          {!phaseInteractionLocked && (
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
                          )}
                        </div>
                      ) : (
                        <FlowAiMessage
                          content={m.content}
                          phase={phaseClass}
                          variant="careeringMatte"
                          careeringAiRoleLabel={t('explore.chat.careeringAiRole')}
                          contentMode={
                            'markdown'
                          }
                          streaming={sending && idx === messages.length - 1}
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
                          toolbarSavepointTitle={savepointBusy ? '保存中…' : '保存为检查点'}
                          sessionId={backendSessionId ?? undefined}
                          logIndex={messages
                            .slice(0, aiIndexForHandlers)
                            .filter((x) => x.role === 'assistant' && x.type !== 'dimension_conclusion')
                            .length}
                          dimension={phase}
                          messageId={m.id}
                          threadId={threads.find((t) => t.id === activeThreadId)?.id}
                          phaseKey={phase}
                          activationCode={activationCode ?? undefined}
                          onSavepoint={
                            canUseAdminSavepoint && !savepointBusy && msgIdxInFull >= 0
                              ? () => void handleOpenSavepointModal(m, aiIndexForHandlers)
                              : undefined
                          }
                          hideToolbar={
                            phaseInteractionLocked
                          }
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
                {autoRetryNotice && !chatError && (
                  <div className="flow-msg-retrying">
                    <span className="flow-msg-retrying-dot" aria-hidden />
                    <span>{t('explore.chat.retrying')}</span>
                  </div>
                )}
                {chatError && (
                  <div className="flow-msg-error">
                    <div className="flow-msg-error-text">{chatError}</div>
                    {!phaseInteractionLocked && (
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
                    )}
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
            {phaseInteractionLocked && (
              <div
                className="border-t border-amber-200/90 bg-amber-50 px-4 py-2 text-center text-xs font-medium text-amber-950"
                role="status"
              >
                {t('explore.chat.phaseLockedInputBanner')}
              </div>
            )}
            <div className="flow-input-area">
              <form onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }} className="w-full">
                {pendingConclusionChoiceBlocksChat && (
                  <p
                    className="mb-1.5 w-full shrink-0 rounded-lg border border-amber-200/90 bg-amber-50/90 px-2 py-1.5 text-left text-xs leading-snug text-amber-950"
                    role="status"
                  >
                    {t('explore.chat.conclusionChoiceRequiredBanner')}
                  </p>
                )}
                {showConclusionRequestButton && (
                  <ConclusionRequestButton
                    state={conclusionReqState}
                    idle={!sending && !input.trim()}
                    onClick={handleRequestConclusion}
                  />
                )}
                <div
                  className={`flow-input-box${
                    (phaseInteractionLocked && !sending) ||
                    (pendingConclusionChoiceBlocksChat && !sending)
                      ? ' opacity-40 pointer-events-none'
                      : ''
                  } !flex !flex-col !items-stretch gap-1.5`}
                >
                  {(conclusionReqState === 'loading' ||
                    (sending &&
                      (postLlmTailActive ||
                        waitingForConclusionCardUi ||
                        conclusionLoading))) && (
                    <p
                      className="w-full shrink-0 px-1 text-left text-xs leading-snug text-neutral-500"
                      role="status"
                      aria-live="polite"
                    >
                      {conclusionReqState === 'loading' ||
                      waitingForConclusionCardUi ||
                      (sending && conclusionLoading)
                        ? t('explore.chat.streamStatusConclusion')
                        : t('explore.chat.streamStatusGeneric')}
                    </p>
                  )}
                  <div className="flex w-full min-w-0 items-end gap-2.5">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (!sending && !isReadOnly) {
                          handleSend();
                        }
                      }
                    }}
                    placeholder={
                      streamTailInputPlaceholder ??
                      (phaseInteractionLocked
                        ? t('explore.chat.placeholderPhaseLocked')
                        : isReadOnly
                          ? t('explore.chat.placeholderReadOnly')
                          : hasCollapsedConclusion
                            ? t('explore.chat.placeholderRefine')
                            : t('explore.chat.inputPlaceholderCareering'))
                    }
                    rows={1}
                    disabled={sending || isReadOnly || conclusionReqState === 'loading'}
                    className="flow-input-field"
                  />
                  <div className="flow-send-btn-wrap">
                    {sending && (
                      <div className="flow-send-glow" aria-hidden />
                    )}
                    <button
                      type="button"
                      onClick={sending ? handleStopStream : () => handleSend()}
                      disabled={
                        isReadOnly ||
                        conclusionReqState === 'loading' ||
                        (!sending && !input.trim())
                      }
                      className={`flow-send-btn ${sending ? 'is-stop' : ''}`}
                    >
                      {sending ? (
                        <Square size={16} strokeWidth={0} fill="white" />
                      ) : (
                        <ArrowUp size={16} strokeWidth={2.2} />
                      )}
                    </button>
                  </div>
                  </div>
                </div>
                <p className="mt-1 w-full shrink-0 text-center text-[10px] leading-tight text-[var(--flow-text-muted)] opacity-70">
                  {t('explore.chat.aiDisclaimer')}
                </p>
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
      {phaseLockNoticeOpen && (
        <div
          className="fixed inset-0 z-[57] flex items-center justify-center bg-black/35 backdrop-blur-sm"
          onClick={() => dismissPhaseLockNotice(phaseLockNoticeDontRemind, false)}
          role="presentation"
        >
          <div
            className="mx-4 w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="phase-lock-notice-title"
          >
            <h3
              id="phase-lock-notice-title"
              className="mb-2 text-lg font-semibold text-[var(--flow-text-body)]"
            >
              {t('explore.chat.phaseLockModalTitle')}
            </h3>
            <p className="mb-5 text-sm leading-relaxed text-[var(--flow-text-muted)]">
              {t('explore.chat.phaseLockModalMessage')}
            </p>
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <label className="flex cursor-pointer items-center gap-2 text-sm text-[var(--flow-text-body)]">
                <input
                  type="checkbox"
                  checked={phaseLockNoticeDontRemind}
                  onChange={(e) => setPhaseLockNoticeDontRemind(e.target.checked)}
                  className="h-4 w-4 rounded border-neutral-300"
                />
                {t('explore.chat.phaseLockModalDontRemind')}
              </label>
            </div>
            <div className="flex flex-wrap justify-end gap-3">
              <button
                type="button"
                onClick={() => dismissPhaseLockNotice(phaseLockNoticeDontRemind, false)}
                className="rounded-xl px-4 py-2 text-sm font-medium text-[var(--flow-text-muted)] transition-colors hover:bg-neutral-100"
              >
                {t('explore.chat.phaseLockModalGotIt')}
              </button>
              <button
                type="button"
                onClick={() => dismissPhaseLockNotice(phaseLockNoticeDontRemind, true)}
                disabled={!canContinue}
                className="rounded-xl bg-neutral-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {t('explore.chat.completeAndContinue')}
              </button>
            </div>
          </div>
        </div>
      )}
      {savepointModalOpen && (
        <div
          className="fixed inset-0 z-[62] flex items-center justify-center bg-black/35 backdrop-blur-sm"
          role="presentation"
          onClick={() => !savepointBusy && setSavepointModalOpen(false)}
        >
          <div
            className="mx-4 w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="savepoint-create-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="savepoint-create-title" className="mb-3 text-lg font-semibold text-[var(--flow-text-body)]">
              保存为检查点
            </h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-[var(--flow-text-muted)]">检查点名称（唯一）</label>
                <input
                  className="w-full rounded-xl border border-bd-border bg-bd-bg px-3 py-2 text-sm text-bd-fg"
                  value={savepointDraftName}
                  onChange={(e) => setSavepointDraftName(e.target.value)}
                  disabled={savepointBusy}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-[var(--flow-text-muted)]">断言参考（可编辑）</label>
                <textarea
                  className="min-h-[92px] w-full rounded-xl border border-bd-border bg-bd-bg px-3 py-2 text-sm text-bd-fg"
                  value={savepointDraftHint}
                  onChange={(e) => setSavepointDraftHint(e.target.value)}
                  disabled={savepointBusy}
                />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                className="rounded-xl px-4 py-2 text-sm font-medium text-[var(--flow-text-muted)] hover:bg-neutral-100"
                onClick={() => setSavepointModalOpen(false)}
                disabled={savepointBusy}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded-xl bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800 disabled:opacity-50"
                onClick={() => void handleCreateSavepoint()}
                disabled={savepointBusy}
              >
                {savepointBusy ? '保存中…' : '确认保存'}
              </button>
            </div>
          </div>
        </div>
      )}
      <PhaseCelebrateBurst playSignal={phaseCelebrateSignal} />
      <PhaseCompleteWarmModal
        open={phaseCompleteModalOpen}
        title={t('explore.phaseComplete.title')}
        body={`${t('explore.phaseComplete.subtitle')}\n\n${t(`explore.phaseComplete.outro.${phase}`)}`}
        fatigueNote={
          fatigueMinutes != null
            ? t('explore.phaseComplete.fatigueNote', { minutes: String(fatigueMinutes) })
            : t('explore.phaseComplete.fatigueNoteGeneric')
        }
        continueLabel={t('explore.phaseComplete.continue')}
        dontRemindLabel={t('explore.phaseComplete.dontRemind')}
        onContinue={handlePhaseCompleteModalContinue}
      />
      <ContinueConfirmModal
        open={continueConfirmOpen}
        title={t('explore.chat.continueConfirmTitle')}
        body={t('explore.chat.continueConfirmMessage')}
        primaryLabel={t('explore.chat.continueConfirmOk')}
        secondaryLabel={t('explore.chat.continueConfirmCancel')}
        onPrimary={() => {
          setContinueConfirmOpen(false);
          handleCompleteAndContinue();
        }}
        onClose={() => setContinueConfirmOpen(false)}
      />
      <TrialLimitModal
        open={trialBlock !== null}
        title={
          trialBlock?.kind === 'locked'
            ? t('explore.trial.lockedTitle')
            : t('explore.trial.limitTitle')
        }
        body={
          trialBlock?.kind === 'locked' ? t('explore.trial.lockedBody') : t('explore.trial.limitBody')
        }
        primaryLabel={
          trialBlock?.hasUpgradeCodes ? t('explore.trial.useExisting') : t('explore.trial.buy')
        }
        secondaryLabel={t('explore.trial.later')}
        extraLabel={trialBlock?.hasUpgradeCodes ? t('explore.trial.buy') : undefined}
        onExtra={
          trialBlock?.hasUpgradeCodes
            ? () => {
                setTrialBlock(null);
                setTrialPurchaseOpen(true);
              }
            : undefined
        }
        onPrimary={() => {
          const hasCodes = trialBlock?.hasUpgradeCodes;
          setTrialBlock(null);
          if (hasCodes) {
            setTrialUpgradeOpen(true);
          } else {
            setTrialPurchaseOpen(true);
          }
        }}
        onClose={() => setTrialBlock(null)}
      />
      <PurchaseModal
        open={trialPurchaseOpen}
        onClose={() => setTrialPurchaseOpen(false)}
        intent="upgrade_trial"
        onSuccess={(code, order) => {
          setTrialPurchaseOpen(false);
          // 直购升级：后端已自动消耗升级试用码，留在当前对话即可
          if (order.meta?.auto_upgraded) return;
          // 支付成功：提示用户去激活页使用新码（激活页从 query 预填）
          router.push(`/explore/activate?code=${encodeURIComponent(code)}`);
        }}
      />
      <UpgradeTrialModal
        open={trialUpgradeOpen}
        onClose={() => setTrialUpgradeOpen(false)}
        onUpgraded={() => setTrialUpgradeOpen(false)}
      />
      <PhaseWelcomeModal
        open={phaseWelcomeOpen}
        phaseLabel={t(`explore.chat.phaseLabels.${phase}`)}
        phaseNum={phaseInfo?.num ?? ''}
        estimateLabel={t('explore.phaseWelcome.estimateLabel', { minutes: PHASE_ESTIMATE_MINUTES[phase] })}
        autoSaveHint={t('explore.phaseWelcome.autoSaveHint')}
        reassuranceHint={t('explore.phaseWelcome.reassuranceHint')}
        startLabel={t('explore.phaseWelcome.start')}
        onClose={handlePhaseWelcomeClose}
      />
    </div>
  );
}
