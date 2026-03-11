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

export interface SyncFromHistoryResult {
  synced: number;
  skipped: number;
  total_entries: number;
}

export async function syncAnalyticsFromHistory(): Promise<ApiResponse<SyncFromHistoryResult>> {
  return apiClient.post('/admin/analytics/sync-from-history');
}

export interface ChatRecord {
  id: string;
  session_id: string;
  dimension: string;
  user_input_chars: number;
  llm_input_tokens: number;
  llm_output_tokens: number;
  log_index: number | null;
  created_at: string | null;
  user_id?: string | null;
  username?: string | null;
  activation_code?: string | null;
}

export interface ChatRecordsResponse {
  records: ChatRecord[];
  total: number;
  page: number;
  page_size: number;
}

export function getChatRecords(params: {
  page?: number;
  page_size?: number;
  dimension?: string;
  session_id?: string;
}): Promise<ApiResponse<ChatRecordsResponse>> {
  return apiClient.get('/admin/analytics/chat-records', { params });
}

export interface SessionDetailRuns {
  source: 'runs';
  session_id: string;
  turns: Array<{ log_index: number; entry: Record<string, unknown> }>;
}

export interface SessionDetailSimple {
  source: 'simple';
  session_id: string;
  conversations: Record<string, Array<{ role?: string; content?: string; created_at?: string }>>;
}

export function getSessionDetail(sessionId: string): Promise<ApiResponse<SessionDetailRuns | SessionDetailSimple | null>> {
  return apiClient.get('/admin/analytics/session-detail', { params: { session_id: sessionId } });
}
