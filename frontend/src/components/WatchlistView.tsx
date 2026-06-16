import React, { useEffect, useState } from 'react';
import { Plus, X, RefreshCw, FileText } from 'lucide-react';
import {
  WatchlistRow,
  WatchlistFlag,
  getWatchlistDashboard,
  addToWatchlist,
  removeFromWatchlist,
} from '../api';
import { Badge, Button, Input, Spinner, cn } from './ui';

const pct = (v?: number | null) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(1)}%`;
const mult = (v?: number | null) =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : `${v.toFixed(1)}x`;

type Tone = 'neutral' | 'amber' | 'ledger' | 'azure' | 'crimson';

function flagTone(direction: string): Tone {
  if (direction === 'bull') return 'ledger';
  if (direction === 'bear') return 'crimson';
  if (direction === 'info') return 'azure';
  return 'amber';
}

function verdictTone(verdict?: string | null): Tone {
  if (verdict === 'cheap') return 'ledger';
  if (verdict === 'expensive') return 'crimson';
  return 'amber';
}

const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="min-w-0">
    <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-fg-400">{label}</div>
    <div className="truncate font-mono text-[13px] text-fg-100">{value}</div>
  </div>
);

const RowCard: React.FC<{ row: WatchlistRow; onRemove: (t: string) => void; busy: boolean }> = ({
  row,
  onRemove,
  busy,
}) => {
  const km = row.key_metrics || {};
  const v = row.valuation || {};
  return (
    <div className="rounded-lg border border-line bg-ink-850/80 p-4 shadow-panel">
      <div className="mb-3 flex items-center gap-3">
        <span className="font-display text-lg text-fg-100">{row.ticker}</span>
        {row.verdict && <Badge tone={verdictTone(row.verdict)}>{row.verdict}</Badge>}
        <span className="ml-auto font-mono text-sm text-fg-200">
          {row.price != null ? `$${row.price.toFixed(2)}` : ''}
        </span>
        <button
          type="button"
          aria-label={`Remove ${row.ticker}`}
          disabled={busy}
          onClick={() => onRemove(row.ticker)}
          className="rounded p-1 text-fg-400 hover:text-crimson-400 disabled:opacity-50"
        >
          <X size={14} />
        </button>
      </div>

      {!row.covered ? (
        <p className="font-mono text-[11px] text-fg-400">
          {row.flags[0]?.label || 'Limited structured coverage.'}
        </p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-3 gap-x-4 gap-y-2 sm:grid-cols-6">
            <Metric label="Net margin" value={pct(km.net_margin)} />
            <Metric label="Rev growth" value={pct(km.revenue_growth_yoy)} />
            <Metric label="FCF margin" value={pct(km.fcf_margin)} />
            <Metric label="ROIC" value={pct(km.roic_approx)} />
            <Metric label="P/E" value={mult(v.pe)} />
            <Metric label="Leverage" value={mult(km.net_debt_to_ebitda)} />
          </div>

          {v.dcf_intrinsic != null && (
            <p className="mb-3 font-mono text-[11px] text-fg-300">
              DCF intrinsic ${v.dcf_intrinsic.toFixed(0)}
              {v.dcf_low != null && v.dcf_high != null
                ? ` (${'$' + v.dcf_low.toFixed(0)}–${'$' + v.dcf_high.toFixed(0)})`
                : ''}
              {v.upside_vs_price != null && (
                <span className={cn('ml-2', v.upside_vs_price >= 0 ? 'text-ledger-400' : 'text-crimson-400')}>
                  {v.upside_vs_price >= 0 ? '+' : ''}
                  {(v.upside_vs_price * 100).toFixed(0)}% vs price
                </span>
              )}
            </p>
          )}

          {row.flags.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {row.flags.map((f: WatchlistFlag, i) => (
                <Badge key={i} tone={flagTone(f.direction)}>
                  {f.label}
                </Badge>
              ))}
            </div>
          )}

          {row.new_filing?.available && (
            <p className="mb-2 flex items-center gap-1.5 font-mono text-[11px] text-azure-400">
              <FileText size={12} /> New filing on EDGAR ({row.new_filing.edgar_date}) — ask about it to ingest.
            </p>
          )}

          {row.changed.length > 0 && (
            <div className="mb-1 border-t border-line-soft pt-2">
              <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-fg-400">Since last view</div>
              <ul className="mt-1 space-y-0.5">
                {row.changed.map((c, i) => (
                  <li key={i} className="font-mono text-[11px] text-fg-200">• {c}</li>
                ))}
              </ul>
            </div>
          )}

          {(row.holdings?.insider || row.holdings?.smart_money) && (
            <div className="mt-2 space-y-0.5 border-t border-line-soft pt-2">
              {row.holdings.smart_money && (
                <p className="font-mono text-[11px] text-fg-300">Smart money: {row.holdings.smart_money}</p>
              )}
              {row.holdings.insider && (
                <p className="font-mono text-[11px] text-fg-300">Insiders: {row.holdings.insider}</p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

const WatchlistView: React.FC = () => {
  const [rows, setRows] = useState<WatchlistRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await getWatchlistDashboard();
      setRows(d.rows);
    } catch {
      setError('Could not load the watchlist dashboard.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const add = async () => {
    const t = input.trim().toUpperCase();
    if (!t || busy) return;
    setBusy(true);
    try {
      await addToWatchlist(t);
      setInput('');
      await load();
    } catch {
      setError(`Could not add ${t}.`);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (t: string) => {
    setBusy(true);
    try {
      await removeFromWatchlist(t);
      setRows((r) => r.filter((x) => x.ticker !== t));
    } catch {
      setError(`Could not remove ${t}.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-line bg-ink-900/40">
      <div className="vr-rule-b flex items-center gap-2 px-5 py-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-300">Watchlist</h2>
        <span className="h-px flex-1 bg-line-soft" />
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && add()}
          placeholder="Add ticker…"
          className="h-8 w-32 uppercase"
          aria-label="Add a ticker to the watchlist"
        />
        <Button onClick={add} disabled={busy || !input.trim()} aria-label="Add">
          <Plus size={14} />
        </Button>
        <Button onClick={load} disabled={loading} variant="ghost" aria-label="Refresh">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </Button>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {error && <p className="font-mono text-[11px] text-crimson-400">{error}</p>}
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 font-mono text-[11px] uppercase tracking-[0.16em] text-fg-400">
            <Spinner /> Computing valuations…
          </div>
        ) : rows.length === 0 ? (
          <div className="py-16 text-center font-mono text-[11px] uppercase tracking-[0.16em] text-fg-400">
            Add tickers to track their valuation, signals, and filings.
          </div>
        ) : (
          rows.map((row) => <RowCard key={row.ticker} row={row} onRemove={remove} busy={busy} />)
        )}
      </div>
    </div>
  );
};

export default WatchlistView;
