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

interface ThemeStore {
  themeId: ThemeId;
  setTheme: (id: ThemeId) => void;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      themeId: 'slate-dark',
      setTheme: (id) => {
        set({ themeId: id });
        if (typeof document !== 'undefined') {
          document.documentElement.setAttribute('data-theme', id);
        }
      },
    }),
    { name: 'bd-theme' }
  )
);
