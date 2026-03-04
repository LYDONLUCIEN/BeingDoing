/**
 * 设计效果 Store
 *
 * 管理效果预设的选择（毛玻璃、素描纸、扁平等），
 * 与阶段配色、主题相互独立。预设来自 design-effects.json。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import designEffectsConfig from '@/config/design-effects.json';

export interface EffectPreset {
  name: string;
  vars: Record<string, string>;
}

export interface DesignEffectsConfig {
  presets: Record<string, EffectPreset>;
}

const config: DesignEffectsConfig = {
  presets: (designEffectsConfig as DesignEffectsConfig)?.presets ?? {},
};

export const EFFECT_PRESETS = config.presets;
export const EFFECT_PRESET_IDS = Object.keys(config.presets);

export type EffectPresetId = keyof typeof config.presets;

interface DesignEffectsStore {
  presetId: EffectPresetId | '';
  setPreset: (id: EffectPresetId | '') => void;
  getCurrentPreset: () => EffectPreset | null;
}

export const useDesignEffectsStore = create<DesignEffectsStore>()(
  persist(
    (set, get) => ({
      presetId: 'none',
      setPreset: (id) => set({ presetId: id || 'none' }),
      getCurrentPreset: () => {
        const id = get().presetId || 'none';
        return config.presets?.[id] ?? null;
      },
    }),
    {
      name: 'bd-design-effects',
      partialize: (s) => ({ presetId: s.presetId }),
      onRehydrateStorage: () => (state) => {
        if (state?.presetId && !(state.presetId in config.presets)) {
          useDesignEffectsStore.setState({ presetId: 'none' });
        }
      },
    }
  )
);

export function getEffectPresetCSS(presetId: EffectPresetId | ''): string {
  const id = presetId || 'none';
  const preset = config.presets?.[id];
  if (!preset || Object.keys(preset.vars).length === 0) return '';
  const lines: string[] = [':root, [data-theme] {'];
  for (const [key, value] of Object.entries(preset.vars)) {
    lines.push(`  ${key}: ${value};`);
  }
  lines.push('}');
  return lines.join('\n');
}
