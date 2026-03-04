/**
 * Debug 模式状态
 * 仅当 DEBUG_MODE=true 且当前用户为 DEBUG_ADMIN 时 isDebugAdmin 为 true
 */

import { create } from 'zustand';
import { debugApi } from '@/lib/api/debug';

interface DebugState {
  debugMode: boolean;
  isDebugAdmin: boolean;
  loaded: boolean;
  loadStatus: () => Promise<void>;
}

export const useDebugStore = create<DebugState>((set) => ({
  debugMode: false,
  isDebugAdmin: false,
  loaded: false,

  loadStatus: async () => {
    try {
      const res = await debugApi.getStatus();
      const data = res.data as { debug_mode: boolean; is_debug_admin: boolean };
      set({
        debugMode: data.debug_mode ?? false,
        isDebugAdmin: data.is_debug_admin ?? false,
        loaded: true,
      });
    } catch {
      set({ debugMode: false, isDebugAdmin: false, loaded: true });
    }
  },
}));
