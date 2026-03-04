'use client';

import { useEffect } from 'react';
import { useColorThemeStore, getColorThemeCSS, DEFAULT_LIGHT, DEFAULT_DARK } from '@/stores/colorThemeStore';

const STYLE_ID = 'bd-color-theme-inject';

/**
 * 根据 colorThemeStore 注入 light/dark 配色，按 data-color-scheme 生效。
 * 覆盖主题默认的背景、四维色、导引色。
 */
export default function PhaseColorInjector() {
  const lightOverrides = useColorThemeStore((s) => s.light);
  const darkOverrides = useColorThemeStore((s) => s.dark);

  useEffect(() => {
    const light = { ...DEFAULT_LIGHT, ...lightOverrides };
    const dark = { ...DEFAULT_DARK, ...darkOverrides };
    const css = getColorThemeCSS(light, dark);

    let el = document.getElementById(STYLE_ID);
    if (!el) {
      el = document.createElement('style');
      el.id = STYLE_ID;
      document.head.appendChild(el);
    }
    el.textContent = css;
  }, [lightOverrides, darkOverrides]);

  return null;
}
