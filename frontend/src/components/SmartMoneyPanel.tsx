import React, { useEffect, useState } from 'react';
import { LogOut } from 'lucide-react';
import { getSmartMoney, SmartMoney, FundPosition, FundChange } from '../api';
import { Badge, Spinner, cn } from './ui';

interface SmartMoneyPanelProps {
  ticker: string | null;
}

type Tone = 'ledger' | 'amber' | 'crimson' | 'neutral';

/** Map a 13F position change to a Badge tone. Pure; unknown → neutral. */
export function changeTone(change: FundChange | string | null | undefined): Tone {
  switch (change) {
    case 'added':
    case 'new':
      return 'ledger';
    case 'trimmed':
      return 'amber';
    case 'exited':
      return 'crimson';
    default:
      return 'neutral';
  }
}

/** Compact USD for large book values: $57.8B, $850M, $1.2M, $4.2K, $312. Null/NaN → "—".
 *  One decimal place, with a trailing ".0" trimmed (so 850M → "$850M", not "$850.0M"). */
export function formatDollars(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const sign = n < 0 ? '−' : '';
  const abs = Math.abs(n);
  const compact = (v: number, suffix: string) =>
    `${sign}$${v.toFixed(1).replace(/\.0$/, '')}${suffix}`;
  if (abs >= 1_000_000_000) return compact(abs / 1_000_000_000, 'B');
  if (abs >= 1_000_000) return compact(abs / 1_000_000, 'M');
  if (abs >= 1_000) return compact(abs / 1_000, 'K');
  return `${sign}$${Math.round(abs).toLocaleString()}`;
}

/** Compact share count for the exits subsection. Null/NaN → "—". */
function formatShares(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}K`;
  return Math.round(n).toLocaleString();
}

/** Percent of the fund's book. Null/NaN/0 → null (caller hides it). */
function formatPct(n: number | null | undefined): string | null {
  if (n === null || n === undefined || !Number.isFinite(n) || n === 0) return null;
  return `${n.toFixed(n >= 10 ? 0 : 1)}%`;
}

const SmartMoneyPanel: React.FC<SmartMoneyPanelProps> = ({ ticker }) => {
  const [data, setData] = useState<SmartMoney | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!ticker) {
      setLoading(false);
      setError(false);
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    setData(null);
    getSmartMoney(ticker)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const positions = data?.positions ?? [];
  const exits = data?.exits ?? [];
  const indexEmpty = data != null && !data.refreshed_at;

  if (!ticker) {
    return (
      <section aria-label="Superinvestors" className="px-5 pb-4 pt-3">
        <SectionLabel>Superinvestors</SectionLabel>
        <div className="px-1 py-3 font-serif text-[13px] italic leading-relaxed text-fg-400">
          Select a filing or ask about a company to see who holds it.
        </div>
      </section>
    );
  }

  return (
    <section aria-label={`Superinvestors holding ${ticker}`} className="px-5 pb-4 pt-3">
      <SectionLabel>
        Superinvestors · {ticker}
        {!loading && !error && positions.length > 0 && (
          <span className="font-mono text-[9.5px] tabular-nums text-fg-300">{positions.length}</span>
        )}
      </SectionLabel>

      {loading ? (
        <div className="flex items-center gap-2 px-1 py-3 font-serif text-[13px] italic text-fg-400">
          <Spinner size={13} label="Loading smart-money holders" />
          Polling the 13F crowd…
        </div>
      ) : error ? (
        <div className="px-1 py-3 font-serif text-[13px] italic leading-relaxed text-fg-400">
          Couldn't load smart-money holders right now.
        </div>
      ) : indexEmpty ? (
        <div className="px-1 py-3 font-serif text-[13px] italic leading-relaxed text-fg-400">
          Smart-money index not built yet — run a refresh.
        </div>
      ) : positions.length === 0 ? (
        <div className="px-1 py-3 font-serif text-[13px] italic leading-relaxed text-fg-400">
          No tracked superinvestors hold {ticker}.
        </div>
      ) : (
        <>
          <ul className="max-h-64 space-y-1 overflow-y-auto pr-0.5">
            {positions.map((p, i) => (
              <HolderRow key={`${p.cik}-${i}`} pos={p} />
            ))}
          </ul>
          {exits.length > 0 && <Exits exits={exits} />}
        </>
      )}
    </section>
  );
};

const HolderRow: React.FC<{ pos: FundPosition }> = ({ pos }) => {
  const tone = changeTone(pos.change);
  const fund = pos.fund || 'Unknown fund';
  const pct = formatPct(pos.pct);

  return (
    <li className="flex items-center gap-2 rounded-md border-l-2 border-line bg-ink-800/70 px-2.5 py-1.5">
      <div className="min-w-0 flex-1">
        <div className="truncate font-mono text-[12px] font-semibold text-fg-100" title={fund}>{fund}</div>
        {pct && <div className="font-serif text-[11px] italic text-fg-400">{pct} of book</div>}
      </div>
      <Badge tone={tone} mono className="shrink-0 px-1.5 py-0.5 text-[9px]" title={`Position ${pos.change}`}>
        {pos.change}
      </Badge>
      <div className="w-[64px] shrink-0 text-right">
        <div
          className={cn(
            'font-mono text-[11.5px] font-semibold tabular-nums',
            tone === 'ledger'
              ? 'text-ledger-300'
              : tone === 'crimson'
                ? 'text-crimson-400'
                : tone === 'amber'
                  ? 'text-amber-300'
                  : 'text-fg-200',
          )}
        >
          {formatDollars(pos.value)}
        </div>
      </div>
    </li>
  );
};

const Exits: React.FC<{ exits: FundPosition[] }> = ({ exits }) => (
  <div className="mt-3">
    <div className="flex items-center gap-1.5 pb-1.5 font-mono text-[9.5px] font-semibold uppercase tracking-[0.2em] text-crimson-400">
      <LogOut size={10} aria-hidden="true" />
      Recent exits
    </div>
    <ul className="space-y-1">
      {exits.map((e, i) => (
        <li
          key={`${e.cik}-exit-${i}`}
          className="flex items-center gap-2 rounded-md border-l-2 border-crimson-500/40 bg-ink-800/70 px-2.5 py-1.5"
        >
          <div
            className="min-w-0 flex-1 truncate font-mono text-[12px] font-semibold text-fg-200"
            title={e.fund || 'Unknown fund'}
          >
            {e.fund || 'Unknown fund'}
          </div>
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-fg-400">
            sold {formatShares(e.prev_shares)} sh
          </span>
        </li>
      ))}
    </ul>
  </div>
);

const SectionLabel: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex items-center gap-2.5 pb-2.5 font-mono text-[9.5px] font-semibold uppercase tracking-[0.24em] text-fg-400">
    {children}
    <span className="h-px flex-1 bg-line" aria-hidden="true" />
  </div>
);

export default SmartMoneyPanel;
