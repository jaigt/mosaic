import React, { useState } from 'react';
import DOMPurify from 'dompurify';
import { FileText, Download, Maximize2, Info } from 'lucide-react';
import { Source } from '../api';
import { Card, Modal, cn } from './ui';

interface SourcePanelProps {
  sources: Source[];
  /** Index of the source tab to show — controlled by App so citation pills
   *  in the chat can focus a specific source. */
  activeIdx: number;
  onActiveIdxChange: (index: number) => void;
}

// Allowlist for SEC table HTML: structural table tags only, no scripts/styles/
// event handlers. Backstops the backend cleanup against stored XSS.
const TABLE_SANITIZE = {
  ALLOWED_TAGS: ['table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption', 'colgroup', 'col', 'span', 'br'],
  ALLOWED_ATTR: ['colspan', 'rowspan', 'scope'],
  FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'svg', 'img', 'link'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'style'],
};

function downloadSource(source: Source, index: number) {
  const blob = new Blob([JSON.stringify(source, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${source.ticker}-${source.year}-source-${index + 1}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

const SourcePanel: React.FC<SourcePanelProps> = ({ sources, activeIdx, onActiveIdxChange }) => {
  const [expanded, setExpanded] = useState(false);

  const hasRealSources = sources.length > 0;
  // Clamp defensively: a stale index from a previous result set must never
  // blank the panel.
  const safeIdx = hasRealSources ? Math.min(activeIdx, sources.length - 1) : 0;
  const activeSource = hasRealSources ? sources[safeIdx] : null;

  return (
    <Card elevated className="flex flex-1 flex-col bg-ink-900/70">
      <header className="vr-rule-b flex h-[62px] items-center justify-between pl-1 pr-3">
        <div className="flex h-full flex-1 items-center gap-1 overflow-x-auto">
          {hasRealSources ? (
            sources.map((s, i) => (
              <Tab
                key={i}
                label={`Exhibit ${i + 1}`}
                sublabel={`${s.ticker} ${s.year}`}
                active={i === safeIdx}
                onClick={() => onActiveIdxChange(i)}
              />
            ))
          ) : (
            <Tab label="Exhibits" active />
          )}
        </div>
        <div className="ml-3 flex shrink-0 items-center gap-1 text-fg-400">
          <button
            type="button"
            disabled={!activeSource}
            onClick={() => activeSource && downloadSource(activeSource, safeIdx)}
            className="grid h-7 w-7 place-items-center rounded text-fg-400 transition-colors hover:bg-white/5 hover:text-fg-200 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Download source"
            title="Download source as JSON"
          >
            <Download size={15} />
          </button>
          <button
            type="button"
            disabled={!activeSource}
            onClick={() => setExpanded(true)}
            className="grid h-7 w-7 place-items-center rounded text-fg-400 transition-colors hover:bg-white/5 hover:text-fg-200 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Expand source"
            title="Expand source"
          >
            <Maximize2 size={15} />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto bg-ink-950/50 text-fg-200">
        {!hasRealSources ? (
          <EmptyState />
        ) : activeSource ? (
          <div className="px-6 py-8 md:px-10">
            <SourceChunkView source={activeSource} index={safeIdx} total={sources.length} />
          </div>
        ) : null}
      </div>

      {activeSource && (
        <Modal
          open={expanded}
          onClose={() => setExpanded(false)}
          eyebrow="Reading view"
          title={`Exhibit ${safeIdx + 1} of ${sources.length}`}
          className="max-w-5xl"
        >
          <div className="max-h-[70vh] overflow-y-auto">
            <SourceChunkView source={activeSource} index={safeIdx} total={sources.length} compact />
          </div>
        </Modal>
      )}
    </Card>
  );
};

const EmptyState: React.FC = () => (
  <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center gap-6 p-10 text-center">
    {/* An empty paper tray: a faint stacked-sheets motif. */}
    <div className="relative h-20 w-16" aria-hidden="true">
      <div className="absolute inset-0 translate-x-2 translate-y-2 rounded-[2px] border border-line bg-ink-800/60" />
      <div className="absolute inset-0 translate-x-1 translate-y-1 rounded-[2px] border border-line bg-ink-800/80" />
      <div className="absolute inset-0 grid place-items-center rounded-[2px] border border-line-strong bg-ink-700">
        <FileText size={22} className="text-fg-400" />
      </div>
    </div>
    <div>
      <div className="font-display text-[20px] text-paper-100">The evidence tray is empty</div>
      <p className="mx-auto mt-2.5 max-w-xs font-serif text-[13.5px] italic leading-relaxed text-fg-400">
        When the analyst answers, the exact filing excerpts it cited are laid out here as paper exhibits.
      </p>
    </div>
  </div>
);

interface SourceChunkViewProps {
  source: Source;
  index: number;
  total: number;
  /** Compact = rendered inside the expand modal (header already shown). */
  compact?: boolean;
}

/* The exhibit renders as an ivory paper sheet inside the dark study — long-form
   filing text reads as ink-on-paper. Print palette comes from .vr-paper (CSS). */
const SourceChunkView: React.FC<SourceChunkViewProps> = ({ source, index, total, compact }) => (
  <div className={cn('vr-paper vr-rise mx-auto max-w-3xl', compact ? 'px-8 py-7' : 'px-10 py-9 md:px-12')}>
    {/* Exhibit header — typeset like a filing cover line. */}
    <div className="mb-7 border-b-2 border-double border-[color:var(--paper-line-strong)] pb-5">
      <div className="flex items-baseline justify-between gap-4 font-mono text-[10px] uppercase tracking-[0.22em] text-[color:var(--paper-muted)]">
        <span>United States · SEC · EDGAR</span>
        <span className="tabular-nums">Exhibit {index + 1} of {total}</span>
      </div>
      <div className="mt-4 flex items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="font-mono text-[12px] font-semibold tracking-[0.1em] text-[color:var(--paper-accent)]">
            {source.ticker} · {source.year}
            {source.quarter && source.quarter !== 'FY' ? ` ${source.quarter}` : ''} · {source.chunk_type === 'table' ? 'Financial Table' : 'Narrative'}
          </div>
          <h2 className="mt-1.5 font-display text-[26px] leading-[1.15] text-[color:var(--paper-ink-strong)]">
            {source.section || 'Filing excerpt'}
          </h2>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-1.5 text-[11.5px] text-[color:var(--paper-muted)]">
        <Info size={12} aria-hidden="true" />
        Relevance {(1 / (1 + source.score)).toFixed(4)}
      </div>
    </div>

    {source.chunk_type === 'table' ? (
      <div>
        {source.text_content && (
          <div className="mb-6 border-l-2 border-[color:var(--paper-accent)] pl-4">
            <div className="mb-1.5 font-mono text-[9.5px] font-semibold uppercase tracking-[0.2em] text-[color:var(--paper-accent)]">
              Analyst's note
            </div>
            <p className="font-serif text-[14px] italic leading-relaxed text-[color:var(--paper-ink)]">
              {source.text_content}
            </p>
          </div>
        )}
        {/* Rendered HTML table — sanitized; print styling lives in index.css */}
        <div
          className="sec-table-container"
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(source.raw_payload, TABLE_SANITIZE) }}
        />
      </div>
    ) : (
      <div className="whitespace-pre-wrap break-words font-serif text-[15.5px] leading-[1.85] text-[color:var(--paper-ink)]">
        {source.raw_payload}
      </div>
    )}

    {/* Foot rule, like the bottom of a certificate. */}
    <div className="mt-8 border-t border-[color:var(--paper-line)] pt-3 text-center font-mono text-[9px] uppercase tracking-[0.3em] text-[color:var(--paper-muted)]">
      Retrieved verbatim from the filing
    </div>
  </div>
);

const Tab: React.FC<{ label: string; sublabel?: string; active?: boolean; onClick?: () => void }> = ({
  label,
  sublabel,
  active,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={!onClick}
    className={cn(
      'flex h-full min-w-[120px] flex-col justify-center border-b-2 border-r border-r-line px-4 text-left transition-colors',
      active ? 'border-b-amber-400 bg-ink-950/40' : 'border-b-transparent hover:bg-white/[0.02]',
      onClick ? 'cursor-pointer' : 'cursor-default',
    )}
  >
    <span className={cn('text-[12px] font-semibold', active ? 'text-fg-100' : 'text-fg-400')}>{label}</span>
    {sublabel && <span className="font-mono text-[10px] text-fg-400/70">{sublabel}</span>}
  </button>
);

export default SourcePanel;
