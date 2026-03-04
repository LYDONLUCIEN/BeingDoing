'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';
import { usePhaseColorStore, PHASE_KEYS, DEFAULT_NAMES, type PhaseKey } from '@/stores/phaseColorStore';
import { ArrowLeft, RotateCcw } from 'lucide-react';

/** 用于「恢复默认」的参考色（ideal 主题） */
const FALLBACK_HEX: Record<PhaseKey, string> = {
  values: '#6FAEE0',
  strengths: '#83C290',
  interests: '#EF837E',
  purpose: '#F4C062',
};

export default function PhaseColorsSettingsPage() {
  const router = useRouter();
  const { isAuthenticated, _hasHydrated } = useAuthStore();
  const openAuthModal = useAuthModalStore((s) => s.openAuthModal);
  const overrides = usePhaseColorStore((s) => s.overrides);
  const setPhaseColor = usePhaseColorStore((s) => s.setPhaseColor);
  const resetOverrides = usePhaseColorStore((s) => s.resetOverrides);

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted || !_hasHydrated) return;
    if (!isAuthenticated) {
      openAuthModal('/settings/colors');
      return;
    }
  }, [mounted, _hasHydrated, isAuthenticated, openAuthModal]);

  const hasOverrides = Object.keys(overrides).length > 0;

  if (!mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bd-bg)' }}>
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
            阶段配色
          </h1>
          <div className="w-16" />
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-8">
        <p className="text-sm leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
          信念、禀赋、热忱、使命四个维度的颜色会在首页和探索流程中统一使用。修改后将覆盖当前主题的默认配色，并保存到本地。
        </p>

        <div className="space-y-6">
          {PHASE_KEYS.map((key) => {
            const value = overrides[key] ?? FALLBACK_HEX[key];
            return (
              <div
                key={key}
                className="bd-eff-card rounded-xl p-4 flex items-center gap-4"
                style={{
                  background: 'var(--bd-bg-card)',
                  border: '1px solid var(--bd-border)',
                }}
              >
                <div className="flex-shrink-0">
                  <label
                    htmlFor={`phase-${key}`}
                    className="block text-sm font-medium mb-1"
                    style={{ color: 'var(--bd-fg)' }}
                  >
                    {DEFAULT_NAMES[key]}
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      id={`phase-${key}`}
                      type="color"
                      value={value}
                      onChange={(e) => setPhaseColor(key, e.target.value)}
                      className="w-12 h-12 rounded-lg cursor-pointer border-0 bg-transparent"
                    />
                    <input
                      type="text"
                      value={value}
                      onChange={(e) => {
                        const v = e.target.value.trim();
                        if (/^#[0-9A-Fa-f]{6}$/.test(v)) setPhaseColor(key, v);
                      }}
                      className="w-24 px-2 py-1.5 text-sm rounded-lg font-mono"
                      style={{
                        background: 'var(--bd-overlay)',
                        border: '1px solid var(--bd-border)',
                        color: 'var(--bd-fg)',
                      }}
                    />
                  </div>
                </div>
                {overrides[key] && (
                  <button
                    type="button"
                    onClick={() => setPhaseColor(key, null)}
                    className="text-xs px-2 py-1 rounded"
                    style={{
                      background: 'var(--bd-overlay)',
                      color: 'var(--bd-fg-muted)',
                    }}
                  >
                    使用主题默认
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {hasOverrides && (
          <button
            type="button"
            onClick={resetOverrides}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              background: 'var(--bd-error-dim)',
              color: 'var(--bd-error)',
            }}
          >
            <RotateCcw size={16} /> 恢复全部默认
          </button>
        )}

        <p className="text-xs" style={{ color: 'var(--bd-fg-subtle)' }}>
          配色保存在浏览器本地，仅影响当前设备。切换主题会使用该主题自带的阶段色，你的覆盖设置优先于主题默认。
        </p>
      </main>
    </div>
  );
}
