/**
 * 统一"后端为准"的会话 / journey 恢复策略。
 *
 * 设计原则：
 *  1. 后端是唯一 source of truth，localStorage 仅做加速缓存。
 *  2. 清缓存后从后端可完整恢复所有状态（阶段进度、线程列表、问卷状态）。
 *  3. 跨设备登录时每次从后端拉取最新进度，保证一致性。
 */

import { apiClient } from '@/lib/api/client';
import {
  loadSession,
  saveSession,
  applyExploreResumeToSession,
  setLastActivationCode,
  type ExploreSession,
  type ExploreResumePayload,
  type PhaseKey,
  setUserSurveyCompleted,
  getUserSurveyCompleted,
} from './session';
import {
  getThreads,
  setThreadsForPhase,
  getActiveThreadId,
  setActiveThreadId,
  clearThreadCache,
  markSynced,
  collapseRuminationThreadsToOne,
  pickCanonicalRuminationThread,
  type ChatThread,
  type ThreadMessage,
} from './threads';
import { fetchExploreResumeFromJourneys } from './journeyResume';
import { surveyApi } from '@/lib/api/survey';
import { ruminationStepBoundaryKey } from './ruminationStepBoundaries';

// ──────────────────────────────────────────────
// 类型
// ──────────────────────────────────────────────

/** 后端 /simple-chat/threads 返回的线程元数据 */
interface BackendThreadMeta {
  id: string;
  title: string;
  status: string;
  createdAt: number;
  dimensionConclusion?: Record<string, unknown>;
  selected?: boolean;
}

/** 后端 /simple-chat/history 返回的消息 */
interface BackendMessage {
  role: string;
  content: string;
  think_content?: string;
  type?: string;
  conclusion_data?: Record<string, unknown>;
  table_payload?: Record<string, unknown>;
  rumination_row_label?: string;
  created_at?: string | number;
  id?: string;
}

/** 完整恢复结果：可用于初始化 UI 状态 */
export interface RecoveryResult {
  session: ExploreSession;
  threads: ChatThread[];
  activeThreadId: string | null;
  /** 后端 activation_session_id（用于后续请求） */
  activationSessionId?: string;
  /** 该步骤是否已锁定 */
  stepLocked: boolean;
  /** 该步骤的 selected_thread_id（报告用） */
  selectedThreadId: string | null;
}

// ──────────────────────────────────────────────
// 后端 API 调用
// ──────────────────────────────────────────────

const BACKEND_PHASE: Record<string, string> = {
  values: 'values',
  strengths: 'strengths',
  interests: 'interests',
  purpose: 'purpose',
  rumination: 'rumination',
};

/** 调用 /simple-auth/journeys 获取所有旅程 */
async function fetchAllJourneys() {
  const res = await apiClient.get('/simple-auth/journeys');
  return (res.data?.journeys ?? []) as Array<{
    activation_code: string;
    explore_resume?: ExploreResumePayload;
  }>;
}

/** 调用 /simple-chat/threads 获取某阶段线程列表 */
async function fetchBackendThreads(activationCode: string, phase: string) {
  const res = await apiClient.get('/simple-chat/threads', {
    params: { activation_code: activationCode, phase: BACKEND_PHASE[phase] },
  });
  const threads = (res.data?.threads ?? []) as BackendThreadMeta[];
  const stepLocked = Boolean(res.data?.step_locked);
  const selectedTid = threads.find((t) => t.selected)?.id ?? null;
  return { threads, stepLocked, selectedThreadId: selectedTid };
}

/** 调用 /simple-chat/history 获取线程完整消息 */
async function fetchBackendHistory(
  activationCode: string,
  phase: string,
  threadId: string
) {
  const res = await apiClient.get('/simple-chat/history', {
    params: {
      activation_code: activationCode,
      phase: BACKEND_PHASE[phase],
      thread_id: threadId,
    },
  });
  const messages = (res.data?.messages ?? []) as BackendMessage[];
  const meta = res.data?.metadata ?? {};
  const activation = res.data?.activation ?? {};
  const activationSessionId = activation.activation_session_id as string | undefined;
  const dimensionConclusion = meta.dimension_conclusion as Record<string, unknown> | undefined;
  const threadCompleted = Boolean(meta.thread_completed);
  const stepLocked = meta.step_locked as boolean | undefined;
  return { messages, meta, activationSessionId, dimensionConclusion, threadCompleted, stepLocked };
}

// ──────────────────────────────────────────────
// 消息转换
// ──────────────────────────────────────────────

/** 将后端消息格式转换为前端 ThreadMessage */
function mapBackendMessage(msg: BackendMessage, index: number): ThreadMessage {
  const id = msg.id ?? `m_${index}`;
  return {
    id,
    role: msg.role === 'user' ? 'user' : 'assistant',
    content: msg.content ?? '',
    thinkContent: msg.think_content,
    type: (msg.type as ThreadMessage['type']) ?? 'text',
    conclusionData: msg.conclusion_data as any,
    tablePayload: msg.table_payload as any,
    ruminationRowLabel: msg.rumination_row_label,
    createdAt: msg.created_at
      ? new Date(msg.created_at).getTime()
      : Date.now() - (100 - index) * 1000,
  };
}

/** 将后端线程元数据转换为前端 ChatThread（不含 messages，需后续 hydrate） */
function mapBackendThreadMeta(t: BackendThreadMeta): ChatThread {
  return {
    id: t.id,
    title: t.title,
    status: t.status as 'in-progress' | 'completed',
    messages: [],
    createdAt: t.createdAt,
    dimensionConclusion: t.dimensionConclusion as any,
  };
}

// ──────────────────────────────────────────────
// 核心恢复函数
// ──────────────────────────────────────────────

/**
 * 从后端完整恢复某激活码的阶段状态。
 *
 * 流程：
 *  1. 拉取 /simple-auth/journeys 获取 explore_resume → 同步阶段进度
 *  2. 拉取 /simple-chat/threads 获取线程列表
 *  3. 对每个线程拉取 /simple-chat/history 获取完整消息
 *  4. 写入 localStorage（作为加速缓存）
 *  5. 返回完整 RecoveryResult
 *
 * @param activationCode 激活码
 * @param phase 目标阶段
 * @param userId 当前用户 ID（用于查询问卷状态）
 * @returns RecoveryResult 或 null（网络失败时返回 null）
 */
export async function recoverSessionFromBackend(
  activationCode: string,
  phase: string,
  userId?: string
): Promise<RecoveryResult | null> {
  // 第一步：同步 explore_resume（阶段进度）
  let exploreResume: ExploreResumePayload | null = null;
  try {
    exploreResume = await fetchExploreResumeFromJourneys(activationCode);
  } catch {
    // 网络失败时，尝试使用 localStorage 中的 session
  }

  // 构建 session：后端 resume 覆盖本地
  const localSession = loadSession(activationCode);
  let session: ExploreSession;
  if (exploreResume?.resume_phase) {
    session = applyExploreResumeToSession(localSession, exploreResume);
  } else {
    session = localSession;
  }

  // 第二步：同步问卷完成状态（从后端查询，避免本地缓存不一致）
  try {
    if (userId) {
      const statusRes = await surveyApi.getUserSurveyStatus();
      if (statusRes.data?.completed) {
        session = { ...session, surveyCompleted: true };
        setUserSurveyCompleted(userId, true);
      }
    }
  } catch {
    // 使用本地状态兜底
    session = { ...session, surveyCompleted: session.surveyCompleted || getUserSurveyCompleted(userId) };
  }

  saveSession(session);
  setLastActivationCode(activationCode);

  // 第三步：同步线程列表和消息
  try {
    const { threads: backendThreads, stepLocked, selectedThreadId } =
      await fetchBackendThreads(activationCode, phase);

    let threadsToHydrate: BackendThreadMeta[];

    // 沉淀阶段：只取主线程
    if (phase === 'rumination') {
      if (backendThreads.length === 0) {
        threadsToHydrate = [];
      } else {
        // 选出 canonical thread（与前端 collapse 逻辑一致）
        const mapped = backendThreads.map(mapBackendThreadMeta);
        const canonical = pickCanonicalRuminationThread(mapped);
        threadsToHydrate = canonical ? [backendThreads.find((t) => t.id === canonical.id)!] : [];
      }
    } else {
      threadsToHydrate = backendThreads;
    }

    // 并行获取所有线程的完整消息
    const hydratedThreads = await Promise.all(
      threadsToHydrate.map(async (bt) => {
        const thread = mapBackendThreadMeta(bt);
        try {
          const { messages, activationSessionId, dimensionConclusion, threadCompleted, stepLocked: threadStepLocked } =
            await fetchBackendHistory(activationCode, phase, bt.id);
          thread.messages = messages.map(mapBackendMessage);
          if (dimensionConclusion) thread.dimensionConclusion = dimensionConclusion as any;
          if (threadCompleted) thread.status = 'completed';
          // 返回 activationSessionId 供调用方使用
          return { thread, activationSessionId, stepLocked: threadStepLocked };
        } catch {
          return { thread, activationSessionId: undefined, stepLocked: undefined };
        }
      })
    );

    const finalThreads = hydratedThreads.map((h) => h.thread);
    const lastActivationSessionId = hydratedThreads.find((h) => h.activationSessionId)?.activationSessionId;
    // 合并 step_locked 信息
    const effectiveStepLocked =
      hydratedThreads.some((h) => h.stepLocked === true) || stepLocked;

    // 写入 localStorage（作为加速缓存）
    setThreadsForPhase(activationCode, phase as PhaseKey, finalThreads);

    // 确定活跃线程
    const localActiveId = getActiveThreadId(activationCode, phase as PhaseKey);
    const activeThreadId =
      finalThreads.length > 0
        ? finalThreads.some((t) => t.id === localActiveId)
          ? localActiveId
          : finalThreads[0].id
        : null;

    if (activeThreadId) {
      setActiveThreadId(activationCode, phase as PhaseKey, activeThreadId);
    }

    // 更新 session 中的 activationSessionId
    if (lastActivationSessionId) {
      session = {
        ...session,
        activationSessionId: lastActivationSessionId,
        sessionId: lastActivationSessionId,
      };
      saveSession(session);
    }

    return {
      session,
      threads: finalThreads,
      activeThreadId,
      activationSessionId: lastActivationSessionId,
      stepLocked: effectiveStepLocked,
      selectedThreadId,
    };
  } catch {
    // 线程同步失败，回退到 localStorage 缓存
    let cached = getThreads(activationCode, phase as PhaseKey);
    if (phase === 'rumination' && cached.length > 1) {
      cached = collapseRuminationThreadsToOne(cached);
    }
    const activeId = getActiveThreadId(activationCode, phase as PhaseKey);
    return {
      session,
      threads: cached,
      activeThreadId: cached.some((t) => t.id === activeId) ? activeId : cached[0]?.id ?? null,
      stepLocked: false,
      selectedThreadId: null,
    };
  }
}

/**
 * 清缓存后完整恢复：清除所有本地数据，再从后端重建。
 * 用于"设置 → 清除缓存"或首次安装等场景。
 *
 * @returns 恢复后的最新 session，或 null
 */
export async function fullRecoveryAfterCacheClear(
  userId?: string
): Promise<ExploreSession | null> {
  try {
    const journeys = await fetchAllJourneys();
    if (journeys.length === 0) return null;

    // 取最近的旅程
    const latest = journeys[0];
    const activationCode = latest.activation_code;
    const exploreResume = latest.explore_resume ?? null;

    setLastActivationCode(activationCode);

    // 从后端恢复 session
    const session = loadSession(activationCode);
    let recovered = exploreResume?.resume_phase
      ? applyExploreResumeToSession(session, exploreResume)
      : session;

    // 同步问卷状态
    if (userId) {
      try {
        const statusRes = await surveyApi.getUserSurveyStatus();
        if (statusRes.data?.completed) {
          recovered = { ...recovered, surveyCompleted: true };
          setUserSurveyCompleted(userId, true);
        }
      } catch {}
    }

    saveSession(recovered);

    // 为所有旅程清除旧的线程缓存，使其下次进入阶段时从后端重新拉取
    for (const j of journeys) {
      clearThreadCache(j.activation_code);
    }

    return recovered;
  } catch {
    return null;
  }
}

/**
 * 调用后端删除线程，使用后端返回的 remaining_thread_ids 同步本地状态。
 *
 * 与直接调用 removeThread 不同，此函数：
 *  1. 先调用后端 API
 *  2. 使用后端返回的 remaining_thread_ids 更新本地（而非本地计算）
 *  3. 如果后端成功但本地更新失败，不影响后端状态
 *  4. 如果后端失败，本地不做任何变更（保证一致性）
 *
 * @returns 后端返回的剩余线程 ID 列表和状态，或 null（失败时）
 */
export async function deleteThreadBackendFirst(
  activationCode: string,
  phase: string,
  threadId: string
): Promise<{
  remainingThreadIds: string[];
  selectedThreadId: string | null;
  stepLocked: boolean;
} | null> {
  try {
    const res = await apiClient.post('/simple-chat/thread/delete', {
      activation_code: activationCode,
      phase: BACKEND_PHASE[phase],
      thread_id: threadId,
    });

    const data = res.data?.data ?? {};
    const remainingThreadIds: string[] = data.remaining_thread_ids ?? [];
    const selectedThreadId: string | null = data.selected_thread_id ?? null;
    const stepLocked: boolean = data.step_locked ?? false;

    // 后端成功后，直接移除被删除的线程（不依赖 remaining_thread_ids 的 ID 格式匹配）
    const currentThreads = getThreads(activationCode, phase as PhaseKey);
    const updatedThreads = currentThreads.filter((t) => t.id !== threadId);
    setThreadsForPhase(activationCode, phase as PhaseKey, updatedThreads);

    // 更新活跃线程：若删除的是活跃线程，切换到后端 selected 或第一个
    const currentActiveId = getActiveThreadId(activationCode, phase as PhaseKey);
    if (currentActiveId === threadId) {
      const nextActiveId = selectedThreadId ?? updatedThreads[0]?.id ?? null;
      setActiveThreadId(activationCode, phase as PhaseKey, nextActiveId);
    }

    // 清除已删除线程的 rumination 步骤边界缓存
    try {
      localStorage.removeItem(ruminationStepBoundaryKey(activationCode, threadId));
    } catch {}

    return { remainingThreadIds, selectedThreadId, stepLocked };
  } catch {
    return null;
  }
}
