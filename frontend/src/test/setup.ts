import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom in this config doesn't always expose a usable localStorage; provide a
// minimal in-memory implementation so persistence code paths can run in tests.
if (typeof globalThis.localStorage === 'undefined') {
  const store = new Map<string, string>();
  const mock: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    removeItem: (k: string) => void store.delete(k),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
  };
  Object.defineProperty(globalThis, 'localStorage', { value: mock, configurable: true });
}

afterEach(() => {
  cleanup();
});
