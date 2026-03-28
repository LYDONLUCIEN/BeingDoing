'use client';

import { useEffect, useState } from 'react';
import { useThemeStore } from '@/stores/themeStore';
import { EFFECT_PRESET_IDS, useDesignEffectsStore } from '@/stores/designEffectsStore';
import { DEFAULT_DARK, DEFAULT_LIGHT, useColorThemeStore, type SchemeColors } from '@/stores/colorThemeStore';
import { fetchAdminSystemSettings, patchAdminSystemSettings } from '@/lib/api/admin';

interface BasicSettings {
  APP_ENV?: string;
  ARCHITECTURE_MODE?: string;
  LLM_PROVIDER?: string;
  LLM_MODEL?: string;
  BASIC_INFO_MERGE_STRATEGY?: 'A' | 'B' | 'C';
  ADMIN_DEBUG_POLICY_ENABLED?: boolean;
  ADMIN_DEBUG_WORKSPACE_ENABLED?: boolean;
  ADMIN_SANDBOX_ENABLED?: boolean;
}

export default function AdminSystemPage() {
  const [settings, setSettings] = useState<BasicSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mergeSaving, setMergeSaving] = useState(false);
  const { colorScheme, toggleColorScheme } = useThemeStore();
  const presetId = useDesignEffectsStore((s) => s.presetId);
  const setPreset = useDesignEffectsStore((s) => s.setPreset);
  const light = useColorThemeStore((s) => s.light);
  const dark = useColorThemeStore((s) => s.dark);
  const setLight = useColorThemeStore((s) => s.setLight);
  const setDark = useColorThemeStore((s) => s.setDark);
  const resetAll = useColorThemeStore((s) => s.resetAll);

  const loadSettings = () => {
    fetchAdminSystemSettings()
      .then((res) => setSettings(res))
      .catch((e: any) => setError(e?.message || '加载系统设置失败'));
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleMergeStrategyChange = async (val: 'A' | 'B' | 'C') => {
    setMergeSaving(true);
    setError(null);
    try {
      await patchAdminSystemSettings({ basic_info_merge_strategy: val });
      setSettings((prev) => (prev ? { ...prev, BASIC_INFO_MERGE_STRATEGY: val } : prev));
    } catch (e: any) {
      setError(e?.message || '保存失败');
    } finally {
      setMergeSaving(false);
    }
  };

  const colorKeys: Array<keyof SchemeColors> = [
    'bg',
    'bgMid',
    'bgEnd',
    'phaseValues',
    'phaseStrengths',
    'phaseInterests',
    'phasePurpose',
    'uiAccent',
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          系统设置（只读）
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          只读展示系统配置，同时迁移主题/配色/效果控制入口（仅影响前端视觉，不涉及高风险后端写操作）。
        </p>
      </header>

      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">
          {error}
        </section>
      )}

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm space-y-3 text-xs">
        <h2 className="text-sm font-medium text-bd-fg">系统配置</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>APP_ENV：<span className="text-bd-fg">{settings?.APP_ENV ?? '—'}</span></div>
          <div>ARCHITECTURE_MODE：<span className="text-bd-fg">{settings?.ARCHITECTURE_MODE ?? '—'}</span></div>
          <div>LLM_PROVIDER：<span className="text-bd-fg">{settings?.LLM_PROVIDER ?? '—'}</span></div>
          <div>LLM_MODEL：<span className="text-bd-fg">{settings?.LLM_MODEL ?? '—'}</span></div>
          <div>
            ADMIN_DEBUG_POLICY_ENABLED：
            <span className="text-bd-fg">{String(settings?.ADMIN_DEBUG_POLICY_ENABLED ?? false)}</span>
          </div>
          <div>
            ADMIN_DEBUG_WORKSPACE_ENABLED：
            <span className="text-bd-fg">{String(settings?.ADMIN_DEBUG_WORKSPACE_ENABLED ?? true)}</span>
          </div>
          <div>
            ADMIN_SANDBOX_ENABLED：
            <span className="text-bd-fg">{String(settings?.ADMIN_SANDBOX_ENABLED ?? true)}</span>
          </div>
        </div>
        <div className="pt-3 border-t border-bd-border">
          <label className="block font-medium text-bd-fg mb-2">问卷合并策略 (basic_info_merge_strategy)</label>
          <p className="text-bd-muted mb-2">
            A=最新覆盖；B=并集；C=交集。多来源时如何合并用户 basic_info。
          </p>
          <select
            value={(settings?.BASIC_INFO_MERGE_STRATEGY ?? 'A') as string}
            onChange={(e) => handleMergeStrategyChange((e.target.value || 'A') as 'A' | 'B' | 'C')}
            disabled={mergeSaving}
            className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-1.5 text-sm"
          >
            <option value="A">A - 最新覆盖</option>
            <option value="B">B - 并集</option>
            <option value="C">C - 交集</option>
          </select>
        </div>
      </section>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm space-y-4">
        <h2 className="text-sm font-medium text-bd-fg">主题与效果</h2>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={toggleColorScheme}
            className="px-3 py-1.5 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg"
          >
            切换明暗（当前：{colorScheme}）
          </button>
          <select
            value={presetId || 'none'}
            onChange={(e) => setPreset((e.target.value || 'none') as any)}
            className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-1.5"
          >
            {EFFECT_PRESET_IDS.map((id) => (
              <option key={id} value={id}>{id}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={resetAll}
            className="px-3 py-1.5 rounded-lg border border-bd-border text-bd-fg"
          >
            重置配色
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="space-y-2">
            <h3 className="font-medium text-bd-fg">Light 配色</h3>
            {colorKeys.map((k) => (
              <label key={`l-${k}`} className="flex items-center justify-between gap-3">
                <span className="text-bd-muted">{k}</span>
                <input
                  type="color"
                  value={(light[k] || DEFAULT_LIGHT[k]) as string}
                  onChange={(e) => setLight(k, e.target.value)}
                  className="w-10 h-7 p-0 border-0 bg-transparent"
                />
              </label>
            ))}
          </div>
          <div className="space-y-2">
            <h3 className="font-medium text-bd-fg">Dark 配色</h3>
            {colorKeys.map((k) => (
              <label key={`d-${k}`} className="flex items-center justify-between gap-3">
                <span className="text-bd-muted">{k}</span>
                <input
                  type="color"
                  value={(dark[k] || DEFAULT_DARK[k]) as string}
                  onChange={(e) => setDark(k, e.target.value)}
                  className="w-10 h-7 p-0 border-0 bg-transparent"
                />
              </label>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

