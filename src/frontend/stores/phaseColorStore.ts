/**
 * 阶段配色覆盖 Store
 *
 * 允许用户自定义信念/禀赋/热忱/使命四个维度的颜色，
 * 覆盖当前主题的默认阶段色。存 localStorage，全站生效。
 *
 * 设计原则：价值观=蓝 | 禀赋=绿 | 热忱=红 | 使命=黄
 * 默认由各 theme 文件定义，此处仅作用户覆盖。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type PhaseKey = 'values' | 'strengths' | 'interests' | 'purpose';

export interface PhaseColorOverrides {
  values?: string;    // hex e.g. #6FAEE0
  strengths?: string;
  interests?: string;
  purpose?: string;
}

const PHASE_KEYS: PhaseKey[] = ['values', 'strengths', 'interests', 'purpose'];

const DEFAULT_NAMES: Record<PhaseKey, string> = {
  values: '信念',
  strengths: '禀赋',
  interests: '热忱',
  purpose: '使命',
};

function hexToRgba(hex: string, alpha: number): string {
  const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  if (!m) return hex;
  const r = parseInt(m[1], 16);
  const g = parseInt(m[2], 16);
  const b = parseInt(m[3], 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

interface PhaseColorStore {
  overrides: PhaseColorOverrides;
  setPhaseColor: (phase: PhaseKey, hex: string | null) => void;
  resetOverrides: () => void;
}

export const usePhaseColorStore = create<PhaseColorStore>()(
  persist(
    (set) => ({
      overrides: {},
      setPhaseColor: (phase, hex) => {
        set((s) => {
          const next = { ...s.overrides };
          if (hex) next[phase] = hex;
          else delete next[phase];
          return { overrides: next };
        });
      },
      resetOverrides: () => set({ overrides: {} }),
    }),
    {
      name: 'bd-phase-colors',
      partialize: (s) => ({ overrides: s.overrides }),
    }
  )
);

// 供 PhaseColorInjector 使用
export function getPhaseColorCSS(overrides: PhaseColorOverrides): string {
  if (Object.keys(overrides).length === 0) return '';
  const lines: string[] = [':root, [data-theme] {'];
  for (const key of PHASE_KEYS) {
    const hex = overrides[key];
    if (!hex) continue;
    const dim = hexToRgba(hex, 0.12);
    lines.push(`  --bd-phase-${key}: ${hex};`);
    lines.push(`  --bd-phase-${key}-dim: ${dim};`);
  }
  lines.push('}');
  return lines.join('\n');
}

export { PHASE_KEYS, DEFAULT_NAMES };
