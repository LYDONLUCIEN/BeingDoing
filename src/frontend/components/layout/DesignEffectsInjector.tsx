'use client';

import { useEffect } from 'react';
import {
  useDesignEffectsStore,
  getEffectPresetCSS,
  EFFECT_PRESET_IDS,
} from '@/stores/designEffectsStore';

const STYLE_ID = 'bd-design-effects-overrides';
const EFFECT_ATTR = 'data-bd-effect';

/**
 * 注入效果预设的 CSS 变量，并设置 data-bd-effect 以启用效果层规则。
 * presetId 为 none 或空时，移除注入和属性。
 */
export default function DesignEffectsInjector() {
  const presetId = useDesignEffectsStore((s) => s.presetId);

  useEffect(() => {
    const id = presetId || 'none';
    const effectiveId = id === 'none' || !EFFECT_PRESET_IDS.includes(id) ? '' : id;
    const css = getEffectPresetCSS(effectiveId as any);

    // CSS 变量
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

    // data-bd-effect 属性（用于效果层选择器）
    if (effectiveId) {
      document.documentElement.setAttribute(EFFECT_ATTR, effectiveId);
    } else {
      document.documentElement.removeAttribute(EFFECT_ATTR);
    }
  }, [presetId]);

  return null;
}
