import { apiClient, ApiResponse } from './client';

export interface RegisterRequest {
  email?: string;
  phone?: string;
  username?: string;
  password: string;
}

export interface LoginRequest {
  email?: string;
  phone?: string;
  password: string;
}

export interface AuthResponse {
  user_id: string;
  email?: string;
  phone?: string;
  username?: string;
  token: string;
  expires_in: number;
}

export const authApi = {
  register: async (data: RegisterRequest): Promise<ApiResponse<AuthResponse>> => {
    return apiClient.post('/auth/register', data);
  },

  login: async (data: LoginRequest): Promise<ApiResponse<AuthResponse>> => {
    const response = await apiClient.post('/auth/login', data);
    // 保存Token
    if (response.data?.token) {
      apiClient.setToken(response.data.token);
    }
    return response;
  },

  getCurrentUser: async (): Promise<ApiResponse<any>> => {
    return apiClient.get('/auth/me');
  },
};
