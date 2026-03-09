import { create } from 'zustand';

interface AuthModalState {
  isOpen: boolean;
  redirectTo: string;
  openAuthModal: (redirectTo?: string) => void;
  closeAuthModal: () => void;
}

export const useAuthModalStore = create<AuthModalState>((set) => ({
  isOpen: false,
  redirectTo: '/explore/intro',
  openAuthModal: (redirectTo = '/explore/intro') => set({ isOpen: true, redirectTo }),
  closeAuthModal: () => set({ isOpen: false }),
}));
