import { useCallback, useEffect, useState } from 'react';

/** The three available themes. `study` is the default engraved-ledger look. */
export type Theme = 'study' | 'modern-light' | 'modern-dark';

export const THEMES: Theme[] = ['study', 'modern-light', 'modern-dark'];

export const THEME_STORAGE_KEY = 'vr.theme';
export const DEFAULT_THEME: Theme = 'study';

function isTheme(value: unknown): value is Theme {
  return value === 'study' || value === 'modern-light' || value === 'modern-dark';
}

/** Read the persisted theme, falling back to the default. Null/foreign → study. */
export function readStoredTheme(): Theme {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(raw) ? raw : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

/** Apply a theme to <html> (drives the `data-theme` CSS variable overrides). */
export function applyTheme(theme: Theme): void {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = theme;
  }
}

/**
 * Theme state synced to <html data-theme> and persisted to localStorage.
 * Initialises from the value the no-flash inline script already applied (so the
 * hook never re-flashes), defaulting to `study`.
 */
export function useTheme(): { theme: Theme; setTheme: (theme: Theme) => void } {
  const [theme, setThemeState] = useState<Theme>(() => {
    const current = typeof document !== 'undefined' ? document.documentElement.dataset.theme : undefined;
    return isTheme(current) ? current : readStoredTheme();
  });

  // Keep <html> in sync if state was initialised from storage rather than the DOM.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    applyTheme(next);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Storage unavailable (private mode / quota) — keep the in-memory theme.
    }
  }, []);

  return { theme, setTheme };
}
