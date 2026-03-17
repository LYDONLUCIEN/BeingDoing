'use client';

import ThemeProvider from './ThemeProvider';
import PhaseColorInjector from './PhaseColorInjector';
import DesignEffectsInjector from './DesignEffectsInjector';
import ChunkErrorRecovery from './ChunkErrorRecovery';

/**
 * Single client boundary wrapper.
 * Fixes "Cannot read properties of null (reading 'useContext')" by ensuring
 * all client components share a consistent React context tree.
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
