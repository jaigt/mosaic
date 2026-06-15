import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMediaQuery } from './useMediaQuery';

type Listener = () => void;

// Minimal controllable matchMedia stub: jsdom doesn't implement it.
function stubMatchMedia(initialMatches: boolean) {
  let matches = initialMatches;
  const listeners = new Set<Listener>();
  const mql = {
    get matches() {
      return matches;
    },
    media: '',
    addEventListener: (_: string, cb: Listener) => listeners.add(cb),
    removeEventListener: (_: string, cb: Listener) => listeners.delete(cb),
  };
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia;
  return {
    set(next: boolean) {
      matches = next;
      listeners.forEach((cb) => cb());
    },
  };
}

describe('useMediaQuery', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns the initial match state', () => {
    stubMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery('(max-width: 767px)'));
    expect(result.current).toBe(true);
  });

  it('updates when the media query changes', () => {
    const ctrl = stubMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery('(max-width: 767px)'));
    expect(result.current).toBe(false);
    act(() => ctrl.set(true));
    expect(result.current).toBe(true);
  });
});
