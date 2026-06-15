import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import InsiderPanel, { sentiment, formatShares, formatPrice } from './InsiderPanel';

describe('sentiment', () => {
  it('labels positive net as net buying with ledger tone', () => {
    expect(sentiment(12000)).toEqual({ label: 'Net buying: +12K sh', tone: 'ledger' });
  });

  it('labels negative net as net selling with crimson tone', () => {
    expect(sentiment(-5000)).toEqual({ label: 'Net selling: −5.0K sh', tone: 'crimson' });
  });

  it('labels zero/invalid net as flat/neutral', () => {
    expect(sentiment(0).tone).toBe('neutral');
    expect(sentiment(null).tone).toBe('neutral');
    expect(sentiment(undefined).tone).toBe('neutral');
    expect(sentiment(NaN).tone).toBe('neutral');
  });
});

describe('formatShares / formatPrice', () => {
  it('abbreviates thousands and millions', () => {
    expect(formatShares(950)).toBe('950');
    expect(formatShares(2500)).toBe('2.5K');
    expect(formatShares(3_400_000)).toBe('3.4M');
  });

  it('is null-safe', () => {
    expect(formatShares(null)).toBe('—');
    expect(formatShares(undefined)).toBe('—');
    expect(formatPrice(null)).toBeNull();
    expect(formatPrice(42.5)).toBe('$42.50');
  });
});

describe('InsiderPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the summary and transaction rows from a mocked fetch', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        ticker: 'AAPL',
        buys: 2,
        sells: 1,
        bought_shares: 15000,
        sold_shares: 3000,
        net_shares: 12000,
        transactions: [
          {
            insider: 'Tim Cook',
            position: 'CEO',
            date: '2026-05-01',
            txn_type: 'buy',
            code: 'P',
            description: 'Open market purchase',
            shares: 10000,
            price: 190.25,
            value: 1902500,
          },
          {
            insider: 'Luca Maestri',
            position: 'CFO',
            date: '2026-04-15',
            txn_type: 'sell',
            code: 'S',
            description: 'Sale',
            shares: 3000,
            price: null,
            value: null,
          },
        ],
      }),
    } as Response);

    render(<InsiderPanel ticker="AAPL" />);

    await waitFor(() => expect(screen.getByText('Net buying: +12K sh')).toBeInTheDocument());
    expect(screen.getByText('2 buys · 1 sells')).toBeInTheDocument();
    expect(screen.getByText('Tim Cook')).toBeInTheDocument();
    expect(screen.getByText('Luca Maestri')).toBeInTheDocument();
    expect(screen.getByText('$190.25')).toBeInTheDocument();
  });

  it('shows an empty state when there are no transactions', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        ticker: 'MSFT',
        buys: 0,
        sells: 0,
        bought_shares: 0,
        sold_shares: 0,
        net_shares: 0,
        transactions: [],
      }),
    } as Response);

    render(<InsiderPanel ticker="MSFT" />);

    await waitFor(() =>
      expect(screen.getByText('No recent insider activity for MSFT.')).toBeInTheDocument(),
    );
  });
});
