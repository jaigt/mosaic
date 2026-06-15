import { describe, it, expect } from 'vitest';
import { dominantTicker } from './App';
import type { Source } from './api';

// Minimal Source factory — only `ticker` matters for dominantTicker.
const src = (ticker: string): Source => ({
  ticker,
  year: 2024,
  quarter: '',
  section: '',
  chunk_type: '',
  text_content: '',
  raw_payload: '',
  score: 0,
});

describe('dominantTicker', () => {
  it('returns the single ticker when all sources agree', () => {
    expect(dominantTicker([src('NVDA'), src('NVDA'), src('NVDA')])).toBe('NVDA');
  });

  it('returns the most frequent ticker across multiple', () => {
    expect(dominantTicker([src('AAPL'), src('MSFT'), src('MSFT')])).toBe('MSFT');
  });

  it('breaks ties in favor of the first ticker seen', () => {
    // AAPL and MSFT both appear twice; AAPL was seen first.
    expect(dominantTicker([src('AAPL'), src('MSFT'), src('MSFT'), src('AAPL')])).toBe('AAPL');
  });

  it('returns null for an empty source list', () => {
    expect(dominantTicker([])).toBeNull();
  });

  it('ignores blank / missing tickers', () => {
    expect(dominantTicker([src('   '), src(''), src('TSLA')])).toBe('TSLA');
    expect(dominantTicker([src(''), src('  ')])).toBeNull();
  });

  it('tolerates sources with no ticker field at all', () => {
    const broken = [{ year: 2024 } as unknown as Source, src('GOOGL')];
    expect(dominantTicker(broken)).toBe('GOOGL');
  });
});
