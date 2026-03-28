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

export interface PasswordResetCodeRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  email: string;
  code: string;
  new_password: string;
}

export interface RefreshTokenResponse {
  token: string;
  expires_in: number;
}

export const authApi = {
  register: async (data: RegisterRequest): Promise<ApiResponse<AuthResponse>> => {
    const response = await apiClient.post('/auth/register', data);
    if (response.data?.token) {
      apiClient.setToken(response.data.token);
    }
    return response;
  },

  login: async (data: LoginRequest): Promise<ApiResponse<AuthResponse>> => {
    const response = await apiClient.post('/auth/login', data);
    if (response.data?.token) {
      apiClient.setToken(response.data.token);
    }
    return response;
  },

  getCurrentUser: async (): Promise<ApiResponse<any>> => {
    return apiClient.get('/auth/me');
  },

  requestPasswordResetCode: async (data: PasswordResetCodeRequest): Promise<ApiResponse<void>> => {
    return apiClient.post('/auth/password/reset/code', data);
  },

  confirmPasswordReset: async (data: PasswordResetConfirmRequest): Promise<ApiResponse<void>> => {
    return apiClient.post('/auth/password/reset/confirm', data);
  },

  refresh: async (): Promise<ApiResponse<RefreshTokenResponse>> => {
    return apiClient.post('/auth/refresh', {});
  },

  logout: async (): Promise<ApiResponse<{ logged_out: boolean }>> => {
    return apiClient.post('/auth/logout', {});
  },
};
