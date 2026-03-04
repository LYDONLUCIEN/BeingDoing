'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';
import {
  useDesignEffectsStore,
  EFFECT_PRESETS,
  EFFECT_PRESET_IDS,
  type EffectPresetId,
} from '@/stores/designEffectsStore';
import { ArrowLeft, Check } from 'lucide-react';

export default function StyleLabPage() {
  const { isAuthenticated, _hasHydrated } = useAuthStore();
  const openAuthModal = useAuthModalStore((s) => s.openAuthModal);
  const presetId = useDesignEffectsStore((s) => s.presetId);
  const setPreset = useDesignEffectsStore((s) => s.setPreset);

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted || !_hasHydrated) return;
    if (!isAuthenticated) {
      openAuthModal('/settings/style-lab');
      return;
    }
  }, [mounted, _hasHydrated, isAuthenticated, openAuthModal]);

  if (!mounted) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: 'var(--bd-bg)' }}
      >
        <div
          className="w-10 h-10 rounded-full border-2 animate-spin"
          style={{ borderColor: 'var(--bd-primary)', borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bd-bg)' }}>
      <header
        className="bd-eff-card sticky top-0 z-40 border-b backdrop-blur-md"
        style={{
          background: 'var(--bd-nav-bg)',
          borderColor: 'var(--bd-nav-border)',
        }}
      >
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link
            href="/"
            className="flex items-center gap-2 text-sm font-medium transition-colors"
            style={{ color: 'var(--bd-fg-muted)' }}
          >
            <ArrowLeft size={18} /> 返回
          </Link>
          <h1 className="text-lg font-semibold" style={{ color: 'var(--bd-fg)' }}>
            效果实验室
          </h1>
          <div className="w-16" />
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-8">
        <p className="text-sm leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
          切换效果预设可即时预览，选中的效果会保存到本地并全站生效。与主题、阶段配色相互独立，可自由组合。
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          {EFFECT_PRESET_IDS.map((id) => {
            const preset = EFFECT_PRESETS[id];
            if (!preset) return null;
            const isActive = (presetId || 'none') === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setPreset(id as EffectPresetId)}
                className="bd-eff-card relative rounded-xl p-4 text-left border-2 transition-all"
                style={{
                  background: 'var(--bd-bg-card)',
                  borderColor: isActive ? 'var(--bd-primary)' : 'var(--bd-border)',
                  boxShadow: isActive ? '0 0 0 2px var(--bd-primary-dim)' : undefined,
                }}
              >
                <div className="font-medium mb-1" style={{ color: 'var(--bd-fg)' }}>
                  {preset.name}
                </div>
                <div className="text-xs" style={{ color: 'var(--bd-fg-subtle)' }}>
                  {Object.keys(preset.vars).length} 个变量覆盖
                </div>
                {isActive && (
                  <div
                    className="absolute top-3 right-3 w-6 h-6 rounded-full flex items-center justify-center"
                    style={{ background: 'var(--bd-primary)', color: 'var(--bd-primary-fg)' }}
                  >
                    <Check size={14} />
                  </div>
                )}
              </button>
            );
          })}
        </div>

        <div
          className="rounded-xl p-4 border"
          style={{
            background: 'var(--bd-bg-card-alt)',
            borderColor: 'var(--bd-border-soft)',
          }}
        >
          <p className="text-xs font-medium mb-2" style={{ color: 'var(--bd-fg-subtle)' }}>
            新增 / 修改预设
          </p>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
            编辑{' '}
            <code
              className="px-1.5 py-0.5 rounded text-xs"
              style={{ background: 'var(--bd-overlay)', border: '1px solid var(--bd-border)' }}
            >
              src/frontend/config/design-effects.json
            </code>{' '}
            添加或调整预设，保存后刷新本页即可在列表中看到新选项。
          </p>
        </div>

        <Link
          href="/"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          style={{
            background: 'var(--bd-primary)',
            color: 'var(--bd-primary-fg)',
          }}
        >
          在首页查看效果 →
        </Link>
      </main>
    </div>
  );
}
