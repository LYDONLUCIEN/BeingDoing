'use client';

import { useEffect, useRef } from 'react';

/** 软键盘可能只缩小 visualViewport；保留 CSS vh/dvh 回退与用户缩放。 */
export function useChatViewport() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => {
      const el = ref.current;
      if (!el) return;
      if (window.innerWidth >= 768 || viewport.scale !== 1) {
        el.style.removeProperty('--chat-visible-height');
        el.style.removeProperty('--chat-visible-top');
        return;
      }
      const top = Math.max(56, viewport.offsetTop);
      el.style.setProperty('--chat-visible-top', `${top}px`);
      el.style.setProperty('--chat-visible-height', `${Math.max(0, viewport.height + viewport.offsetTop - top)}px`);
    };
    update();
    viewport.addEventListener('resize', update);
    viewport.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    return () => {
      viewport.removeEventListener('resize', update);
      viewport.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, []);
  return ref;
}
