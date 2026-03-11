import { apiClient, ApiResponse } from './client';

export async function recordLike(data: {
  session_id: string;
  log_index: number;
  content_preview?: string;
  dimension?: string;
}): Promise<ApiResponse<{ recorded: boolean }>> {
  return apiClient.post('/analytics/like', data);
}

export async function recordReportGenerated(data: {
  session_id: string;
  activation_code?: string;
}): Promise<ApiResponse<{ recorded: boolean }>> {
  return apiClient.post('/analytics/report-generated', data);
}
