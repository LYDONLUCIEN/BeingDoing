import { apiClient, ApiResponse } from './client';

// ──────────────── 点赞 v2 ────────────────

export interface ToggleLikeParams {
  session_id: string;
  thread_id?: string;
  message_id: string;
  role?: 'user' | 'assistant';
  content_preview?: string;
  content_snapshot?: string;
  dimension?: string;
  phase?: string;
  activation_code?: string;
  log_index?: number;
}

/** 点赞 / 取消点赞（toggle） */
export async function toggleLike(data: ToggleLikeParams): Promise<ApiResponse<{ liked: boolean }>> {
  return apiClient.post('/analytics/like', data);
}

/** 取消点赞 */
export async function unlikeMessage(messageId: string): Promise<ApiResponse<{ removed: boolean }>> {
  return apiClient.post('/analytics/unlike', { message_id: messageId });
}

export interface LikedRecord {
  id: string;
  message_id: string;
  role?: string;
  content_preview?: string;
  content_snapshot?: string;
  dimension?: string;
  phase?: string;
  thread_id?: string;
  created_at?: string;
}

export interface LikedRecordsData {
  records: LikedRecord[];
  total: number;
  limit: number;
  offset: number;
}

/** 获取点赞列表（按激活码/阶段筛选） */
export async function getLikes(params?: {
  activation_code?: string;
  phase?: string;
  limit?: number;
  offset?: number;
}): Promise<ApiResponse<LikedRecordsData>> {
  return apiClient.get('/analytics/likes', { params });
}

/** 批量查询消息点赞状态 */
export async function checkLikeStatus(
  messageIds: string[]
): Promise<ApiResponse<Record<string, boolean>>> {
  return apiClient.get('/analytics/likes/check', {
    params: { message_ids: messageIds.join(',') },
  });
}

/** 按 message_id 回查原文（可溯源） */
export async function getLikedMessageTrace(
  messageId: string
): Promise<ApiResponse<{
  message_id: string;
  role?: string;
  content: string;
  source: 'snapshot' | 'history_recovery' | 'fallback';
  content_preview?: string;
  dimension?: string;
  phase?: string;
  session_id?: string;
  thread_id?: string;
  created_at?: string;
}>> {
  return apiClient.get(`/analytics/likes/message/${messageId}`);
}

// ──────────────── 旧版兼容 ────────────────

/** 旧版点赞记录（兼容保留） */
export async function recordLike(data: {
  session_id: string;
  log_index: number;
  content_preview?: string;
  dimension?: string;
}): Promise<ApiResponse<{ recorded: boolean }>> {
  return apiClient.post('/analytics/like/legacy', data);
}

/** 记录报告生成 */
export async function recordReportGenerated(data: {
  session_id: string;
  activation_code?: string;
}): Promise<ApiResponse<{ recorded: boolean }>> {
  return apiClient.post('/analytics/report-generated', data);
}
