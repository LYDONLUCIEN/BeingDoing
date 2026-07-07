/**
 * Rumination v4 API client + 类型定义
 *
 * 见 wiki/开发文档/0707-tag1.6.0.md
 * 端点前缀: /simple-chat/rumination-v4
 */

import { apiClient, ApiResponse } from '@/lib/api/client';

// ── 类型定义(与后端 schema 对齐)──────────────────────────────────────
export type ComboStatus = 'discussing' | 'concluded' | 'abandoned';
export type MainSection = 'matrix' | 'combo_session' | 'final_selection' | 'end';
export type PassionMark = '忍不住想做' | '应该做' | null;
export type TimingMark = '现在' | '未来' | null;

/** hypothesis 可以是字符串(整体)或字典(分优势) */
export type Hypothesis = string | Record<string, string> | null;

export interface ComboMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts?: string;
}

export interface FieldsCollected {
  motivation: string | null;
  hypothesis: Hypothesis;
  work_purposes: string[] | null;
  passion_mark: PassionMark;
  timing_mark: TimingMark;
}

export interface ConclusionCard extends FieldsCollected {
  created_at: string;
  updated_at: string;
}

export interface ComboSession {
  combo_id: string;
  passion: string;
  strengths: string[];
  created_at: string;
  updated_at: string;
  status: ComboStatus;
  messages: ComboMessage[];
  summary: string | null;
  summary_last_round: number;
  fields_collected: FieldsCollected;
  conclusion_card: ConclusionCard | null;
}

export interface ComboMeta {
  combo_id: string;
  passion: string;
  strengths: string[];
  status: ComboStatus;
  created_at: string;
  updated_at: string;
  has_card: boolean;
  round_count: number;
}

export interface FinalSelection {
  selected_combo_ids: string[];
  submitted: boolean;
  submitted_at: string | null;
}

export interface RuminationV4State {
  schema_version: number;
  matrix_snapshot: { passions: string[]; strengths: string[] };
  combo_sessions: ComboSession[];
  active_combo_id: string | null;
  final_selection: FinalSelection;
  main_section: MainSection;
}

// ── API 调用 ──────────────────────────────────────────────────────────
const PREFIX = '/simple-chat/rumination-v4';

export async function fetchV4State(activationCode: string) {
  return apiClient.get<{ state: RuminationV4State; combos: ComboMeta[] }>(
    `${PREFIX}/state`,
    { params: { activation_code: activationCode } }
  );
}

export async function fetchCombos(activationCode: string) {
  return apiClient.get<{ combos: ComboMeta[]; active_combo_id: string | null }>(
    `${PREFIX}/combos`,
    { params: { activation_code: activationCode } }
  );
}

export async function fetchComboDetail(activationCode: string, comboId: string) {
  return apiClient.get<{ combo: ComboSession }>(
    `${PREFIX}/combos/${comboId}`,
    { params: { activation_code: activationCode } }
  );
}

export async function createCombo(activationCode: string, passion: string, strengths: string[]) {
  return apiClient.post<{ combo_id: string; combo: ComboSession }>(
    `${PREFIX}/create-combo`,
    { activation_code: activationCode, passion, strengths }
  );
}

export async function startDiscussion(activationCode: string, comboId: string) {
  return apiClient.post<{ opening: ComboMessage }>(
    `${PREFIX}/start-discussion`,
    { activation_code: activationCode, combo_id: comboId }
  );
}

export async function deleteCombo(activationCode: string, comboId: string) {
  return apiClient.delete<{ combos: ComboMeta[]; active_combo_id: string | null }>(
    `${PREFIX}/combos/${comboId}`,
    { params: { activation_code: activationCode } }
  );
}

export async function patchConclusionCard(
  activationCode: string,
  comboId: string,
  fields: Partial<FieldsCollected>
) {
  return apiClient.patch<{ conclusion_card: ConclusionCard }>(
    `${PREFIX}/combos/${comboId}/conclusion-card`,
    { activation_code: activationCode, ...fields }
  );
}

export async function setComboStatus(activationCode: string, comboId: string, status: ComboStatus) {
  return apiClient.post<{ combo: ComboSession }>(
    `${PREFIX}/combos/${comboId}/status`,
    { activation_code: activationCode, status }
  );
}

export async function setActiveCombo(activationCode: string, comboId: string) {
  return apiClient.post<{ active_combo_id: string }>(
    `${PREFIX}/active`,
    { activation_code: activationCode, combo_id: comboId }
  );
}

export async function updateFinalSelection(activationCode: string, selectedComboIds: string[]) {
  return apiClient.post<{ final_selection: FinalSelection }>(
    `${PREFIX}/final-selection`,
    { activation_code: activationCode, selected_combo_ids: selectedComboIds }
  );
}

export async function submitFinalSelection(activationCode: string) {
  return apiClient.post<{ final_selection: FinalSelection; main_section: MainSection }>(
    `${PREFIX}/final-selection/submit`,
    { activation_code: activationCode }
  );
}

/**
 * 发送 combo 对话消息(SSE 流式)。
 * 返回一个可订阅的事件迭代器,以及 abort 句柄。
 *
 * 服务端事件类型:
 * - { chunk: string }           —— 文本增量
 * - { think_start: true }       —— 思考开始
 * - { think_chunk: string }     —— 思考增量
 * - { think_end: string }       —— 思考结束
 * - { fallback: true }          —— 兜底触发中
 * - { conclusion_card: Card }   —— 结论卡(展示)
 * - { tool_errors: string[] }   —— tool 调用错误(调试)
 * - { done: true }              —— 流结束
 */
export interface ComboChatEvent {
  chunk?: string;
  think_start?: boolean;
  think_chunk?: string;
  think_end?: string;
  fallback?: boolean;
  conclusion_card?: ConclusionCard;
  tool_errors?: string[];
  done?: boolean;
  error?: string;
}

export interface ComboChatHandle {
  /** 订阅事件,callback 返回 false 可提前中断 */
  subscribe: (onEvent: (e: ComboChatEvent) => void | Promise<void>) => void;
  /** 主动中断 */
  abort: () => void;
  /** promise,流结束后 resolve */
  done: Promise<void>;
}

export function streamComboChat(
  activationCode: string,
  comboId: string,
  message: string,
  token?: string
): ComboChatHandle {
  const controller = new AbortController();
  let resolveDone: () => void;
  let rejectDone: (e: any) => void;
  const donePromise = new Promise<void>((res, rej) => {
    resolveDone = res;
    rejectDone = rej;
  });
  let subscriber: ((e: ComboChatEvent) => void | Promise<void>) | null = null;
  // 注:TS 在 async 闭包内对 let 变量的类型收窄会退化为 never,用 accessor 取最新值
  const getSubscriber = (): ((e: ComboChatEvent) => void | Promise<void>) | null => subscriber;

  (async () => {
    try {
      // 解析 baseURL:优先 NEXT_PUBLIC_API_URL,否则同域 /api/v1
      const API_URL = (process.env.NEXT_PUBLIC_API_URL || '').trim();
      let baseURL = '/api/v1';
      if (API_URL) {
        baseURL = `${API_URL.replace(/\/+$/, '')}/api/v1`;
      }
      const resp = await fetch(`${baseURL}${PREFIX}/combo-chat`, {
        method: 'POST',
        credentials: 'include',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ activation_code: activationCode, combo_id: comboId, message }),
      });
      if (!resp.ok || !resp.body) {
        const cb = getSubscriber();
        if (cb) await Promise.resolve(cb({ error: `HTTP ${resp.status}` }));
        resolveDone!();
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // SSE 协议:data: {...}\n\n
        let idx: number;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const raw = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const line = raw.trim();
          if (!line.startsWith('data:')) continue;
          const payload = line.slice(5).trim();
          if (!payload) continue;
          try {
            const evt = JSON.parse(payload) as ComboChatEvent;
            const cb = getSubscriber();
            if (cb) await Promise.resolve(cb(evt));
          } catch {
            // 忽略非 JSON
          }
        }
      }
      resolveDone!();
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        resolveDone!();
        return;
      }
      const cb = getSubscriber();
      if (cb) await Promise.resolve(cb({ error: String(e?.message || e) }));
      resolveDone!();
    }
  })();

  return {
    subscribe: (cb) => {
      subscriber = cb;
    },
    abort: () => controller.abort(),
    done: donePromise,
  };
}
