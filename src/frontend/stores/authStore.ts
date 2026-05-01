import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface User {
  user_id: string;
  email?: string;
  phone?: string;
  username?: string;
  avatar_url?: string;
  is_super_admin?: boolean;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  /** 仅客户端：localStorage 恢复完成后为 true，避免未恢复就重定向导致闪屏/空白 */
  _hasHydrated: boolean;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  setTokens: (token: string | null) => void;
  setHasHydrated: (v: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      _hasHydrated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setToken: (token) => {
        if (typeof window !== 'undefined') {
          if (token) localStorage.setItem('token', token);
          else localStorage.removeItem('token');
        }
        set({ token });
      },
      setTokens: (token) => {
        if (typeof window !== 'undefined') {
          if (token) localStorage.setItem('token', token);
          else localStorage.removeItem('token');
        }
        set({ token });
      },
      setHasHydrated: (v) => set({ _hasHydrated: v }),
      logout: () => {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('token');
          // 多账号切换：清除所有用户的问卷完成状态
          const keysToRemove: string[] = [];
          for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key?.startsWith('explore_user_survey_')) {
              keysToRemove.push(key);
            }
            // 清除所有会话缓存（线程、session、rumination 步骤边界等）
            // 下次登录时将从后端完整恢复
            if (
              key?.startsWith('explore_threads_') ||
              key?.startsWith('explore_active_thread_') ||
              key?.startsWith('explore_threads_sync_ts_') ||
              key?.startsWith('explore_session_') ||
              key?.startsWith('bd_rumination_step_idx_') ||
              key === 'explore_last_code'
            ) {
              keysToRemove.push(key);
            }
          }
          keysToRemove.forEach((k) => localStorage.removeItem(k));
        }
        set({ user: null, token: null, isAuthenticated: false });
      },
    }),
    {
      name: 'auth-storage',
      storage: typeof window !== 'undefined' ? createJSONStorage(() => localStorage) : undefined,
      onRehydrateStorage: () => (state) => {
        useAuthStore.getState().setHasHydrated(true);
        if (typeof window !== 'undefined') {
          if (state?.token) localStorage.setItem('token', state.token);
        }
      },
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
