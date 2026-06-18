/**
 * Rumination 阶段进度 API
 */

import { apiClient, ApiResponse } from './client';

export type RuminationMainSection =
  | 'opening'
  | 'review'
  | 'filter'
  | 'final_choice'
  | 'recommend'
  | 'end';

/** 每步表格快照：initial=首次生成；submitted=确认后（用于回退查看）；skipped=短链跳过 */
export type RuminationStepSnapshot = {
  initial?: Record<string, unknown>[] | null;
  submitted?: Record<string, unknown>[] | null;
  skipped?: boolean;
};

/** 表格确认闸门：待提交暂存 + 跟进状态（与后端 rumination_progress 对齐） */
export type RuminationNegStateStatus = 'awaiting_choice' | 'exploring' | 'closed';

export interface RuminationNegState {
  status: RuminationNegStateStatus;
  step?: number;
  kind?: string;
  items?: Record<string, unknown>[];
  /** 0-based，深入讨论当前条目索引 */
  current_index?: number;
  /** UI 条带：第 i / N 条 + 字段 */
  progress_header_zh?: string;
  llm_failed?: boolean;
  injection_zh?: string;
  opening_zh?: string;
  bar_copy_zh?: string;
}

export interface RuminationProgress {
  schema_version?: number;
  main_section: RuminationMainSection;
  review_sub_index: number;
  filter_step: number;
  filter_row_cursor?: number;
  hypothesis_round?: number;
  filter_table: Record<string, unknown>[] | null;
  filter_early_terminated?: boolean;
  filter_terminate_reason?: string | null;
  filter_step_snapshots?: Record<string, RuminationStepSnapshot>;
  pending_table_submit?: { step: number; table_data: Record<string, unknown>[] } | null;
  rumination_neg_state?: RuminationNegState | null;
  /** 每子步「深入聊聊」闸门首次触发标记集合（已触发的子步号列表） */
  neg_gate_triggered_steps?: number[];
  /** v3: filter_step=3 子阶段：null=旧版 | "matrix"=组合假设填写 | "discussion"=深度讨论(3b) */
  filter_sub_step?: string | null;
  /** v3: {combo_id: {text, state}} */
  combo_conclusions?: Record<string, { text: string; state: 'empty' | 'confirmed' | 'skipped' }>;
  /** v3: 组合矩阵列表 */
  combo_matrix?: ComboItem[] | null;
  /** v3: 用户勾选不再提示完成弹窗 */
  combo_completion_modal_dismissed?: boolean;
}

export interface ComboItem {
  combo_id: string;
  passion_idx: number;
  strength_idx: number;
  passion_name: string;
  strength_name: string;
}

export interface RuminationTablePayload {
  columns: { key: string; label: string; options?: string[] }[];
  rows: Record<string, unknown>[];
  editableCols: string[];
  guideText?: string;
  step?: number;
  singleRowMode?: boolean;
  rowCursor?: number;
  totalRows?: number;
  rowSelectionMode?: 'multi';
  rowSelectionMin?: number;
  rowSelectionMax?: number;
  /** 价值观关键词来源标签（step 4 专用：confirmed_card / report_anchor / prior_text / none） */
  valuesSource?: string;
}

export interface RuminationProgressSaveParams {
  main_section?: RuminationMainSection;
  review_sub_index?: number;
  filter_step?: number;
  filter_sub_step?: string;
  filter_table?: Record<string, unknown>[] | null;
  filter_row_cursor?: number;
  hypothesis_round?: number;
  filter_early_terminated?: boolean;
  filter_terminate_reason?: string | null;
  /** 子步 3 表格显式触发：none=选「无」；hypothesis_commit=填假设失焦/确认 */
  step3_trigger?: 'none' | 'hypothesis_commit';
  combo_conclusions?: Record<string, unknown>;
  combo_completion_modal_dismissed?: boolean;
}

export type RuminationStep3SideEffect =
  | {
      type: 'skip_row';
      message: string;
      from_row: number;
      to_row: number;
    }
  | {
      type: 'confirm_prompt';
      message: string;
      row: number;
    };

export type RuminationSubmitMode = 'full_step' | 'single_row';

export interface RuminationTableSubmitOptions {
  mode?: RuminationSubmitMode;
  rowId?: string;
  patch?: Record<string, unknown>;
  preferSingleRow?: boolean;
  /** 终步多选提交时传行 id（与 table_data 内 __pick 二选一） */
  selectedRowIds?: string[];
  /** 内部：闸门 resolve 后再次提交 */
  negForceCommit?: boolean;
}

export interface RuminationNegConfirmPayload {
  filter_step: number;
  kind?: string;
  items?: Record<string, unknown>[];
  bar_copy_zh?: string;
  llm_failed?: boolean;
}

export interface RuminationSubmitData {
  progress: RuminationProgress;
  next_step: number;
  /** rumination 终表提交后进入过渡页（无结论卡） */
  next_action?:
    | 'rumination_finalize_transition'
    | 'rumination_neg_confirm'
    | 'rumination_neg_deep_started'
    | 'rumination_neg_deep_ended'
    | 'rumination_step3b_entry'
    | string;
  next_table_widget?: RuminationTablePayload;
  full_table_preview?: Record<string, unknown>[];
  early_terminated?: boolean;
  terminate_reason?: string;
  max_reached_filter_step?: number;
  neg_confirm?: RuminationNegConfirmPayload;
  opening_zh?: string;
}

/** 筛选子步右侧引导：固定文案或 LLM（后端 `domain/rumination_step_guidance.py`） */
export type RuminationStepOpeningMode = 'fixed' | 'llm';

export interface RuminationStepOpeningPayload {
  mode: RuminationStepOpeningMode;
  text: string | null;
  filter_step: number;
}

export const ruminationApi = {
  /** 获取 rumination 进度 */
  get: async (
    activationCode: string
  ): Promise<
    ApiResponse<{ progress: RuminationProgress; max_reached_filter_step?: number }>
  > => {
    const res = await apiClient.get('/simple-chat/rumination-progress', {
      params: { activation_code: activationCode },
    });
    return res;
  },

  /** 保存 rumination 进度 */
  save: async (
    activationCode: string,
    params: RuminationProgressSaveParams
  ): Promise<
    ApiResponse<{ progress: RuminationProgress; step3_side_effect?: RuminationStep3SideEffect }>
  > => {
    const res = await apiClient.post('/simple-chat/rumination-progress', {
      activation_code: activationCode,
      ...params,
    });
    return res;
  },

  /** 获取 rumination 筛选表格（进入筛选或下一步） */
  getTable: async (
    activationCode: string,
    step?: number,
    opts?: {
      singleRowMode?: boolean;
      preferSingleRow?: boolean;
      resetInitial?: boolean;
    }
  ): Promise<
    ApiResponse<{
      table_widget: RuminationTablePayload | null;
      progress?: RuminationProgress;
      filter_complete?: boolean;
      max_reached_filter_step?: number;
    }>
  > => {
    const params: Record<string, string | number | boolean> = {
      activation_code: activationCode,
    };
    if (step !== undefined) params.step = step;
    if (opts?.singleRowMode) params.single_row_mode = true;
    if (opts?.preferSingleRow) params.prefer_single_row = true;
    if (opts?.resetInitial) params.reset_initial = true;
    const res = await apiClient.get('/simple-chat/rumination-get-table', { params });
    return res;
  },

  /** 提交 rumination 筛选表格 */
  submitTable: async (
    activationCode: string,
    threadId: string,
    step: number,
    tableData: Record<string, unknown>[] | null | undefined,
    options?: RuminationTableSubmitOptions
  ): Promise<ApiResponse<RuminationSubmitData>> => {
    const body: Record<string, unknown> = {
      activation_code: activationCode,
      thread_id: threadId,
      step,
      table_data: tableData ?? null,
      mode: options?.mode ?? 'full_step',
    };
    if (options?.rowId != null) body.row_id = options.rowId;
    if (options?.patch != null) body.patch = options.patch;
    if (options?.preferSingleRow != null) body.prefer_single_row = options.preferSingleRow;
    if (options?.selectedRowIds?.length) body.selected_row_ids = options.selectedRowIds;
    if (options?.negForceCommit) body.neg_force_commit = true;
    const res = await apiClient.post('/simple-chat/rumination-table-submit', body, {
      timeout: 60_000,
    });
    return res;
  },

  /** 表格闸门：继续推进 / 深入讨论 / 结束讨论 */
  negResolve: async (
    activationCode: string,
    threadId: string,
    action: 'continue' | 'deep_start' | 'deep_end' | 'dismiss'
  ): Promise<ApiResponse<RuminationSubmitData>> => {
    const res = await apiClient.post(
      '/simple-chat/rumination-neg-resolve',
      {
        activation_code: activationCode,
        thread_id: threadId,
        action,
      },
      { timeout: 60_000 }
    );
    return res;
  },

  /** 获取进入某筛选子步时的引导配置（固定文案或标记为 llm） */
  getStepOpening: (
    activationCode: string,
    filterStep: number
  ): Promise<ApiResponse<RuminationStepOpeningPayload>> =>
    apiClient.get<RuminationStepOpeningPayload>('/simple-chat/rumination-step-opening', {
      params: {
        activation_code: activationCode,
        filter_step: filterStep,
      },
    }),

  /** v3: 获取或初始化组合矩阵 */
  getComboMatrix: async (
    activationCode: string,
  ): Promise<
    ApiResponse<{ progress: RuminationProgress; combo_matrix?: ComboItem[] | null }>
  > => {
    const res = await apiClient.get('/simple-chat/rumination-combo-matrix', {
      params: { activation_code: activationCode },
    });
    return res;
  },

  /** v3: 保存单个组合的结论状态（确认/跳过） */
  saveComboConclusion: async (
    activationCode: string,
    comboId: string,
    action: 'confirm' | 'skip',
    text?: string,
  ): Promise<ApiResponse<{ progress: RuminationProgress }>> => {
    const res = await apiClient.post('/simple-chat/rumination-combo-conclusion', {
      activation_code: activationCode,
      combo_id: comboId,
      action,
      text,
    });
    return res;
  },

  /** v3: 确保单个组合已存在固定引导语；不存在则入队异步生成 */
  ensureComboGuide: async (
    activationCode: string,
    comboId: string,
    threadId?: string,
  ): Promise<
    ApiResponse<{
      created: boolean;
      status?: 'queued' | null;
      combo_id?: string;
      message?: Record<string, unknown> | null;
    }>
  > => {
    const res = await apiClient.post('/simple-chat/rumination-combo-guide', {
      activation_code: activationCode,
      combo_id: comboId,
      thread_id: threadId,
    });
    return res;
  },

  /** Poll /history until a combo guide appears for the given comboId */
  pollComboGuide: async (
    activationCode: string,
    comboId: string,
    threadId?: string,
    maxPolls: number = 20,
    intervalMs: number = 2000,
  ): Promise<Record<string, unknown> | null> => {
    for (let i = 0; i < maxPolls; i++) {
      try {
        const h = await apiClient.get('/simple-chat/history', {
          params: { activation_code: activationCode, phase: 'rumination', thread_id: threadId },
        });
        const messages: any[] = (h as any).data?.messages ?? [];
        const guide = messages.find(
          (m) => m.combo_id === comboId && m.role === 'assistant' && m.type === 'combo_guide',
        );
        if (guide) return guide;
      } catch {
        // ignore, retry
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    return null;
  },

  /** v3: 提交组合矩阵，进入 3b 深度讨论 */
  submitComboMatrix: async (
    activationCode: string,
    threadId?: string,
  ): Promise<
    ApiResponse<{
      progress: RuminationProgress;
      next_action?: string;
      next_table_widget?: RuminationTablePayload;
      confirmed_count?: number;
    }>
  > => {
    const res = await apiClient.post('/simple-chat/rumination-combo-matrix-submit', {
      activation_code: activationCode,
      thread_id: threadId,
    });
    return res;
  },
};
