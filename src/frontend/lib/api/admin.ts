import { apiClient, ApiResponse } from './client';

export interface AdminAnalytics {
  user_count: number;
  visit_count: number;
  dialogs_by_dimension: Record<string, number>;
  user_input_total_chars: number;
  llm_input_tokens: number;
  llm_output_tokens: number;
  report_count: number;
  last_stop_by_dimension: Record<string, number>;
  like_count: number;
  like_records: Array<{
    id: string;
    session_id: string;
    log_index: number;
    content_preview: string | null;
    dimension: string | null;
    created_at: string | null;
  }>;
}

export async function getAdminAnalytics(): Promise<ApiResponse<AdminAnalytics>> {
  return apiClient.get('/admin/analytics');
}

export async function getLikeDetail(sessionId: string, logIndex: number): Promise<ApiResponse<any>> {
  return apiClient.get('/admin/analytics/like-detail', {
    params: { session_id: sessionId, log_index: logIndex },
  });
}
