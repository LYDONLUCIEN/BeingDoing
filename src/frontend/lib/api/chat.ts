import { apiClient, ApiResponse } from './client';

export interface SendMessageRequest {
  session_id: string;
  message: string;
  current_step: string;
  category?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  context?: any;
  created_at: string;
}

export interface GuideRequest {
  session_id: string;
  current_step: string;
}

export interface GuidePreferenceRequest {
  session_id: string;
  preference: 'normal' | 'quiet';
}

export const chatApi = {
  sendMessage: async (data: SendMessageRequest): Promise<ApiResponse<{ response: string; session_id: string; tools_used: string[] }>> => {
    return apiClient.post('/chat/messages', data);
  },

  getHistory: async (sessionId: string, category?: string, limit?: number): Promise<ApiResponse<{ messages: Message[]; count: number }>> => {
    return apiClient.get('/chat/history', {
      params: { session_id: sessionId, category, limit },
    });
  },

  triggerGuide: async (data: GuideRequest): Promise<ApiResponse<{ message: string }>> => {
    return apiClient.post('/chat/guide', data);
  },

  setGuidePreference: async (data: GuidePreferenceRequest): Promise<ApiResponse<any>> => {
    return apiClient.post('/chat/guide-preference', data);
  },
};
