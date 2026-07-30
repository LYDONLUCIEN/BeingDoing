import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { clearLastActivationCode } from '@/lib/explore/session';

interface User {
  user_id: string;
  email?: string;
  phone?: string;
  username?: string;
  avatar_url?: string;
  is_super_admin?: boolean;
  email_verified?: boolean;
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
          // 换号残留清理：上次激活码不能带到下一个账号
          clearLastActivationCode();
          // 多账号切换：清除所有用户的问卷完成状态 + 隐私声明知晓状态
          const keysToRemove: string[] = [];
          for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key?.startsWith('explore_user_survey_') || key?.startsWith('explore_user_privacy_ack_')) {
              keysToRemove.push(key);
            }
            // 清除所有会话缓存（线程、session、rumination 步骤边界等）
            // 下次登录时将从后端完整恢复
            if (
              key?.startsWith('explore_threads_') ||
              key?.startsWith('explore_active_thread_') ||
              key?.startsWith('explore_threads_sync_ts_') ||
              key?.startsWith('explore_session_') ||
              key?.startsWith('bd_rumination_step_idx_')
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
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

// 标记 rehydration 完成并同步 token 到 localStorage。
// 注意：不能放在 onRehydrateStorage 回调里直接引用 useAuthStore——
// localStorage 是同步 storage，zustand 会在 create() 期间同步执行回调，
// 此时 useAuthStore 尚未完成初始化（TDZ 报错），导致 _hasHydrated 永远为 false。
const markHydrated = () => {
  useAuthStore.getState().setHasHydrated(true);
  const token = useAuthStore.getState().token;
  if (typeof window !== 'undefined' && token) {
    localStorage.setItem('token', token);
  }
};
if (typeof window !== 'undefined') {
  // 仅客户端执行（SSR 端 storage 为 undefined，persist API 不会挂载）
  if (useAuthStore.persist.hasHydrated()) {
    markHydrated();
  } else {
    useAuthStore.persist.onFinishHydration(markHydrated);
  }
}
