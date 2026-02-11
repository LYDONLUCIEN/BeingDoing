import { apiClient, ApiResponse } from './client';

export interface CreateSessionRequest {
  device_id?: string;
  current_step?: string;
}

export interface Session {
  session_id: string;
  user_id?: string;
  current_step: string;
  status: string;
  created_at: string;
  updated_at: string;
  last_activity_at: string;
}

export const sessionsApi = {
  create: async (data: CreateSessionRequest): Promise<ApiResponse<Session>> => {
    return apiClient.post('/sessions', data);
  },

  list: async (): Promise<ApiResponse<{ sessions: Session[] }>> => {
    return apiClient.get('/sessions');
  },

  get: async (sessionId: string): Promise<ApiResponse<Session>> => {
    return apiClient.get(`/sessions/${sessionId}`);
  },

  delete: async (sessionId: string): Promise<ApiResponse<void>> => {
    return apiClient.delete(`/sessions/${sessionId}`);
  },

  updateProgress: async (
    sessionId: string,
    step: string,
    completedCount?: number,
    totalCount?: number
  ): Promise<ApiResponse<any>> => {
    const params = new URLSearchParams();
    params.append('step', step);
    if (completedCount !== undefined) params.append('completed_count', completedCount.toString());
    if (totalCount !== undefined) params.append('total_count', totalCount.toString());
    
    return apiClient.patch(`/sessions/${sessionId}/progress?${params.toString()}`, {});
  },
};
