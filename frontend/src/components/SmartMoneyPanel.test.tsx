import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SmartMoneyPanel, { formatDollars, changeTone } from './SmartMoneyPanel';

describe('formatDollars', () => {
  it('abbreviates billions, millions, thousands', () => {
    expect(formatDollars(57_800_000_000)).toBe('$57.8B');
    expect(formatDollars(850_000_000)).toBe('$850M');
    expect(formatDollars(1_200_000)).toBe('$1.2M');
    expect(formatDollars(4_200)).toBe('$4.2K');
    expect(formatDollars(312)).toBe('$312');
  });

  it('rounds large magnitudes to whole units', () => {
    expect(formatDollars(12_000_000_000)).toBe('$12B');
    expect(formatDollars(15_000_000)).toBe('$15M');
  });

  it('handles sign and is null/zero-safe', () => {
    expect(formatDollars(-2_000_000)).toBe('−$2M');
    expect(formatDollars(-2_300_000)).toBe('−$2.3M');
    expect(formatDollars(0)).toBe('$0');
    expect(formatDollars(null)).toBe('—');
    expect(formatDollars(undefined)).toBe('—');
    expect(formatDollars(NaN)).toBe('—');
  });
});

describe('changeTone', () => {
  it('maps added/new to ledger', () => {
    expect(changeTone('added')).toBe('ledger');
    expect(changeTone('new')).toBe('ledger');
  });
  it('maps trimmed to amber', () => {
    expect(changeTone('trimmed')).toBe('amber');
  });
  it('maps exited to crimson', () => {
    expect(changeTone('exited')).toBe('crimson');
  });
  it('maps unchanged/unknown/nullish to neutral', () => {
    expect(changeTone('unchanged')).toBe('neutral');
    expect(changeTone('whatever')).toBe('neutral');
    expect(changeTone(null)).toBe('neutral');
    expect(changeTone(undefined)).toBe('neutral');
  });
});

describe('SmartMoneyPanel', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders holders, a change badge, and a recent exit from a mocked fetch', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        ticker: 'AAPL',
        refreshed_at: '2026-05-01T00:00:00Z',
        positions: [
          {
            fund: 'Berkshire Hathaway',
            cik: '0001067983',
            ticker: 'AAPL',
            issuer: 'APPLE INC',
            value: 57_800_000_000,
            shares: 300_000_000,
            pct: 41.2,
            as_of: '2026-03-31',
            change: 'trimmed',
            prev_shares: 350_000_000,
          },
          {
            fund: 'Pershing Square',
            cik: '0001336528',
            ticker: 'AAPL',
            issuer: 'APPLE INC',
            value: 850_000_000,
            shares: 4_500_000,
            pct: 9,
            as_of: '2026-03-31',
            change: 'added',
            prev_shares: 3_000_000,
          },
        ],
        exits: [
          {
            fund: 'Scion Asset Management',
            cik: '0001649339',
            ticker: 'AAPL',
            issuer: 'APPLE INC',
            value: 0,
            shares: 0,
            pct: 0,
            as_of: '2026-03-31',
            change: 'exited',
            prev_shares: 1_200_000,
          },
        ],
      }),
    } as Response);

    render(<SmartMoneyPanel ticker="AAPL" />);

    await waitFor(() => expect(screen.getByText('Berkshire Hathaway')).toBeInTheDocument());
    expect(screen.getByText('Pershing Square')).toBeInTheDocument();
    expect(screen.getByText('$57.8B')).toBeInTheDocument();
    expect(screen.getByText('trimmed')).toBeInTheDocument();
    expect(screen.getByText('added')).toBeInTheDocument();
    expect(screen.getByText('41% of book')).toBeInTheDocument();
    // Recent exits subsection
    expect(screen.getByText('Recent exits')).toBeInTheDocument();
    expect(screen.getByText('Scion Asset Management')).toBeInTheDocument();
    expect(screen.getByText(/sold/).textContent).toContain('1.2M');
  });

  it('shows the index-not-built hint when refreshed_at is empty', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ ticker: 'MSFT', refreshed_at: '', positions: [], exits: [] }),
    } as Response);

    render(<SmartMoneyPanel ticker="MSFT" />);

    await waitFor(() =>
      expect(screen.getByText('Smart-money index not built yet — run a refresh.')).toBeInTheDocument(),
    );
  });

  it('shows an empty-for-ticker state when no superinvestors hold it', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({
        ticker: 'XYZ',
        refreshed_at: '2026-05-01T00:00:00Z',
        positions: [],
        exits: [],
      }),
    } as Response);

    render(<SmartMoneyPanel ticker="XYZ" />);

    await waitFor(() =>
      expect(screen.getByText('No tracked superinvestors hold XYZ.')).toBeInTheDocument(),
    );
  });
});
