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

export interface RuminationProgress {
  main_section: RuminationMainSection;
  review_sub_index: number;
  filter_step: number;
  filter_table: Record<string, unknown> | null;
}

export interface RuminationTablePayload {
  columns: { key: string; label: string; options?: string[] }[];
  rows: Record<string, unknown>[];
  editableCols: string[];
  guideText?: string;
  step?: number;
}

export interface RuminationProgressSaveParams {
  main_section?: RuminationMainSection;
  review_sub_index?: number;
  filter_step?: number;
  filter_table?: Record<string, unknown> | null;
}

export const ruminationApi = {
  /** 获取 rumination 进度 */
  get: async (
    activationCode: string
  ): Promise<ApiResponse<{ progress: RuminationProgress }>> => {
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
    step = 1
  ): Promise<
    ApiResponse<{ table_widget: RuminationTablePayload | null }>
  > => {
    const res = await apiClient.get('/simple-chat/rumination-get-table', {
      params: { activation_code: activationCode, step },
    });
    return res;
  },

  /** 提交 rumination 筛选表格 */
  submitTable: async (
    activationCode: string,
    threadId: string,
    step: number,
    tableData: Record<string, unknown>[]
  ): Promise<ApiResponse<{ progress: RuminationProgress; next_step: number }>> => {
    const res = await apiClient.post('/simple-chat/rumination-table-submit', {
      activation_code: activationCode,
      thread_id: threadId,
      step,
      table_data: tableData,
    });
    return res;
  },
};
