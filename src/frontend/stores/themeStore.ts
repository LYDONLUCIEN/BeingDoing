import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeId =
  | 'slate-dark'
  | 'warm-light'
  | 'forest'
  | 'sand'
  | 'serene'
  | 'insight'
  | 'aurora'
  | 'ideal'
  | 'glimmer';

export interface ThemeMeta {
  id: ThemeId;
  name: string;
  description: string;
  scheme: 'dark' | 'light';
  /** Preview swatch colors [bg, primary, accent] */
  swatches: [string, string, string];
}

export const THEMES: ThemeMeta[] = [
  /* ── Dark themes ── */
  {
    id: 'slate-dark',
    name: '深空',
    description: '深蓝黑底，冷静专注',
    scheme: 'dark',
    swatches: ['#020817', '#0ea5e9', '#818cf8'],
  },
  {
    id: 'forest',
    name: '森林',
    description: '深绿沉浸，自然宁静',
    scheme: 'dark',
    swatches: ['#071007', '#4ade80', '#67e8f9'],
  },

  /* ── Light — Warm/Earth ── */
  {
    id: 'warm-light',
    name: '暖光',
    description: '奶油白底，温暖明亮',
    scheme: 'light',
    swatches: ['#faf8f5', '#d97706', '#7c3aed'],
  },
  {
    id: 'sand',
    name: '暖沙',
    description: '米白沙调，柔和雅致',
    scheme: 'light',
    swatches: ['#f5f0e8', '#b45309', '#0369a1'],
  },

  /* ── Light — Refined ── */
  {
    id: 'serene',
    name: '宁静',
    description: '莫兰迪色系，留白疗愈',
    scheme: 'light',
    swatches: ['#f4f0eb', '#7a9e82', '#7b97b8'],
  },
  {
    id: 'insight',
    name: '睿智',
    description: '燕麦底 · 藏青权威 · 暖金启发',
    scheme: 'light',
    swatches: ['#f2eeea', '#1e3a6e', '#d4860e'],
  },

  /* ── Light — Apple / Aurora ── */
  {
    id: 'aurora',
    name: '极光',
    description: '纯白流光，全息玻璃质感',
    scheme: 'light',
    swatches: ['#f5f5f7', '#5a6ad4', '#a78bfa'],
  },

  /* ── Light — Design Principle (docs/design_principle.md) ── */
  {
    id: 'ideal',
    name: '理想',
    description: '小圆角 · 毛玻璃 · 价值观蓝/能力绿/热爱红/目的黄',
    scheme: 'light',
    swatches: ['#F2F5F8', '#6FAEE0', '#83C290'],
  },
  {
    id: 'glimmer',
    name: '微光',
    description: '小圆角 · 毛玻璃 · 柔和微光色系',
    scheme: 'light',
    swatches: ['#F6F7F9', '#7CAAC4', '#E09098'],
  },
];

export type ColorScheme = 'light' | 'dark';

interface ThemeStore {
  themeId: ThemeId;
  colorScheme: ColorScheme;
  /** 夜间模式使用的主题（admin 可配置） */
  darkThemeId: ThemeId;
  /** 日间模式使用的主题 */
  lightThemeId: ThemeId;
  setTheme: (id: ThemeId) => void;
  setColorScheme: (scheme: ColorScheme) => void;
  toggleColorScheme: () => void;
  setDarkThemeId: (id: ThemeId) => void;
  setLightThemeId: (id: ThemeId) => void;
}

const DARK_THEMES: ThemeId[] = ['slate-dark', 'forest'];
const LIGHT_THEMES: ThemeId[] = ['ideal', 'glimmer', 'aurora', 'warm-light', 'sand', 'serene', 'insight'];

function applyTheme(id: ThemeId) {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', id);
    document.documentElement.setAttribute('data-color-scheme', DARK_THEMES.includes(id) ? 'dark' : 'light');
  }
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set, get) => ({
      themeId: 'ideal',
      colorScheme: 'light',
      darkThemeId: 'slate-dark',
      lightThemeId: 'ideal',
      setTheme: (id) => {
        set({ themeId: id, colorScheme: DARK_THEMES.includes(id) ? 'dark' : 'light' });
        applyTheme(id);
      },
      setColorScheme: (scheme) => {
        const { darkThemeId, lightThemeId } = get();
        const id = scheme === 'dark' ? darkThemeId : lightThemeId;
        set({ colorScheme: scheme, themeId: id });
        applyTheme(id);
      },
      toggleColorScheme: () => {
        const { colorScheme, darkThemeId, lightThemeId } = get();
        const next = colorScheme === 'light' ? 'dark' : 'light';
        const id = next === 'dark' ? darkThemeId : lightThemeId;
        set({ colorScheme: next, themeId: id });
        applyTheme(id);
      },
      setDarkThemeId: (id) => {
        set({ darkThemeId: id });
        const { colorScheme } = get();
        if (colorScheme === 'dark') applyTheme(id);
      },
      setLightThemeId: (id) => {
        set({ lightThemeId: id });
        const { colorScheme } = get();
        if (colorScheme === 'light') applyTheme(id);
      },
    }),
    { name: 'bd-theme' }
  )
);

export { DARK_THEMES, LIGHT_THEMES };
