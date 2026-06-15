import React, { useEffect, useState } from 'react';
import { FileText, X } from 'lucide-react';
import { listFilings, FilingInfo } from '../api';
import { cn } from './ui';
import InsiderPanel from './InsiderPanel';
import SmartMoneyPanel from './SmartMoneyPanel';

interface SidebarProps {
  activeFiling: FilingInfo | null;
  /** Ticker the conversation is currently about — drives the insider /
   *  smart-money panels even when no filing is explicitly focused. */
  activeTicker: string | null;
  onSelectFiling: (filing: FilingInfo) => void;
  /** Below the tablet breakpoint the sidebar renders as a toggleable overlay
   *  drawer instead of a fixed column. */
  isMobile?: boolean;
  drawerOpen?: boolean;
  onCloseDrawer?: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({
  activeFiling,
  activeTicker,
  onSelectFiling,
  isMobile = false,
  drawerOpen = false,
  onCloseDrawer,
}) => {
  const [filings, setFilings] = useState<FilingInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchFilings = async () => {
    try {
      const data = await listFilings();
      setFilings(data.filings);
    } catch (err) {
      console.error('Failed to fetch filings', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFilings();
    // Poll every 30 seconds for updates (the corpus fills as the agent
    // auto-ingests companies users ask about).
    const interval = setInterval(fetchFilings, 30000);
    return () => clearInterval(interval);
  }, []);

  const totalChunks = filings.reduce((n, f) => n + f.chunks, 0);

  // On mobile the sidebar is unmounted when the drawer is closed, so its
  // 30-second poll doesn't run off-screen.
  if (isMobile && !drawerOpen) return null;

  return (
    <aside
      className={cn(
        'flex flex-col overflow-hidden border-line bg-ink-900/55 backdrop-blur-sm',
        isMobile
          ? 'fixed inset-y-0 left-0 z-50 w-[min(86vw,var(--sidebar-width))] border-r shadow-panel'
          : 'w-[var(--sidebar-width)] border-r',
      )}
      aria-label="Filing ledger navigation"
    >
      {/* Masthead: engraved seal + wordmark, certificate double-rule below. */}
      <div className="vr-rule-b px-6 pb-5 pt-7">
        <div className="flex items-center gap-3.5">
          <div
            aria-hidden="true"
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-amber-400/50 shadow-[inset_0_0_0_3px_var(--color-ink-900),inset_0_0_0_4px_rgba(210,173,82,0.35)] bg-gradient-to-b from-ink-700 to-ink-850"
          >
            <span className="font-display text-[19px] leading-none text-amber-300 [text-shadow:0_1px_0_rgba(0,0,0,0.6)]">M</span>
          </div>
          <div className="min-w-0 flex-1 leading-none">
            <h1 className="font-display text-[21px] tracking-[0.01em] text-paper-100">Mosaic</h1>
            <div className="mt-1.5 font-mono text-[9.5px] uppercase tracking-[0.28em] text-fg-400">
              Primary Sources
            </div>
          </div>
          {isMobile && (
            <button
              type="button"
              onClick={onCloseDrawer}
              aria-label="Close menu"
              className="-mr-1 grid h-8 w-8 shrink-0 place-items-center rounded-md text-fg-400 transition-colors hover:bg-white/5 hover:text-fg-100"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-5 pt-5" aria-label="Ingested filings">
        <SectionLabel>On the books</SectionLabel>
        {loading && filings.length === 0 ? (
          <div className="px-1 py-2 font-serif text-[13px] italic text-fg-400">Opening the ledger…</div>
        ) : filings.length === 0 ? (
          <div className="px-1 py-2 font-serif text-[13px] italic leading-relaxed text-fg-400">
            No entries yet. Ask about any company and its filings appear here.
          </div>
        ) : (
          <ul className="mt-1">
            {filings.map((f, idx) => {
              const taskId = `${f.ticker}-${f.document_type}-${f.filing_year}`;
              const isActive =
                activeFiling?.ticker === f.ticker &&
                activeFiling?.filing_year === f.filing_year &&
                activeFiling?.document_type === f.document_type;

              return (
                <li key={taskId} className="vr-rise" style={{ animationDelay: `${idx * 45}ms` }}>
                  <div
                    onClick={() => onSelectFiling(f)}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isActive}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelectFiling(f);
                      }
                    }}
                    className={cn(
                      'group -mx-2 mb-0.5 flex cursor-pointer items-center rounded-md border-l-2 px-3 py-2.5 transition-colors',
                      isActive
                        ? 'border-amber-400 bg-amber-400/[0.07]'
                        : 'border-transparent hover:bg-paper-100/[0.03]',
                    )}
                  >
                    <span
                      className={cn(
                        'font-mono text-[13.5px] font-semibold tracking-[0.04em]',
                        isActive ? 'text-amber-300' : 'text-fg-100',
                      )}
                    >
                      {f.ticker}
                    </span>
                    <span className="vr-leader" aria-hidden="true" />
                    <span className="font-mono text-[11px] tabular-nums text-fg-300">
                      {f.filing_year} {f.document_type}
                    </span>
                  </div>
                  <div className="-mx-2 px-3 pb-2 pt-0">
                    <span className="flex items-center gap-1.5 pl-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-fg-400/80">
                      <FileText size={10} aria-hidden="true" />
                      {f.chunks} excerpts indexed
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </nav>

      {/* Insider activity + smart-money holders for whatever the conversation
       *  is about (or a focused filing's issuer); a hint otherwise. */}
      {activeTicker ? (
        <>
          <div className="vr-rule-t shrink-0">
            <InsiderPanel ticker={activeTicker} />
          </div>
          <div className="vr-rule-t shrink-0">
            <SmartMoneyPanel ticker={activeTicker} />
          </div>
        </>
      ) : (
        <div className="vr-rule-t shrink-0 px-5 py-3 font-serif text-[12px] italic leading-relaxed text-fg-400">
          Select a filing or ask about a company to see its insider activity.
        </div>
      )}

      {/* Ledger footer: a closing line, like the foot of a statement. */}
      <div className="vr-rule-t px-6 py-4">
        <div className="flex items-center justify-between font-mono text-[9.5px] uppercase tracking-[0.22em] text-fg-400">
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-ledger-400 shadow-[0_0_8px_1px_rgba(92,196,136,0.5)]" aria-hidden="true" />
            EDGAR&nbsp;Live
          </span>
          <span className="tabular-nums">{totalChunks.toLocaleString()} entries</span>
        </div>
      </div>
    </aside>
  );
};

const SectionLabel: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <div className={cn('flex items-center gap-2.5 pb-2.5 font-mono text-[9.5px] font-semibold uppercase tracking-[0.24em] text-fg-400', className)}>
    {children}
    <span className="h-px flex-1 bg-line" aria-hidden="true" />
  </div>
);

export default Sidebar;
