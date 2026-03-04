'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  useColorThemeStore,
  DEFAULT_LIGHT,
  DEFAULT_DARK,
  type SchemeColors,
  type ColorScheme,
} from '@/stores/colorThemeStore';
import { ArrowLeft, RotateCcw, Sun, Moon } from 'lucide-react';

const LABELS: Record<keyof SchemeColors, { zh: string; en: string }> = {
  bg: { zh: '背景主色', en: 'Bg' },
  bgMid: { zh: '背景中间', en: 'Bg mid' },
  bgEnd: { zh: '背景底', en: 'Bg end' },
  phaseValues: { zh: '信念', en: 'Values' },
  phaseStrengths: { zh: '禀赋', en: 'Strengths' },
  phaseInterests: { zh: '热忱', en: 'Interests' },
  phasePurpose: { zh: '使命', en: 'Purpose' },
  uiAccent: { zh: '导引色', en: 'Accent' },
};

const KEYS = ['bg', 'bgMid', 'bgEnd', 'phaseValues', 'phaseStrengths', 'phaseInterests', 'phasePurpose', 'uiAccent'] as const;

function ColorRow({
  label,
  value,
  onChange,
  onReset,
  hasOverride,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  onReset: () => void;
  hasOverride: boolean;
}) {
  return (
    <div className="flex items-center gap-3 py-2">
      <label className="w-20 text-sm shrink-0" style={{ color: 'var(--bd-fg-muted)' }}>
        {label}
      </label>
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-10 h-10 rounded-lg cursor-pointer border shrink-0"
        style={{ borderColor: 'var(--bd-border)' }}
      />
      <input
        type="text"
        value={value}
        onChange={(e) => {
          const v = e.target.value.trim();
          if (/^#[0-9A-Fa-f]{6}$/.test(v)) onChange(v);
        }}
        className="flex-1 min-w-0 px-3 py-2 text-sm rounded-lg font-mono"
        style={{
          background: 'var(--bd-overlay)',
          border: '1px solid var(--bd-border)',
          color: 'var(--bd-fg)',
        }}
      />
      {hasOverride && (
        <button
          type="button"
          onClick={onReset}
          className="text-xs px-2 py-1 rounded shrink-0"
          style={{ background: 'var(--bd-overlay)', color: 'var(--bd-fg-subtle)' }}
        >
          默认
        </button>
      )}
    </div>
  );
}

function PreviewBlock({ scheme, colors }: { scheme: ColorScheme; colors: SchemeColors }) {
  const isDark = scheme === 'dark';
  return (
    <div
      className="rounded-xl p-4 border"
      style={{
        background: colors.bg,
        borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'var(--bd-border)',
      }}
    >
      <p className="text-xs mb-3 font-medium" style={{ color: isDark ? 'rgba(255,255,255,0.6)' : 'var(--bd-fg-subtle)' }}>
        预览
      </p>
      <div className="flex flex-wrap gap-2">
        <div className="w-8 h-8 rounded-md shadow-inner" style={{ background: colors.bg }} />
        <div className="w-8 h-8 rounded-md" style={{ background: colors.phaseValues }} />
        <div className="w-8 h-8 rounded-md" style={{ background: colors.phaseStrengths }} />
        <div className="w-8 h-8 rounded-md" style={{ background: colors.phaseInterests }} />
        <div className="w-8 h-8 rounded-md" style={{ background: colors.phasePurpose }} />
        <div className="w-8 h-8 rounded-md" style={{ background: colors.uiAccent }} />
      </div>
    </div>
  );
}

export default function ColorsSettingsPage() {
  const light = useColorThemeStore((s) => s.light);
  const dark = useColorThemeStore((s) => s.dark);
  const setLight = useColorThemeStore((s) => s.setLight);
  const setDark = useColorThemeStore((s) => s.setDark);
  const removeLight = useColorThemeStore((s) => s.removeLight);
  const removeDark = useColorThemeStore((s) => s.removeDark);
  const resetLight = useColorThemeStore((s) => s.resetLight);
  const resetDark = useColorThemeStore((s) => s.resetDark);
  const resetAll = useColorThemeStore((s) => s.resetAll);
  const getEffectiveLight = useColorThemeStore((s) => s.getEffectiveLight);
  const getEffectiveDark = useColorThemeStore((s) => s.getEffectiveDark);

  const [mounted, setMounted] = useState(false);
  const [tab, setTab] = useState<ColorScheme>('light');
  useEffect(() => setMounted(true), []);


  const effLight = getEffectiveLight();
  const effDark = getEffectiveDark();
  const hasLightOverrides = Object.keys(light).length > 0;
  const hasDarkOverrides = Object.keys(dark).length > 0;

  if (!mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bd-bg)' }}>
        <div className="w-10 h-10 rounded-full border-2 animate-spin" style={{ borderColor: 'var(--bd-primary)', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bd-bg)' }}>
      <header
        className="bd-eff-card sticky top-0 z-40 border-b backdrop-blur-md"
        style={{ background: 'var(--bd-nav-bg)', borderColor: 'var(--bd-nav-border)' }}
      >
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
            <ArrowLeft size={18} /> 返回
          </Link>
          <h1 className="text-lg font-semibold" style={{ color: 'var(--bd-fg)' }}>
            配色
          </h1>
          <div className="w-16" />
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-8">
        <p className="text-sm leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
          日间与夜间各有一套配色：背景、四维主题色、导引色。修改后实时生效，并保存到本地。
        </p>

        {/* 预览区块：左右并列 */}
        <div className="grid grid-cols-2 gap-4">
          <PreviewBlock scheme="light" colors={effLight} />
          <PreviewBlock scheme="dark" colors={effDark} />
        </div>

        {/* Tab 切换 */}
        <div className="flex gap-2 border-b" style={{ borderColor: 'var(--bd-border)' }}>
          <button
            type="button"
            onClick={() => setTab('light')}
            className="flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors"
            style={{
              color: tab === 'light' ? 'var(--bd-ui-accent)' : 'var(--bd-fg-muted)',
              borderBottom: tab === 'light' ? '2px solid var(--bd-ui-accent)' : '2px solid transparent',
            }}
          >
            <Sun size={16} /> 日间
          </button>
          <button
            type="button"
            onClick={() => setTab('dark')}
            className="flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors"
            style={{
              color: tab === 'dark' ? 'var(--bd-ui-accent)' : 'var(--bd-fg-muted)',
              borderBottom: tab === 'dark' ? '2px solid var(--bd-ui-accent)' : '2px solid transparent',
            }}
          >
            <Moon size={16} /> 夜间
          </button>
        </div>

        {/* 配置表单 */}
        {tab === 'light' && (
          <div
            className="bd-eff-card rounded-xl p-4 space-y-1"
            style={{ background: 'var(--bd-bg-card)', border: '1px solid var(--bd-border)' }}
          >
            <p className="text-xs font-medium mb-3" style={{ color: 'var(--bd-fg-subtle)' }}>
              日间配色
            </p>
            {KEYS.map((key) => (
              <ColorRow
                key={key}
                label={LABELS[key].zh}
                value={effLight[key]}
                onChange={(v) => setLight(key, v)}
                onReset={() => removeLight(key)}
                hasOverride={key in light}
              />
            ))}
            {hasLightOverrides && (
              <button
                type="button"
                onClick={resetLight}
                className="mt-4 flex items-center gap-2 text-sm"
                style={{ color: 'var(--bd-error)' }}
              >
                <RotateCcw size={14} /> 恢复日间默认
              </button>
            )}
          </div>
        )}
        {tab === 'dark' && (
          <div
            className="bd-eff-card rounded-xl p-4 space-y-1"
            style={{ background: 'var(--bd-bg-card)', border: '1px solid var(--bd-border)' }}
          >
            <p className="text-xs font-medium mb-3" style={{ color: 'var(--bd-fg-subtle)' }}>
              夜间配色
            </p>
            {KEYS.map((key) => (
              <ColorRow
                key={key}
                label={LABELS[key].zh}
                value={effDark[key]}
                onChange={(v) => setDark(key, v)}
                onReset={() => removeDark(key)}
                hasOverride={key in dark}
              />
            ))}
            {hasDarkOverrides && (
              <button
                type="button"
                onClick={resetDark}
                className="mt-4 flex items-center gap-2 text-sm"
                style={{ color: 'var(--bd-error)' }}
              >
                <RotateCcw size={14} /> 恢复夜间默认
              </button>
            )}
          </div>
        )}

        {(hasLightOverrides || hasDarkOverrides) && (
          <button
            type="button"
            onClick={resetAll}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
            style={{ background: 'var(--bd-error-dim)', color: 'var(--bd-error)' }}
          >
            <RotateCcw size={16} /> 恢复全部默认
          </button>
        )}

        <p className="text-xs" style={{ color: 'var(--bd-fg-subtle)' }}>
          配色保存在浏览器本地。顶部导航栏可切换日/夜间模式。
        </p>
      </main>
    </div>
  );
}
