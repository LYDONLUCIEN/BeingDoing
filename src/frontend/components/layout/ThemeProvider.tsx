'use client';

import { useEffect } from 'react';
import { useThemeStore, DARK_THEMES } from '@/stores/themeStore';

/**
 * Syncs the Zustand theme store to data-theme and data-color-scheme on <html>.
 */
export default function ThemeProvider() {
  const { themeId, colorScheme } = useThemeStore();

  useEffect(() => {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const scheme = DARK_THEMES.includes(themeId) ? 'dark' : 'light';
    if (currentTheme !== themeId) {
      document.documentElement.setAttribute('data-theme', themeId);
    }
    document.documentElement.setAttribute('data-color-scheme', scheme);
  }, [themeId, colorScheme]);

  return null;
}
