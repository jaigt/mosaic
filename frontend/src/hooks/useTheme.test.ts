import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTheme, readStoredTheme, THEME_STORAGE_KEY } from './useTheme';

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it('defaults to study when nothing is stored', () => {
    expect(readStoredTheme()).toBe('study');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('study');
    expect(document.documentElement.dataset.theme).toBe('study');
  });

  it('ignores a foreign stored value and falls back to study', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'neon');
    expect(readStoredTheme()).toBe('study');
  });

  it('initialises from a valid stored theme', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'modern-dark');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('modern-dark');
    expect(document.documentElement.dataset.theme).toBe('modern-dark');
  });

  it('setTheme updates state, the <html> attribute, and persists to localStorage', () => {
    const { result } = renderHook(() => useTheme());

    act(() => result.current.setTheme('modern-light'));
    expect(result.current.theme).toBe('modern-light');
    expect(document.documentElement.dataset.theme).toBe('modern-light');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('modern-light');

    act(() => result.current.setTheme('modern-dark'));
    expect(document.documentElement.dataset.theme).toBe('modern-dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('modern-dark');
  });
});
