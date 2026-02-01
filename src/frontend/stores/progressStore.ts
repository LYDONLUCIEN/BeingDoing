import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface Progress {
  step: string;
  completed_count: number;
  total_count: number;
  percentage: number;
}

interface ProgressState {
  progresses: Record<string, Progress>;
  setProgress: (step: string, progress: Progress) => void;
  clearProgress: () => void;
}

export const useProgressStore = create<ProgressState>()(
  persist(
    (set) => ({
      progresses: {},
      setProgress: (step, progress) =>
        set((state) => ({
          progresses: { ...state.progresses, [step]: progress },
        })),
      clearProgress: () => set({ progresses: {} }),
    }),
    {
      name: 'progress-storage',
      storage: typeof window !== 'undefined' ? createJSONStorage(() => localStorage) : undefined,
    }
  )
);
