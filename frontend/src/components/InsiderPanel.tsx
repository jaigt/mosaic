import React, { useEffect, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { getInsiderActivity, InsiderActivity, InsiderTxn } from '../api';
import { Badge, Spinner, cn } from './ui';

interface InsiderPanelProps {
  ticker: string | null;
}

type Tone = 'ledger' | 'crimson' | 'neutral';

/** Net-flow sentiment from Form 4 buys vs sells. Pure + null-safe. */
export function sentiment(netShares: number | null | undefined): {
  label: string;
  tone: Tone;
} {
  const net = Number.isFinite(netShares) ? (netShares as number) : 0;
  if (net > 0) return { label: `Net buying: +${formatShares(net)} sh`, tone: 'ledger' };
  if (net < 0) return { label: `Net selling: −${formatShares(Math.abs(net))} sh`, tone: 'crimson' };
  return { label: 'Flat: no net change', tone: 'neutral' };
}

/** Compact, locale-aware share count. Null/NaN → "—". */
export function formatShares(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${(n / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}K`;
  return Math.round(n).toLocaleString();
}

/** USD price per share. Null/NaN → null (caller hides it). */
export function formatPrice(n: number | null | undefined): string | null {
  if (n === null || n === undefined || !Number.isFinite(n)) return null;
  return `$${n.toFixed(2)}`;
}

const txnTone: Record<InsiderTxn['txn_type'], Tone> = {
  buy: 'ledger',
  sell: 'crimson',
  other: 'neutral',
};

const InsiderPanel: React.FC<InsiderPanelProps> = ({ ticker }) => {
  const [data, setData] = useState<InsiderActivity | null>(null);
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
    getInsiderActivity(ticker)
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

  const txns = data?.transactions ?? [];

  if (!ticker) {
    return (
      <section aria-label="Insider activity" className="px-5 pb-4 pt-3">
        <SectionLabel>Insider Activity</SectionLabel>
        <div className="px-1 py-3 font-serif text-[13px] italic leading-relaxed text-fg-400">
          Select a filing or ask about a company to see its insider activity.
        </div>
      </section>
    );
  }

  return (
    <section aria-label={`Insider activity for ${ticker}`} className="px-5 pb-4 pt-3">
      <SectionLabel>Insider Activity · {ticker}</SectionLabel>

      {loading ? (
        <div className="flex items-center gap-2 px-1 py-3 font-serif text-[13px] italic text-fg-400">
          <Spinner size={13} label="Loading insider activity" />
          Reading the Form 4 tape…
        </div>
      ) : error ? (
        <div className="px-1 py-3 font-serif text-[13px] italic leading-relaxed text-fg-400">
          Couldn't load insider activity right now.
        </div>
      ) : txns.length === 0 ? (
        <div className="px-1 py-3 font-serif text-[13px] italic leading-relaxed text-fg-400">
          No recent insider activity for {ticker}.
        </div>
      ) : (
        <>
          <Summary data={data!} />
          <ul className="mt-2.5 max-h-64 space-y-1 overflow-y-auto pr-0.5">
            {txns.map((t, i) => (
              <TxnRow key={i} txn={t} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
};

const Summary: React.FC<{ data: InsiderActivity }> = ({ data }) => {
  const s = sentiment(data.net_shares);
  const buys = Number.isFinite(data.buys) ? data.buys : 0;
  const sells = Number.isFinite(data.sells) ? data.sells : 0;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone={s.tone} pill mono className="tabular-nums">
        {s.tone === 'ledger' ? (
          <ArrowUpRight size={11} aria-hidden="true" />
        ) : s.tone === 'crimson' ? (
          <ArrowDownRight size={11} aria-hidden="true" />
        ) : (
          <Minus size={11} aria-hidden="true" />
        )}
        {s.label}
      </Badge>
      <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] tabular-nums text-fg-400">
        {buys} buys · {sells} sells
      </span>
    </div>
  );
};

const TxnRow: React.FC<{ txn: InsiderTxn }> = ({ txn }) => {
  const tone = txnTone[txn.txn_type] ?? 'neutral';
  const price = formatPrice(txn.price);
  const date = txn.date || '—';
  const insider = txn.insider || 'Unknown';

  return (
    <li className="rounded-md border-l-2 border-line bg-ink-800/70 px-2.5 py-1.5">
      {/* Top row: insider name (full width, truncates gracefully) + type tag. */}
      <div className="flex items-center gap-2">
        <span
          className="min-w-0 flex-1 truncate font-mono text-[12px] font-semibold text-fg-100"
          title={insider}
        >
          {insider}
        </span>
        <Badge
          tone={tone}
          mono
          className="shrink-0 px-1.5 py-0.5 text-[9px]"
          title={txn.description || txn.code || txn.txn_type}
        >
          {txn.txn_type}
        </Badge>
      </div>
      {/* Bottom row: compact single-line date + position, then shares/price. */}
      <div className="mt-0.5 flex items-baseline gap-2">
        <div className="min-w-0 flex-1 overflow-hidden">
          <span className="whitespace-nowrap font-mono text-[10px] tabular-nums text-fg-400">{date}</span>
          {txn.position && (
            <span className="ml-1.5 truncate font-serif text-[11px] italic text-fg-400" title={txn.position}>
              · {txn.position}
            </span>
          )}
        </div>
        <div className="shrink-0 text-right">
          <span
            className={cn(
              'font-mono text-[11.5px] font-semibold tabular-nums',
              tone === 'ledger' ? 'text-ledger-300' : tone === 'crimson' ? 'text-crimson-400' : 'text-fg-200',
            )}
          >
            {formatShares(txn.shares)}
          </span>
          {price && <span className="ml-1.5 font-mono text-[10px] tabular-nums text-fg-400">{price}</span>}
        </div>
      </div>
    </li>
  );
};

const SectionLabel: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex items-center gap-2.5 pb-2.5 font-mono text-[9.5px] font-semibold uppercase tracking-[0.24em] text-fg-400">
    {children}
    <span className="h-px flex-1 bg-line" aria-hidden="true" />
  </div>
);

export default InsiderPanel;
