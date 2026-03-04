import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeId = 'ideal' | 'slate-dark';

export type ColorScheme = 'light' | 'dark';

const DARK_THEME: ThemeId = 'slate-dark';
const LIGHT_THEME: ThemeId = 'ideal';

function applyTheme(colorScheme: ColorScheme) {
  if (typeof document === 'undefined') return;
  const themeId = colorScheme === 'light' ? LIGHT_THEME : DARK_THEME;
  document.documentElement.setAttribute('data-theme', themeId);
  document.documentElement.setAttribute('data-color-scheme', colorScheme);
}

interface ThemeStore {
  colorScheme: ColorScheme;
  themeId: ThemeId;
  toggleColorScheme: () => void;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      colorScheme: 'light',
      themeId: LIGHT_THEME,
      toggleColorScheme: () => {
        set((s) => {
          const next = s.colorScheme === 'light' ? 'dark' : 'light';
          const themeId = next === 'light' ? LIGHT_THEME : DARK_THEME;
          applyTheme(next);
          return { colorScheme: next, themeId };
        });
      },
    }),
    {
      name: 'bd-theme',
      migrate: (persisted: unknown) => {
        const p = persisted as { state?: { themeId?: string; colorScheme?: string } };
        const st = p?.state;
        if (!st) return { colorScheme: 'light' as ColorScheme, themeId: LIGHT_THEME };
        const darkIds = ['slate-dark', 'forest'];
        const id = st.themeId;
        const scheme = st.colorScheme ?? (id && darkIds.includes(id) ? 'dark' : 'light');
        const themeId = scheme === 'dark' ? DARK_THEME : LIGHT_THEME;
        return { colorScheme: scheme as ColorScheme, themeId };
      },
      version: 2,
      onRehydrateStorage: () => (state) => {
        if (state) applyTheme(state.colorScheme);
      },
    }
  )
);

export const DARK_THEMES: ThemeId[] = [DARK_THEME];
export const LIGHT_THEMES: ThemeId[] = [LIGHT_THEME];
