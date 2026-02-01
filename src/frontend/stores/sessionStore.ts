import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface Session {
  session_id: string;
  user_id?: string;
  current_step: string;
  status: string;
}

interface SessionState {
  currentSession: Session | null;
  setCurrentSession: (session: Session | null) => void;
  clearSession: () => void;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      currentSession: null,
      setCurrentSession: (session) => set({ currentSession: session }),
      clearSession: () => set({ currentSession: null }),
    }),
    {
      name: 'session-storage',
      storage: typeof window !== 'undefined' ? createJSONStorage(() => localStorage) : undefined,
    }
  )
);
