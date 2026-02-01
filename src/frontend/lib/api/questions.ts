import { apiClient, ApiResponse } from './client';

export interface Question {
  id: number;
  category: string;
  question_number: number;
  content: string;
  is_starred: boolean;
}

export const questionsApi = {
  getQuestions: async (category?: string): Promise<ApiResponse<{ questions: Question[]; count: number }>> => {
    return apiClient.get('/questions', { params: { category } });
  },

  getQuestion: async (questionId: number): Promise<ApiResponse<Question>> => {
    return apiClient.get(`/questions/${questionId}`);
  },

  getGuideQuestions: async (currentStep: string, limit: number = 5): Promise<ApiResponse<{ questions: Question[]; count: number }>> => {
    return apiClient.get('/questions/guide-questions/list', {
      params: { current_step: currentStep, limit },
    });
  },

  getStarredQuestions: async (category: string): Promise<ApiResponse<{ questions: Question[]; count: number }>> => {
    return apiClient.get('/questions/starred/list', {
      params: { category },
    });
  },
};
