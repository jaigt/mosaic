import React, { useEffect, useState } from 'react';
import { LayoutDashboard, History, Settings, LogOut, Database, FileText, RefreshCw } from 'lucide-react';
import { listFilings, FilingInfo, ingestFiling, getIngestStatus } from '../api';
import { Button, Spinner, cn } from './ui';

interface SidebarProps {
  onIngestClick: () => void;
  activeFiling: FilingInfo | null;
  onSelectFiling: (filing: FilingInfo) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ onIngestClick, activeFiling, onSelectFiling }) => {
  const [filings, setFilings] = useState<FilingInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [reingesting, setReingesting] = useState<string | null>(null); // filing_id as ticker-year-type

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
    // Poll every 30 seconds for updates
    const interval = setInterval(fetchFilings, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleReingest = async (e: React.MouseEvent, f: FilingInfo) => {
    e.stopPropagation();
    const taskId = `${f.ticker}-${f.document_type}-${f.filing_year}`;
    if (reingesting === taskId) return;

    try {
      const resp = await ingestFiling(f.ticker, f.document_type, f.filing_year);
      setReingesting(resp.task_id);

      // Start polling
      const poll = async () => {
        try {
          const statusResp = await getIngestStatus(resp.task_id);
          if (statusResp.status === 'running') {
            setTimeout(poll, 2000);
          } else {
            setReingesting(null);
            fetchFilings();
          }
        } catch (err) {
          console.error('Polling failed', err);
          setReingesting(null);
        }
      };
      setTimeout(poll, 2000);
    } catch (err) {
      alert(`Re-ingestion failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <aside className="flex w-[var(--sidebar-width)] flex-col overflow-hidden border-r border-line bg-ink-900/60 py-6 backdrop-blur-sm">
      <div className="flex items-center gap-3 px-6 pb-6">
        <div className="grid h-9 w-9 place-items-center rounded-md bg-gradient-to-br from-amber-300 to-amber-500 shadow-[0_4px_16px_-4px_rgba(232,168,56,0.55)]">
          <Database size={18} className="text-ink-950" />
        </div>
        <div className="leading-none">
          <h1 className="font-display text-[19px] font-semibold tracking-tight text-paper-100">ValueRAG</h1>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400">Filing Analyst</span>
        </div>
      </div>

      <div className="px-4 pb-5">
        <Button variant="primary" size="lg" onClick={onIngestClick} className="w-full">
          <Database size={16} />
          Ingest New Filing
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto px-4">
        <SectionLabel>Workspace</SectionLabel>
        <NavItem icon={<LayoutDashboard size={17} />} label="Analysis Lab" active />
        <NavItem icon={<History size={17} />} label="Query History" />

        <SectionLabel className="pt-6">Ingested Filings</SectionLabel>
        {loading && filings.length === 0 ? (
          <div className="px-3 py-2 text-xs italic text-fg-400">Loading filings...</div>
        ) : filings.length === 0 ? (
          <div className="px-3 py-2 text-xs text-fg-400/70">No filings ingested yet.</div>
        ) : (
          filings.map((f) => {
            const taskId = `${f.ticker}-${f.document_type}-${f.filing_year}`;
            const isActive =
              activeFiling?.ticker === f.ticker &&
              activeFiling?.filing_year === f.filing_year &&
              activeFiling?.document_type === f.document_type;
            const isReingesting = reingesting === taskId;

            return (
              <div
                key={taskId}
                onClick={() => onSelectFiling(f)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectFiling(f);
                  }
                }}
                className={cn(
                  'group mb-0.5 flex cursor-pointer items-center gap-2.5 rounded-md border px-3 py-2.5 transition-colors',
                  isActive
                    ? 'border-amber-400/30 bg-amber-400/10'
                    : 'border-transparent hover:bg-white/[0.03]',
                )}
              >
                <FileText
                  size={15}
                  className={cn('shrink-0', isActive ? 'text-amber-400' : 'text-fg-400')}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-[13px] font-semibold tracking-wide text-fg-100">{f.ticker}</div>
                  <div className="truncate text-[11px] text-fg-400">
                    {f.filing_year} {f.document_type} · {f.chunks} chunks
                  </div>
                </div>

                <button
                  type="button"
                  onClick={(e) => handleReingest(e, f)}
                  disabled={isReingesting}
                  title="Re-ingest / refresh"
                  aria-label={`Re-ingest ${f.ticker} ${f.filing_year} ${f.document_type}`}
                  className={cn(
                    'grid h-7 w-7 shrink-0 place-items-center rounded text-fg-400 transition-colors',
                    isReingesting
                      ? 'cursor-not-allowed'
                      : 'opacity-0 hover:bg-white/10 hover:text-fg-100 focus-visible:opacity-100 group-hover:opacity-100',
                  )}
                >
                  {isReingesting ? <Spinner size={14} /> : <RefreshCw size={14} />}
                </button>

                {isActive && <span className="h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden="true" />}
              </div>
            );
          })
        )}
      </nav>

      <div className="mt-auto border-t border-line px-4 pt-4">
        <NavItem icon={<Settings size={17} />} label="Settings" />
        <NavItem icon={<LogOut size={17} />} label="Sign Out" />
      </div>
    </aside>
  );
};

const SectionLabel: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <div className={cn('px-3 pb-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-fg-400', className)}>
    {children}
  </div>
);

interface NavItemProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
}

const NavItem: React.FC<NavItemProps> = ({ icon, label, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={cn(
      'mb-1 flex w-full items-center gap-3 rounded-md border-l-2 px-3 py-2.5 text-left text-sm transition-colors',
      active
        ? 'border-amber-400 bg-amber-400/10 font-semibold text-paper-100'
        : 'border-transparent font-medium text-fg-300 hover:bg-white/[0.03] hover:text-fg-100',
    )}
  >
    <span className={active ? 'text-amber-400' : 'text-fg-400'}>{icon}</span>
    {label}
  </button>
);

export default Sidebar;
