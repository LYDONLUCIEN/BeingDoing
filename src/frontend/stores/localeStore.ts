import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { LocaleId } from '@/lib/i18n';

interface LocaleStore {
  locale: LocaleId;
  setLocale: (locale: LocaleId) => void;
}

export const useLocaleStore = create<LocaleStore>()(
  persist(
    (set) => ({
      locale: 'zh',
      setLocale: (locale) => set({ locale }),
    }),
    { name: 'bd-locale' }
  )
);
