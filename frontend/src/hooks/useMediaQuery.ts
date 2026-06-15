import { useEffect, useState } from 'react';

/**
 * Subscribes to a CSS media query and returns whether it currently matches.
 * SSR-safe (returns false when `matchMedia` is unavailable) and re-evaluates
 * on viewport changes. Used to switch between the desktop split layout and the
 * stacked mobile layout.
 */
export function useMediaQuery(query: string): boolean {
  const getMatch = () =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false;

  const [matches, setMatches] = useState(getMatch);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

/** Tablet-and-below breakpoint. Mirrors Tailwind's `md` (768px). */
export const MOBILE_QUERY = '(max-width: 767px)';

/** True when the viewport is tablet-sized or smaller. */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY);
}
