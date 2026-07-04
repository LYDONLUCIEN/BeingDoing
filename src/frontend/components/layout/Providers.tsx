'use client';

import ThemeProvider from './ThemeProvider';
import PhaseColorInjector from './PhaseColorInjector';
import DesignEffectsInjector from './DesignEffectsInjector';
import ChunkErrorRecovery from './ChunkErrorRecovery';

/**
 * Single client boundary wrapper.
 * Fixes "Cannot read properties of null (reading 'useContext')" by ensuring
 * all client components share a consistent React context tree.
 *
 * 注：SiteNoticeBanner 不再放在这里——它需要在 (main) 布局里贴在
 * TopNavbar 下方（sticky top-14），放 Providers 会造成渲染顺序晚于
 * fixed 的 navbar，被 z-50 遮挡。
 */
export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ChunkErrorRecovery />
      <ThemeProvider />
      <PhaseColorInjector />
      <DesignEffectsInjector />
      {children}
    </>
  );
}
