/**
 * Client-side session state for the step-by-step explore flow.
 * Persisted in localStorage keyed by activation_code.
 */

export type PhaseKey = 'values' | 'strengths' | 'interests' | 'purpose';

export const PHASES: { key: PhaseKey; label: string; color: string; num: string }[] = [
  { key: 'values',    label: '信念',  color: 'blue',    num: '01' },
  { key: 'strengths', label: '禀赋',  color: 'amber',   num: '02' },
  { key: 'interests', label: '热忱',  color: 'rose',    num: '03' },
  { key: 'purpose',   label: '使命',  color: 'emerald', num: '04' },
];

export interface ExploreSession {
  activationCode: string;
  unlockedPhases: PhaseKey[];
  currentPhase: PhaseKey;
  surveyCompleted: boolean;
  /** 是否已生成报告（完成使命后通过渲染预备页） */
  reportReady?: boolean;
}

/** 检查是否有可查看的报告（完成全部四阶段探索） */
export function hasReportAvailable(session: ExploreSession): boolean {
  return session.unlockedPhases.includes('purpose');
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
