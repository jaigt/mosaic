import { describe, it, expect, beforeEach } from 'vitest';
import { loadMessages } from './ChatPanel';

const KEY = 'vr.chat.v1';

describe('loadMessages (chat persistence)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns an empty array when nothing is stored', () => {
    expect(loadMessages()).toEqual([]);
  });

  it('restores valid messages and never marks them as streaming', () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([
        { id: 'a', role: 'user', content: 'How is NVDA doing?' },
        { id: 'b', role: 'assistant', content: 'Fine.', isStreaming: true },
      ]),
    );
    const restored = loadMessages();
    expect(restored).toHaveLength(2);
    expect(restored[1]).toMatchObject({ id: 'b', role: 'assistant', content: 'Fine.' });
    expect(restored.every((m) => m.isStreaming === false)).toBe(true);
  });

  it('caps to the last 50 messages', () => {
    const many = Array.from({ length: 60 }, (_, i) => ({
      id: String(i),
      role: 'user' as const,
      content: `m${i}`,
    }));
    localStorage.setItem(KEY, JSON.stringify(many));
    const restored = loadMessages();
    expect(restored).toHaveLength(50);
    expect(restored[0].id).toBe('10');
    expect(restored[49].id).toBe('59');
  });

  it('is robust to corrupt or foreign payloads', () => {
    localStorage.setItem(KEY, 'not json');
    expect(loadMessages()).toEqual([]);

    localStorage.setItem(KEY, JSON.stringify({ not: 'an array' }));
    expect(loadMessages()).toEqual([]);

    localStorage.setItem(KEY, JSON.stringify([{ foo: 'bar' }, { id: 'x', role: 'user', content: 'ok' }]));
    expect(loadMessages()).toEqual([{ id: 'x', role: 'user', content: 'ok', isStreaming: false }]);
  });
});
