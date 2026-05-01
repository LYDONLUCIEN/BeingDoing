/**
 * Client-side session state for the step-by-step explore flow.
 * Persisted in localStorage keyed by activation_code.
 */

export type PhaseKey = 'values' | 'strengths' | 'interests' | 'purpose' | 'rumination';

export const PHASES: { key: PhaseKey; label: string; color: string; num: string }[] = [
  { key: 'values',    label: '信念',  color: 'blue',    num: '01' },
  { key: 'strengths', label: '禀赋',  color: 'amber',   num: '02' },
  { key: 'interests', label: '热忱',  color: 'rose',    num: '03' },
  { key: 'purpose',   label: '使命',  color: 'emerald', num: '04' },
  { key: 'rumination', label: '沉淀', color: 'violet',  num: '05' },
];

export interface ExploreSession {
  activationCode: string;
  unlockedPhases: PhaseKey[];
  currentPhase: PhaseKey;
  surveyCompleted: boolean;
  /** 是否已生成报告（完成使命后通过渲染预备页） */
  reportReady?: boolean;
  /** 后端 session_id（用于埋点、报告生成等） */
  sessionId?: string;
  /** 语义化别名：激活码存储会话ID（与 thread_id 不同） */
  activationSessionId?: string;
}

/** 检查是否有可查看的报告（完成全部五阶段探索，含沉淀） */
export function hasReportAvailable(session: ExploreSession): boolean {
  return session.unlockedPhases.includes('rumination');
}

const KEY = (code: string) => `explore_session_${code}`;

export function loadSession(code: string): ExploreSession {
  if (typeof window === 'undefined') {
    return defaultSession(code);
  }
  try {
    const raw = localStorage.getItem(KEY(code));
    if (raw) return JSON.parse(raw) as ExploreSession;
  } catch {}
  return defaultSession(code);
}

export function saveSession(session: ExploreSession): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(KEY(session.activationCode), JSON.stringify(session));
}

/** 统一读取 activation session id（新字段优先，回退旧字段） */
export function getActivationSessionId(session: ExploreSession | null | undefined): string | undefined {
  const v = session?.activationSessionId ?? session?.sessionId;
  if (!v) return undefined;
  const s = String(v).trim();
  return s || undefined;
}

/** 统一写入 activation session id（兼容期双写） */
export function setActivationSessionId(session: ExploreSession, activationSessionId: string): ExploreSession {
  const normalized = String(activationSessionId || '').trim();
  if (!normalized) return session;
  return {
    ...session,
    activationSessionId: normalized,
    sessionId: normalized,
  };
}

/** history API metadata: strict thread_id only. */
export function readThreadIdFromHistoryMetadata(
  meta: Record<string, unknown> | null | undefined
): string | undefined {
  if (!meta) return undefined;
  const t = meta.thread_id;
  if (typeof t === 'string' && t.trim()) return t.trim();
  return undefined;
}

/** simple-chat API nested activation: use activation_session_id only (legacy activation.session_id was thread). */
export function readActivationSessionIdFromActivationApi(
  activation: Record<string, unknown> | null | undefined
): string | undefined {
  if (!activation) return undefined;
  const v = activation.activation_session_id;
  if (typeof v === 'string' && v.trim()) return v.trim();
  return undefined;
}

/** 激活接口返回：根据 report record.json 推断应回到的阶段（字段可能部分缺失） */
export interface ExploreResumePayload {
  resume_phase?: string;
  unlocked_phases?: string[];
  /** 后端根据 record 推断：五阶段均已选定会话时可进入报告流 */
  report_unlocked?: boolean;
}

/**
 * 用后端 explore_resume 覆盖 currentPhase / unlockedPhases（重新登录时与服务器进度对齐）。
 */
export function applyExploreResumeToSession(
  session: ExploreSession,
  resume: ExploreResumePayload | null | undefined
): ExploreSession {
  if (!resume?.resume_phase) return session;
  const rp = resume.resume_phase as PhaseKey;
  if (!PHASES.some((p) => p.key === rp)) return session;
  const raw = resume.unlocked_phases;
  let unlocked: PhaseKey[] = [];
  if (Array.isArray(raw)) {
    unlocked = raw.filter((k): k is PhaseKey =>
      PHASES.some((p) => p.key === k)
    );
  }
  if (unlocked.length === 0) {
    const idx = PHASES.findIndex((p) => p.key === rp);
    unlocked = PHASES.slice(0, idx + 1).map((p) => p.key);
  }
  return {
    ...session,
    currentPhase: rp,
    unlockedPhases: unlocked,
  };
}

export function unlockNextPhase(session: ExploreSession): ExploreSession {
  const keys = PHASES.map((p) => p.key);
  const currentIdx = keys.indexOf(session.currentPhase);
  // currentPhase 不在 PHASES 中（异常数据）时不做任何变更，避免跳到 values
  if (currentIdx < 0) return session;
  const nextKey = keys[currentIdx + 1];
  // 已是最后阶段（rumination）时不再前进
  if (!nextKey) return session;
  const updated: ExploreSession = {
    ...session,
    unlockedPhases: session.unlockedPhases.includes(nextKey)
      ? session.unlockedPhases
      : [...session.unlockedPhases, nextKey],
    currentPhase: nextKey,
  };
  saveSession(updated);
  return updated;
}

function defaultSession(code: string): ExploreSession {
  return {
    activationCode: code,
    unlockedPhases: ['values'],
    currentPhase: 'values',
    surveyCompleted: false,
  };
}

/** Stored in a separate key so we can retrieve the last used code on /activate */
export function getLastActivationCode(): string {
  if (typeof window === 'undefined') return '';
  return localStorage.getItem('explore_last_code') ?? '';
}

export function setLastActivationCode(code: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem('explore_last_code', code);
}

// ──────────────────────────────────────────────
// 用户维度问卷完成状态（不随激活码变化，切换激活码仍然有效）
// 按用户 ID 隔离，支持多账号切换
// ──────────────────────────────────────────────

const USER_SURVEY_DONE_PREFIX = 'explore_user_survey_';

/** 标记指定用户已完成问卷（用户维度，localStorage 持久化） */
export function setUserSurveyCompleted(userId: string, done: boolean): void {
  if (typeof window === 'undefined' || !userId) return;
  localStorage.setItem(`${USER_SURVEY_DONE_PREFIX}${userId}`, done ? '1' : '0');
}

/** 读取当前用户维度问卷完成状态（默认 false） */
export function getUserSurveyCompleted(userId?: string): boolean {
  if (typeof window === 'undefined') return false;
  // 未传 userId 时尝试从 auth-storage 读取当前用户
  if (!userId) {
    try {
      const raw = localStorage.getItem('auth-storage');
      if (raw) {
        const parsed = JSON.parse(raw);
        userId = parsed?.state?.user?.user_id;
      }
    } catch {}
    if (!userId) return false;
  }
  return localStorage.getItem(`${USER_SURVEY_DONE_PREFIX}${userId}`) === '1';
}

/** 清除所有用户的问卷完成状态（登出时调用） */
export function clearAllUserSurveyStatus(): void {
  if (typeof window === 'undefined') return;
  const keysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(USER_SURVEY_DONE_PREFIX)) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((k) => localStorage.removeItem(k));
}
