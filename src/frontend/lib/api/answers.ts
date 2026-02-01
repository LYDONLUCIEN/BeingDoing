import { apiClient, ApiResponse } from './client';

export interface Answer {
  id: string;
  session_id: string;
  question_id?: number;
  category: string;
  content: string;
  metadata?: any;
  created_at: string;
  updated_at: string;
}

export interface SubmitAnswerRequest {
  session_id: string;
  category: string;
  content: string;
  question_id?: number;
  metadata?: any;
}

export interface UpdateAnswerRequest {
  content?: string;
  metadata?: any;
}

export const answersApi = {
  submit: async (data: SubmitAnswerRequest): Promise<ApiResponse<Answer>> => {
    return apiClient.post('/answers', data);
  },

  update: async (answerId: string, data: UpdateAnswerRequest): Promise<ApiResponse<Answer>> => {
    return apiClient.patch(`/answers/${answerId}`, data);
  },

  getAnswers: async (sessionId: string, category?: string): Promise<ApiResponse<{ answers: Answer[]; count: number }>> => {
    return apiClient.get('/answers', {
      params: { session_id: sessionId, category },
    });
  },

  getAnswer: async (answerId: string): Promise<ApiResponse<Answer>> => {
    return apiClient.get(`/answers/${answerId}`);
  },
};
