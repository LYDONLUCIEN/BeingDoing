/**
 * Per-phase chat threads (max 5 per dimension).
 * Stored in localStorage keyed by activation_code.
 */

import type { PhaseKey } from './session';

/** Rumination 表格 Widget 载荷 */
export interface RuminationTablePayload {
  columns: { key: string; label: string; options?: string[] }[];
  rows: Record<string, unknown>[];
  editableCols: string[];
  guideText?: string;
  step?: number;
}

export interface ThreadMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** Unix ms; last message time used in sidebar */
  createdAt?: number;
  /** 维度探索结论消息（与 content 二选一） */
  type?: 'text' | 'dimension_conclusion' | 'table_widget';
  conclusionData?: DimensionConclusionData;
  /** 结论卡是否已折叠（用户点击「再聊聊」后折叠） */
  conclusionCollapsed?: boolean;
  /** 结论卡是否已确认（用于前端按钮状态兜底） */
  conclusionConfirmed?: boolean;
  /** 表格 Widget 载荷（type=table_widget 时） */
  tablePayload?: RuminationTablePayload;
}

/** 维度探索结论卡片（持久化，完成/重访时仍可查看） */
export interface DimensionConclusionData {
  /** 温暖汇总文案（支持 Markdown 加粗） */
  summary?: string;
  /** 关键词列表（标签展示） */
  keywords?: string[];
  /** 兼容旧格式 */
  ai_summary?: string;
  dimension_goal?: string;
  final_answer?: string;
}

export interface ChatThread {
  id: string;
  title: string;
  status: 'in-progress' | 'completed';
  messages: ThreadMessage[];
  createdAt: number;
  /** 探索结论卡片（有则展示，用户可完善后再确认） */
  dimensionConclusion?: DimensionConclusionData;
}

export interface PhaseThreads {
  [phase: string]: ChatThread[];
}

const STORAGE_KEY = (code: string) => `explore_threads_${code}`;
const ACTIVE_KEY = (code: string) => `explore_active_thread_${code}`;
const MAX_THREADS = 5;

function loadRaw(code: string): PhaseThreads {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY(code));
    if (raw) return JSON.parse(raw);
  } catch {}
  return {};
}

function saveRaw(code: string, data: PhaseThreads) {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY(code), JSON.stringify(data));
}

export function getThreads(code: string, phase: PhaseKey): ChatThread[] {
  const data = loadRaw(code);
  return data[phase] ?? [];
}

/** 批量替换某阶段的线程列表（用于后端同步结果持久化，失败回退时可用） */
export function setThreadsForPhase(code: string, phase: PhaseKey, threads: ChatThread[]) {
  const data = loadRaw(code);
  data[phase] = threads;
  saveRaw(code, data);
}

export function saveThread(code: string, phase: PhaseKey, thread: ChatThread) {
  const data = loadRaw(code);
  const list = data[phase] ?? [];
  const idx = list.findIndex((t) => t.id === thread.id);
  if (idx >= 0) {
    list[idx] = thread;
  } else {
    list.push(thread);
    if (list.length > MAX_THREADS) list.shift();
  }
  data[phase] = list;
  saveRaw(code, data);
}

export function addThread(code: string, phase: PhaseKey, thread: ChatThread): ChatThread[] {
  const data = loadRaw(code);
  const list = data[phase] ?? [];
  if (list.length >= MAX_THREADS) list.shift();
  list.push(thread);
  data[phase] = list;
  saveRaw(code, data);
  return list;
}

export function removeThread(code: string, phase: PhaseKey, threadId: string): ChatThread[] {
  const data = loadRaw(code);
  const list = (data[phase] ?? []).filter((t) => t.id !== threadId);
  data[phase] = list;
  saveRaw(code, data);
  const activeId = getActiveThreadId(code, phase);
  if (activeId === threadId) {
    setActiveThreadId(code, phase, list.length > 0 ? list[0].id : null);
  }
  return list;
}

export function getActiveThreadId(code: string, phase: PhaseKey): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const key = ACTIVE_KEY(code);
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const map: Record<string, string> = JSON.parse(raw);
    return map[phase] ?? null;
  } catch {}
  return null;
}

export function setActiveThreadId(code: string, phase: PhaseKey, threadId: string | null) {
  if (typeof window === 'undefined') return;
  try {
    const key = ACTIVE_KEY(code);
    const raw = localStorage.getItem(key) || '{}';
    const map: Record<string, string> = JSON.parse(raw);
    if (threadId) map[phase] = threadId;
    else delete map[phase];
    localStorage.setItem(key, JSON.stringify(map));
  } catch {}
}

export function createThreadId(): string {
  return `t_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}
