'use client';

import { useEffect } from 'react';
import { useThemeStore } from '@/stores/themeStore';

/**
 * Syncs the Zustand theme store to data-theme and data-color-scheme on <html>.
 */
export default function ThemeProvider() {
  const { themeId, colorScheme } = useThemeStore();

  useEffect(() => {
    const nextTheme = themeId;
    const nextScheme = colorScheme;
    if (document.documentElement.getAttribute('data-theme') !== nextTheme) {
      document.documentElement.setAttribute('data-theme', nextTheme);
    }
    if (document.documentElement.getAttribute('data-color-scheme') !== nextScheme) {
      document.documentElement.setAttribute('data-color-scheme', nextScheme);
    }
  }, [themeId, colorScheme]);

  return null;
}
