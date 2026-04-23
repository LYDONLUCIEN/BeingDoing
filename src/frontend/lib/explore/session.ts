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

/** history API metadata: explicit thread_id or legacy session_id (= thread). */
export function readThreadIdFromHistoryMetadata(
  meta: Record<string, unknown> | null | undefined
): string | undefined {
  if (!meta) return undefined;
  const t = meta.thread_id ?? meta.session_id;
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
  const nextKey = keys[currentIdx + 1];
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
