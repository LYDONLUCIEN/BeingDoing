/**
 * Rumination v4 API client + 类型定义（2026-08-06 版，ADR-0015）
 *
 * 端点前缀: /simple-chat/rumination-v4
 * 变更: chips/tool/双信号/兜底协议删除;结论卡仅 hypothesis(用户手填);
 *       平衡点判定为独立后台 AI(confirm/analysis-stream 两条 SSE)
 */

import { apiClient, ApiResponse } from '@/lib/api/client';

// ── 类型定义(与后端 schema 对齐)──────────────────────────────────────
export type ComboStatus = 'discussing' | 'concluded' | 'abandoned';
export type MainSection = 'matrix' | 'combo_session' | 'final_selection' | 'end';

/** hypothesis 恒为字符串(旧 dict 形态已废弃,仅存于历史数据) */
export type Hypothesis = string | Record<string, string> | null;

export interface ComboMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts?: string;
}

/** 结论卡(ADR-0015:仅 hypothesis 一字段,用户手写/可改;balance 两字段为后台判定结果) */
export interface ConclusionCard {
  hypothesis: Hypothesis;
  /** 平衡点判定结果(后台隐藏字段;null=未判定/证据不足) */
  balance_found: boolean | null;
  /** 未找到平衡点时的原因说明(balance_found=false 时有值) */
  balance_fail_reason: string | null;
  created_at: string;
  updated_at: string;
}

/** 平衡点判定状态(ADR-0015);null = 未判定 */
export interface BalanceAnalysis {
  status: 'analyzing' | 'done' | 'failed';
  balance_found: boolean | null;
  balance_fail_reason: string | null;
  started_at: string;
  finished_at: string | null;
  error: string | null;
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
  conclusion_card: ConclusionCard | null;
  balance_analysis: BalanceAnalysis | null;
  /** 用户主动跳过(status=abandoned 时置 true,卡内容保留、可逆) */
  user_skipped?: boolean;
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
  /** 用户主动跳过 */
  user_skipped?: boolean;
  balance_analysis?: BalanceAnalysis | null;
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
  /** 开场弹窗是否已展示(2026-08-10:每激活码首次进入 v4 页面弹一次) */
  intro_shown?: boolean;
}

// ── API 调用 ──────────────────────────────────────────────────────────
const PREFIX = '/simple-chat/rumination-v4';

/** v3/v4 分组判定结果 */
export interface RuminationVersionInfo {
  version: 'v3' | 'v4';
  source: 'forced' | 'ab';
  assigned_at: string | null;
  ratio_at_assignment: number | null;
}

/** 查询该 report 应走的 rumination 版本(后端权威,首次分配后续稳定) */
export async function fetchRuminationVersion(activationCode: string) {
  return apiClient.get<RuminationVersionInfo>(
    `${PREFIX}/version`,
    { params: { activation_code: activationCode } }
  );
}

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

/** 原子操作:创建 combo + 唤起引导语开场,一次调用完成 */
export async function createAndStart(activationCode: string, passion: string, strengths: string[]) {
  return apiClient.post<{ combo_id: string; combo: ComboSession; opening: ComboMessage }>(
    `${PREFIX}/create-and-start`,
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

/** 用户手填/修改结论卡 hypothesis(ADR-0015:改即作废旧判定,已确认卡退回 discussing) */
export async function patchConclusionCard(
  activationCode: string,
  comboId: string,
  hypothesis: string
) {
  return apiClient.patch<{ conclusion_card: ConclusionCard; combo: ComboSession }>(
    `${PREFIX}/combos/${comboId}/conclusion-card`,
    { activation_code: activationCode, hypothesis }
  );
}

/** 跳过(abandoned)/再聊聊(discussing);确认(concluded)走 streamConfirmConclusion */
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

/** 标记 v4 开场弹窗已展示(每激活码仅首次进入弹一次,纯 UI 标记) */
export async function markV4IntroShown(activationCode: string) {
  return apiClient.post<{ intro_shown: boolean }>(
    `${PREFIX}/intro-shown`,
    { activation_code: activationCode }
  );
}

// ── SSE 流式 ──────────────────────────────────────────────────────────

export interface SseStreamHandle<T> {
  /** 订阅事件,callback 返回 false 可提前中断 */
  subscribe: (onEvent: (e: T) => void | Promise<void>) => void;
  /** 主动中断 */
  abort: () => void;
  /** promise,流结束后 resolve */
  done: Promise<void>;
}

function resolveApiBaseURL(): string {
  const API_URL = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  if (API_URL) return `${API_URL.replace(/\/+$/, '')}/api/v1`;
  return '/api/v1';
}

/** 通用 SSE POST 流(fetch + ReadableStream 手解 data: 帧) */
function createSseStream<T extends { error?: string }>(
  path: string,
  body: Record<string, unknown>,
  token?: string
): SseStreamHandle<T> {
  const controller = new AbortController();
  let resolveDone: () => void;
  const donePromise = new Promise<void>((res) => {
    resolveDone = res;
  });
  let subscriber: ((e: T) => void | Promise<void>) | null = null;
  // 注:TS 在 async 闭包内对 let 变量的类型收窄会退化为 never,用 accessor 取最新值
  const getSubscriber = (): ((e: T) => void | Promise<void>) | null => subscriber;

  (async () => {
    try {
      const resp = await fetch(`${resolveApiBaseURL()}${PREFIX}${path}`, {
        method: 'POST',
        credentials: 'include',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
      if (!resp.ok || !resp.body) {
        let detail = `HTTP ${resp.status}`;
        try {
          const errBody = await resp.json();
          if (errBody?.detail) detail = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail);
        } catch { /* ignore */ }
        const cb = getSubscriber();
        if (cb) await Promise.resolve(cb({ error: detail } as T));
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
            const evt = JSON.parse(payload) as T;
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
      if (cb) await Promise.resolve(cb({ error: String(e?.message || e) } as T));
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

/**
 * 主对话(SSE 流式)。
 *
 * 服务端事件类型(2026-08-06 起纯对话,无 chips/结论卡/兜底事件):
 * - { chunk: string }        —— 文本增量
 * - { think_start: true }    —— 思考开始
 * - { think_chunk: string }  —— 思考增量
 * - { think_end: string }    —— 思考结束
 * - { done: true }           —— 流结束
 */
export interface ComboChatEvent {
  chunk?: string;
  think_start?: boolean;
  think_chunk?: string;
  think_end?: string;
  done?: boolean;
  error?: string;
}

export function streamComboChat(
  activationCode: string,
  comboId: string,
  message: string,
  token?: string
): SseStreamHandle<ComboChatEvent> {
  return createSseStream<ComboChatEvent>(
    '/combo-chat',
    { activation_code: activationCode, combo_id: comboId, message },
    token
  );
}

/**
 * 平衡点判定 SSE 事件(confirm / analysis-stream 共用):
 * - { analysis_status: 'analyzing' | 'none' }  —— 已进入判定 / 无判定记录
 * - { analysis_done: { balance_found, balance_fail_reason } } —— 判定完成
 * - { analysis_failed: { error } }             —— 判定失败(可重试)
 * - { done: true }                             —— 流结束
 */
export interface BalanceAnalysisEvent {
  analysis_status?: 'analyzing' | 'none';
  analysis_done?: { balance_found: boolean | null; balance_fail_reason: string | null };
  analysis_failed?: { error: string };
  done?: boolean;
  error?: string;
}

/** 确认结论卡(含平衡点判定;失败重试也走这里) */
export function streamConfirmConclusion(
  activationCode: string,
  comboId: string,
  token?: string
): SseStreamHandle<BalanceAnalysisEvent> {
  return createSseStream<BalanceAnalysisEvent>(
    `/combos/${comboId}/conclusion-card/confirm`,
    { activation_code: activationCode },
    token
  );
}

/** 判定结果补拉/附着(刷新/重进页面后发现 analyzing 时调用) */
export function streamAnalysis(
  activationCode: string,
  comboId: string,
  token?: string
): SseStreamHandle<BalanceAnalysisEvent> {
  return createSseStream<BalanceAnalysisEvent>(
    `/combos/${comboId}/analysis/stream`,
    { activation_code: activationCode },
    token
  );
}
