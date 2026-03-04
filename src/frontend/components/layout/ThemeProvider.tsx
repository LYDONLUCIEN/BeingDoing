'use client';

import { useEffect } from 'react';
import { useThemeStore } from '@/stores/themeStore';

/**
 * Syncs the Zustand theme store to data-theme on <html>.
 * The initial theme is set by an inline <script> in layout.tsx before hydration,
 * so this component only needs to handle subsequent theme changes.
 */
export default function ThemeProvider() {
  const { themeId } = useThemeStore();

  useEffect(() => {
    const current = document.documentElement.getAttribute('data-theme');
    if (current !== themeId) {
      document.documentElement.setAttribute('data-theme', themeId);
    }
  }, [themeId]);

  return null;
}
