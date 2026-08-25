import { apiClient, ApiResponse } from './client';
import { clearLastActivationCode } from '@/lib/explore/session';

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
  email_verified?: boolean;
  /** 已注销账户登录时为 "deleted"，此时 token 为受限 token（仅可调用账户恢复端点） */
  account_status?: string;
}

export interface DeleteAccountResponse {
  /** 数据永久删除时间（ISO 格式），在此之前登录可恢复账户 */
  purge_after: string;
}


export interface PasswordResetCodeRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  email: string;
  code: string;
  new_password: string;
}

export interface PasswordChangeRequest {
  old_password: string;
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
      // 换号登录：清除残留的「上次激活码」，避免串到旧账号的报告
      clearLastActivationCode();
    }
    return response;
  },

  login: async (data: LoginRequest): Promise<ApiResponse<AuthResponse>> => {
    const response = await apiClient.post('/auth/login', data);
    if (response.data?.token) {
      apiClient.setToken(response.data.token);
      // 换号登录：清除残留的「上次激活码」，避免串到旧账号的报告
      clearLastActivationCode();
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

  /** 已登录用户修改密码（旧密码 + 新密码）。成功后全部会话被强制下线，调用方需登出并引导重新登录 */
  changePassword: async (data: PasswordChangeRequest): Promise<ApiResponse<void>> => {
    return apiClient.post('/auth/password/change', data);
  },

  refresh: async (): Promise<ApiResponse<RefreshTokenResponse>> => {
    return apiClient.post('/auth/refresh', {});
  },

  logout: async (): Promise<ApiResponse<{ logged_out: boolean }>> => {
    return apiClient.post('/auth/logout', {});
  },

  /** 注销账户（需登录）。confirmText 必须为「注销我的账户」 */
  deleteAccount: async (confirmText: string): Promise<ApiResponse<DeleteAccountResponse>> => {
    return apiClient.post('/auth/account/delete', { confirm_text: confirmText });
  },

  /** 发送账户恢复邮箱验证码（需受限 token） */
  sendAccountRecoveryCode: async (): Promise<ApiResponse<void>> => {
    return apiClient.post('/auth/account/recovery/code', {});
  },

  /** 校验验证码并恢复账户（需受限 token），成功返回正式 token（refresh 经 cookie 下发，与登录一致） */
  confirmAccountRecovery: async (
    code: string
  ): Promise<ApiResponse<AuthResponse>> => {
    const response = await apiClient.post<AuthResponse>(
      '/auth/account/recovery/confirm',
      { code }
    );
    const token = response.data?.token;
    if (token) {
      apiClient.setToken(token);
    }
    return response;
  },
};
