import { apiClient, ApiResponse } from './client';

export interface UserProfile {
  user_id: string;
  email?: string;
  phone?: string;
  username?: string;
  gender?: string;
  age?: number;
  profile_completed: boolean;
  work_histories: WorkHistory[];
}

export interface WorkHistory {
  id: string;
  company?: string;
  position?: string;
  start_date?: string;
  end_date?: string;
  evaluation?: string;
  projects: ProjectExperience[];
}

export interface ProjectExperience {
  id: string;
  name: string;
  description?: string;
  role?: string;
  achievements?: string;
}

export interface UserProfileRequest {
  gender?: string;
  age?: number;
}

export interface WorkHistoryRequest {
  company?: string;
  position?: string;
  start_date?: string;
  end_date?: string;
  evaluation?: string;
  skills_used?: string[];
}

export interface ProjectExperienceRequest {
  name: string;
  description?: string;
  role?: string;
  achievements?: string;
}

export const usersApi = {
  submitProfile: async (data: UserProfileRequest): Promise<ApiResponse<any>> => {
    return apiClient.post('/users/profile', data);
  },

  getProfile: async (): Promise<ApiResponse<UserProfile>> => {
    return apiClient.get('/users/profile');
  },

  submitWorkHistory: async (data: WorkHistoryRequest): Promise<ApiResponse<any>> => {
    return apiClient.post('/users/work-history', data);
  },

  submitProjectExperience: async (
    workHistoryId: string,
    data: ProjectExperienceRequest
  ): Promise<ApiResponse<any>> => {
    return apiClient.post(`/users/work-history/${workHistoryId}/projects`, data);
  },

  markProfileComplete: async (): Promise<ApiResponse<any>> => {
    return apiClient.post('/users/profile/complete');
  },
};
