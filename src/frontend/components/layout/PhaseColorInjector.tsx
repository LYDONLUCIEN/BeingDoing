'use client';

import { useEffect } from 'react';
import { usePhaseColorStore, getPhaseColorCSS } from '@/stores/phaseColorStore';

const STYLE_ID = 'bd-phase-color-overrides';

/**
 * 当用户设置了阶段配色覆盖时，注入 CSS 覆盖 :root 的 --bd-phase-* 变量。
 * 保证首页、探索页等全站阶段相关 UI 使用统一配色。
 */
export default function PhaseColorInjector() {
  const overrides = usePhaseColorStore((s) => s.overrides);

  useEffect(() => {
    const css = getPhaseColorCSS(overrides);
    let el = document.getElementById(STYLE_ID);
    if (css) {
      if (!el) {
        el = document.createElement('style');
        el.id = STYLE_ID;
        document.head.appendChild(el);
      }
      el.textContent = css;
    } else if (el) {
      el.remove();
    }
  }, [overrides]);

  return null;
}
