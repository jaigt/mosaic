import React, { useEffect, useState } from 'react';
import DOMPurify from 'dompurify';
import { FileText, Download, Maximize2, Search, Info } from 'lucide-react';
import { Source } from '../api';
import { Badge, Card, cn } from './ui';

interface SourcePanelProps {
  sources: Source[];
}

// Allowlist for SEC table HTML: structural table tags only, no scripts/styles/
// event handlers. Backstops the backend cleanup against stored XSS.
const TABLE_SANITIZE = {
  ALLOWED_TAGS: ['table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption', 'colgroup', 'col', 'span', 'br'],
  ALLOWED_ATTR: ['colspan', 'rowspan', 'scope'],
  FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'svg', 'img', 'link'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'style'],
};

const SourcePanel: React.FC<SourcePanelProps> = ({ sources }) => {
  const [activeIdx, setActiveIdx] = useState(0);

  // Reset the active tab whenever a new result set arrives, so a previously
  // selected (now out-of-range) index can't blank the panel.
  useEffect(() => { setActiveIdx(0); }, [sources]);

  const hasRealSources = sources.length > 0;
  const activeSource = hasRealSources ? sources[activeIdx] : null;

  return (
    <Card elevated className="flex flex-1 flex-col bg-ink-900/70">
      <header className="flex h-12 items-center justify-between border-b border-line pl-1 pr-3">
        <div className="flex h-full flex-1 items-center gap-1 overflow-x-auto">
          {hasRealSources ? (
            sources.map((s, i) => (
              <Tab
                key={i}
                label={`Source ${i + 1}`}
                sublabel={`${s.ticker} ${s.year}`}
                active={i === activeIdx}
                onClick={() => setActiveIdx(i)}
              />
            ))
          ) : (
            <Tab label="Source Viewer" active />
          )}
        </div>
        <div className="ml-3 flex shrink-0 items-center gap-1 text-fg-400">
          {[Search, Download, Maximize2].map((Icon, i) => (
            <button
              key={i}
              type="button"
              className="grid h-7 w-7 place-items-center rounded text-fg-400 transition-colors hover:bg-white/5 hover:text-fg-200"
              aria-label={['Search source', 'Download source', 'Expand source'][i]}
            >
              <Icon size={15} />
            </button>
          ))}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto bg-ink-950/40 text-fg-200">
        {!hasRealSources ? (
          <EmptyState />
        ) : activeSource ? (
          <SourceChunkView source={activeSource} index={activeIdx} total={sources.length} />
        ) : null}
      </div>
    </Card>
  );
};

const EmptyState: React.FC = () => (
  <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center gap-5 p-10 text-center">
    <div className="grid h-16 w-16 place-items-center rounded-xl border border-line-strong bg-ink-800 text-fg-400">
      <FileText size={30} />
    </div>
    <div>
      <div className="font-display text-lg font-semibold text-paper-100">No sources selected</div>
      <p className="mx-auto mt-2 max-w-xs text-[13px] leading-relaxed text-fg-400">
        Retrieved SEC excerpts and tables will appear here for verification, side by side with the analyst's answer.
      </p>
    </div>
  </div>
);

interface SourceChunkViewProps {
  source: Source;
  index: number;
  total: number;
}

const SourceChunkView: React.FC<SourceChunkViewProps> = ({ source, index, total }) => (
  <div className="vr-rise mx-auto max-w-3xl p-10">
    <div className="mb-8 flex items-start justify-between gap-4 border-b border-line pb-6">
      <div className="min-w-0">
        <div className="mb-2 flex items-center gap-2">
          <Badge tone="amber" mono>{source.ticker}</Badge>
          <span className="font-mono text-[12px] uppercase tracking-wider text-fg-400">
            {source.year}{source.quarter && source.quarter !== 'FY' ? ` ${source.quarter}` : ''} · {source.chunk_type}
          </span>
        </div>
        <h2 className="font-display text-2xl font-semibold leading-tight text-paper-100">{source.section}</h2>
        <div className="mt-2.5 flex items-center gap-1.5 text-[12px] text-fg-400">
          <Info size={13} />
          Relevance score {(1 / (1 + source.score)).toFixed(4)}
        </div>
      </div>
      <Badge tone="neutral" mono className="shrink-0">
        Doc {index + 1} / {total}
      </Badge>
    </div>

    {source.chunk_type === 'table' ? (
      <div>
        {source.text_content && (
          <div className="mb-6 rounded-md border-l-2 border-amber-500 bg-amber-400/[0.07] px-5 py-4">
            <div className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-300">
              Contextual Summary
            </div>
            <p className="text-[14px] leading-relaxed text-fg-200">{source.text_content}</p>
          </div>
        )}
        {/* Rendered HTML table — sanitized; styling lives in index.css */}
        <div
          className="sec-table-container"
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(source.raw_payload, TABLE_SANITIZE) }}
        />
      </div>
    ) : (
      <div className="whitespace-pre-wrap break-words font-serif text-[16.5px] leading-[1.85] text-fg-200">
        {source.raw_payload}
      </div>
    )}
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
