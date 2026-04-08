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

/** 每步表格快照：initial=首次生成；submitted=确认后（用于回退查看） */
export type RuminationStepSnapshot = {
  initial?: Record<string, unknown>[] | null;
  submitted?: Record<string, unknown>[] | null;
};

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
}

export interface RuminationProgressSaveParams {
  main_section?: RuminationMainSection;
  review_sub_index?: number;
  filter_step?: number;
  filter_table?: Record<string, unknown>[] | null;
  filter_row_cursor?: number;
  hypothesis_round?: number;
  filter_early_terminated?: boolean;
  filter_terminate_reason?: string | null;
}

export type RuminationSubmitMode = 'full_step' | 'single_row';

export interface RuminationTableSubmitOptions {
  mode?: RuminationSubmitMode;
  rowId?: string;
  patch?: Record<string, unknown>;
  preferSingleRow?: boolean;
  /** 终步多选提交时传行 id（与 table_data 内 __pick 二选一） */
  selectedRowIds?: string[];
}

export interface RuminationSubmitData {
  progress: RuminationProgress;
  next_step: number;
  next_action?: string;
  next_table_widget?: RuminationTablePayload;
  full_table_preview?: Record<string, unknown>[];
  early_terminated?: boolean;
  terminate_reason?: string;
  max_reached_filter_step?: number;
  dimension_conclusion?: Record<string, unknown>;
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
  ): Promise<ApiResponse<{ progress: RuminationProgress }>> => {
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
    const res = await apiClient.post('/simple-chat/rumination-table-submit', body);
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

  /** 子步 3：单行重新生成假设1、假设2 */
  regenerateHypotheses: (
    activationCode: string,
    filterStep: number,
    rowId: string
  ): Promise<
    ApiResponse<{
      table_widget: RuminationTablePayload;
      progress: RuminationProgress;
      max_reached_filter_step?: number;
    }>
  > =>
    apiClient.post('/simple-chat/rumination-regenerate-hypotheses', {
      activation_code: activationCode,
      filter_step: filterStep,
      row_id: rowId,
    }),
};
