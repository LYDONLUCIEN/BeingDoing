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
  /** 后端单行确认模式 */
  singleRowMode?: boolean;
  rowCursor?: number;
  totalRows?: number;
  /** 价值观关键词来源标签（step 4 专用：confirmed_card / report_anchor / prior_text / none） */
  valuesSource?: string;
}

export interface ThreadMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** Unix ms; last message time used in sidebar */
  createdAt?: number;
  /** 推理模型思考过程（deepseek-reasoner 等），折叠展示 */
  thinkContent?: string;
  /** 思考中（流式时占位提示，不持久化） */
  thinkStreaming?: boolean;
  /** 思考过程实时输出预览（单行展示，不持久化） */
  thinkChunkContent?: string;
  /** 维度探索结论消息（与 content 二选一） */
  type?: 'text' | 'dimension_conclusion' | 'table_widget';
  conclusionData?: DimensionConclusionData;
  /** 结论卡是否已折叠（用户点击「再聊聊」后折叠） */
  conclusionCollapsed?: boolean;
  /** 结论卡是否已确认（用于前端按钮状态兜底） */
  conclusionConfirmed?: boolean;
  /** 结论卡是否已固化为只读（发送新消息或阶段提交后） */
  conclusionLocked?: boolean;
  /** 表格 Widget 载荷（type=table_widget 时） */
  tablePayload?: RuminationTablePayload;
  /** 沉淀：发送时绑定的表格行摘要（展示在气泡上方） */
  ruminationRowLabel?: string;
  /** 沉淀：消息所属的筛选子步（1-7），用于按子步隔离对话展示 */
  filterStep?: number | null;
  /** 子步 3：AI 生成的假设候选列表，渲染为可点击 chip */
  hypCandidates?: string[];
  /** 子步 3：表格操作类型（区分操作消息和文字消息） */
  tableAction?: 'select_none' | 'fill_hypothesis';
}

/** 使命阶段结构化「经历 → 价值观」行（与后端 payload 一致） */
export interface ExperienceValueRow {
  experience?: string;
  /** 新格式：数组（一段经历可匹配多个价值观）；兼容旧格式单字符串 */
  values?: string[];
  /** @deprecated 旧格式，保留读取兼容 */
  value?: string;
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
  /** 与 keywords 等长（价值观） */
  keyword_notes?: string[];
  /** 与 keywords 等长：a/b/c（优势标记） */
  strength_markers?: string[];
  /** 与 keywords 等长（热爱阶段选择理由） */
  interest_reasons?: string[];
  mission_core?: string;
  mission_detail?: string;
  mission_aim?: string;
  experience_value_rows?: ExperienceValueRow[];
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
const SYNC_TS_KEY = (code: string) => `explore_threads_sync_ts_${code}`;
const MAX_THREADS = 5;
/** localStorage 缓存最大有效期（毫秒），超过后强制从后端拉取 */
const CACHE_MAX_AGE_MS = 5 * 60 * 1000; // 5 分钟

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

/**
 * 沉淀阶段在多条后端线程中选出唯一「主线程」（与 collapse 规则一致）。
 * 未加载 messages 时各线程 length 视为 0，仍与 collapse 在「全空」时的择优顺序一致。
 */
export function pickCanonicalRuminationThread(threads: ChatThread[]): ChatThread | null {
  if (threads.length === 0) return null;
  const len = (x: ChatThread) => x.messages?.length ?? 0;
  return threads.reduce((a, b) => {
    if (b.createdAt > a.createdAt) return b;
    if (b.createdAt < a.createdAt) return a;
    return len(b) >= len(a) ? b : a;
  });
}

/**
 * 沉淀（rumination）阶段仅保留一条对话线程：取 createdAt 最新；相同时取消息条数更多者。
 * 用于消除历史多条线程与产品设计「单线程」不一致。
 */
export function collapseRuminationThreadsToOne(threads: ChatThread[]): ChatThread[] {
  if (threads.length <= 1) return threads;
  const best = pickCanonicalRuminationThread(threads);
  return best ? [best] : threads;
}

/** 批量替换某阶段的线程列表（用于后端同步结果持久化，失败回退时可用） */
export function setThreadsForPhase(code: string, phase: PhaseKey, threads: ChatThread[]) {
  const data = loadRaw(code);
  data[phase] = threads;
  saveRaw(code, data);
  // 记录最后同步时间
  markSynced(code);
}

/** 记录最后一次从后端成功同步的时间戳 */
export function markSynced(code: string) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(SYNC_TS_KEY(code), String(Date.now()));
  } catch {}
}

/** 判断 localStorage 缓存是否过期（超过 CACHE_MAX_AGE_MS 未从后端同步） */
export function isCacheStale(code: string): boolean {
  if (typeof window === 'undefined') return true;
  try {
    const raw = localStorage.getItem(SYNC_TS_KEY(code));
    if (!raw) return true;
    const ts = parseInt(raw, 10);
    if (isNaN(ts)) return true;
    return Date.now() - ts > CACHE_MAX_AGE_MS;
  } catch {
    return true;
  }
}

/** 清除指定激活码的所有 localStorage 缓存（用于激活码切换、登出等场景） */
export function clearThreadCache(code: string) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(STORAGE_KEY(code));
    localStorage.removeItem(ACTIVE_KEY(code));
    localStorage.removeItem(SYNC_TS_KEY(code));
  } catch {}
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

/** 与后端 `allocate_simple_chat_thread_id` 同思路：t_ + 高熵 id，降低碰撞（Simple/report 绑定更安全） */
export function createThreadId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `t_${crypto.randomUUID().replace(/-/g, '')}`;
  }
  return `t_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}
