import { describe, it, expect } from 'vitest';
import { resolveSeries } from './FinancialChart';
import type { ChartSpec } from './FinancialChart';

describe('resolveSeries', () => {
  it('back-compat: single-series `value` shape resolves to ["value"] as a bar', () => {
    const spec: ChartSpec = {
      title: 'Revenue ($B)',
      data: [
        { name: '2022', value: 117.1 },
        { name: '2023', value: 134.9 },
      ],
    };
    expect(resolveSeries(spec)).toEqual({ type: 'bar', series: ['value'] });
  });

  it('uses explicit series in the given order', () => {
    const spec: ChartSpec = {
      type: 'bar',
      title: 'Revenue',
      data: [{ name: '2023', AAPL: 383.3, MSFT: 211.9 }],
      series: ['MSFT', 'AAPL'],
    };
    expect(resolveSeries(spec)).toEqual({ type: 'bar', series: ['MSFT', 'AAPL'] });
  });

  it('infers multiple series from data keys in first-seen order (excluding name)', () => {
    const spec: ChartSpec = {
      type: 'line',
      data: [
        { name: '2023', AAPL: 383.3, MSFT: 211.9 },
        { name: '2024', AAPL: 391.0, MSFT: 245.1, GOOG: 307.4 },
      ],
    };
    expect(resolveSeries(spec)).toEqual({ type: 'line', series: ['AAPL', 'MSFT', 'GOOG'] });
  });

  it('defaults type to "bar" when omitted', () => {
    const spec: ChartSpec = { data: [{ name: 'A', value: 1 }] };
    expect(resolveSeries(spec).type).toBe('bar');
  });

  it('passes through line and area types', () => {
    expect(resolveSeries({ type: 'line', data: [{ name: 'A', value: 1 }] }).type).toBe('line');
    expect(resolveSeries({ type: 'area', data: [{ name: 'A', value: 1 }] }).type).toBe('area');
  });

  it('falls back to "bar" for an unknown type', () => {
    const spec: ChartSpec = { type: 'pie', data: [{ name: 'A', value: 1 }] };
    expect(resolveSeries(spec).type).toBe('bar');
  });

  it('returns empty series for empty/malformed data with no explicit series', () => {
    expect(resolveSeries({ data: [] })).toEqual({ type: 'bar', series: [] });
    expect(resolveSeries({})).toEqual({ type: 'bar', series: [] });
    expect(resolveSeries(null)).toEqual({ type: 'bar', series: [] });
    expect(resolveSeries(undefined)).toEqual({ type: 'bar', series: [] });
  });

  it('ignores an empty explicit series array and infers instead', () => {
    const spec: ChartSpec = { data: [{ name: '2023', AAPL: 1 }], series: [] };
    expect(resolveSeries(spec)).toEqual({ type: 'bar', series: ['AAPL'] });
  });

  it('filters non-string / empty entries out of an explicit series', () => {
    const spec = {
      data: [{ name: '2023', AAPL: 1, MSFT: 2 }],
      series: ['AAPL', '', null, 'MSFT'],
    } as unknown as ChartSpec;
    expect(resolveSeries(spec)).toEqual({ type: 'bar', series: ['AAPL', 'MSFT'] });
  });
});
