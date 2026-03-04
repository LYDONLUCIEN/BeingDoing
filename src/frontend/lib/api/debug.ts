/**
 * Debug 模式 API
 * 仅在 DEBUG_MODE=true 且用户为 SUPER_ADMIN 名单内时有效
 */

import { apiClient, ApiResponse } from './client';

export interface DebugStatus {
  debug_mode: boolean;
  is_debug_admin: boolean;
}

export const debugApi = {
  getStatus: async (): Promise<ApiResponse<DebugStatus>> => {
    return apiClient.get('/debug/status');
  },
};
