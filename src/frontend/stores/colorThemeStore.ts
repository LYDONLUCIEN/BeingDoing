/**
 * 配色主题 Store
 * 黑白各一套，背景 / 四维主题色 / 导引色 均单独可配
 * 存 localStorage，PhaseColorInjector 按 data-color-scheme 注入
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ColorScheme = 'light' | 'dark';

export interface SchemeColors {
  bg: string;
  bgMid: string;
  bgEnd: string;
  phaseValues: string;
  phaseStrengths: string;
  phaseInterests: string;
  phasePurpose: string;
  uiAccent: string;
}

const DEFAULT_LIGHT: SchemeColors = {
  bg: '#F2F5F8',
  bgMid: '#EEF1F4',
  bgEnd: '#F2F5F8',
  phaseValues: '#6FAEE0',
  phaseStrengths: '#83C290',
  phaseInterests: '#EF837E',
  phasePurpose: '#F4C062',
  uiAccent: '#7c3aed',
};

const DEFAULT_DARK: SchemeColors = {
  bg: '#020817',
  bgMid: '#0f172a',
  bgEnd: '#020817',
  phaseValues: '#818cf8',
  phaseStrengths: '#34d399',
  phaseInterests: '#fb7185',
  phasePurpose: '#fbbf24',
  uiAccent: '#a78bfa',
};

function hexToRgba(hex: string, alpha: number): string {
  const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  if (!m) return hex;
  const r = parseInt(m[1], 16);
  const g = parseInt(m[2], 16);
  const b = parseInt(m[3], 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

type SchemeKey = keyof SchemeColors;

interface ColorThemeStore {
  light: Partial<SchemeColors>;
  dark: Partial<SchemeColors>;
  setLight: (key: SchemeKey, value: string) => void;
  setDark: (key: SchemeKey, value: string) => void;
  removeLight: (key: SchemeKey) => void;
  removeDark: (key: SchemeKey) => void;
  resetLight: () => void;
  resetDark: () => void;
  resetAll: () => void;
  getEffectiveLight: () => SchemeColors;
  getEffectiveDark: () => SchemeColors;
}

export const useColorThemeStore = create<ColorThemeStore>()(
  persist(
    (set, get) => ({
      light: {},
      dark: {},
      setLight: (key, value) => set((s) => ({ light: { ...s.light, [key]: value } })),
      setDark: (key, value) => set((s) => ({ dark: { ...s.dark, [key]: value } })),
      removeLight: (key) => set((s) => { const { [key]: _, ...rest } = s.light; return { light: rest }; }),
      removeDark: (key) => set((s) => { const { [key]: _, ...rest } = s.dark; return { dark: rest }; }),
      resetLight: () => set({ light: {} }),
      resetDark: () => set({ dark: {} }),
      resetAll: () => set({ light: {}, dark: {} }),
      getEffectiveLight: () => ({ ...DEFAULT_LIGHT, ...get().light }),
      getEffectiveDark: () => ({ ...DEFAULT_DARK, ...get().dark }),
    }),
    { name: 'bd-color-theme', partialize: (s) => ({ light: s.light, dark: s.dark }) }
  )
);

export function getColorThemeCSS(light: SchemeColors, dark: SchemeColors): string {
  const toPhaseDim = (hex: string) => hexToRgba(hex, 0.12);
  const toAccentDim = (hex: string) => hexToRgba(hex, 0.12);

  const lightVars = `
  --bd-bg: ${light.bg};
  --bd-bg-mid: ${light.bgMid};
  --bd-bg-end: ${light.bgEnd};
  --bd-phase-values: ${light.phaseValues};
  --bd-phase-values-dim: ${toPhaseDim(light.phaseValues)};
  --bd-phase-strengths: ${light.phaseStrengths};
  --bd-phase-strengths-dim: ${toPhaseDim(light.phaseStrengths)};
  --bd-phase-interests: ${light.phaseInterests};
  --bd-phase-interests-dim: ${toPhaseDim(light.phaseInterests)};
  --bd-phase-purpose: ${light.phasePurpose};
  --bd-phase-purpose-dim: ${toPhaseDim(light.phasePurpose)};
  --bd-ui-accent: ${light.uiAccent};
  --bd-ui-accent-dim: ${toAccentDim(light.uiAccent)};
`;
  const darkVars = `
  --bd-bg: ${dark.bg};
  --bd-bg-mid: ${dark.bgMid};
  --bd-bg-end: ${dark.bgEnd};
  --bd-phase-values: ${dark.phaseValues};
  --bd-phase-values-dim: ${toPhaseDim(dark.phaseValues)};
  --bd-phase-strengths: ${dark.phaseStrengths};
  --bd-phase-strengths-dim: ${toPhaseDim(dark.phaseStrengths)};
  --bd-phase-interests: ${dark.phaseInterests};
  --bd-phase-interests-dim: ${toPhaseDim(dark.phaseInterests)};
  --bd-phase-purpose: ${dark.phasePurpose};
  --bd-phase-purpose-dim: ${toPhaseDim(dark.phasePurpose)};
  --bd-ui-accent: ${dark.uiAccent};
  --bd-ui-accent-dim: ${toAccentDim(dark.uiAccent)};
`;

  return `
[data-color-scheme="light"] {
${lightVars}
}
[data-color-scheme="dark"] {
${darkVars}
}
`.trim();
}

export { DEFAULT_LIGHT, DEFAULT_DARK };
