import React, { useMemo, useState } from 'react';
import { ExternalLink, ShieldCheck, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import FinancialChart from './Visualizer/FinancialChart';
import { Source, VerificationResult } from '../api';
import { Badge, cn } from './ui';

interface Citation {
  id: string;
  label: string;
}

interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  chartData?: { name: string; value: number }[];
  citations?: Citation[];
  sources?: Source[];
  isStreaming?: boolean;
  /** Critic-pass result auditing the answer against its sources. Only rendered
   *  on finished (non-streaming) assistant messages. */
  verification?: VerificationResult;
  /** Clicking a source pill focuses that source in the SourcePanel.
   *  Kept as a (sources, index) signature so the same stable handler can be
   *  shared across messages without breaking React.memo. */
  onCitationClick?: (sources: Source[], index: number) => void;
}

// Trust signal shown under a finished answer once the critic pass returns.
const VerificationBadge: React.FC<{ verification: VerificationResult }> = ({ verification }) => {
  const [expanded, setExpanded] = useState(false);

  if (verification.status === 'supported') {
    return (
      <div className="mt-3">
        <Badge tone="ledger" pill>
          <ShieldCheck size={11} aria-hidden="true" />
          Verified against sources
        </Badge>
      </div>
    );
  }

  if (verification.status === 'caveats') {
    const count = verification.issues.length;
    const hasIssues = count > 0;
    return (
      <div className="mt-3">
        <button
          type="button"
          onClick={hasIssues ? () => setExpanded((v) => !v) : undefined}
          aria-expanded={hasIssues ? expanded : undefined}
          className={cn(
            'rounded-full outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60',
            hasIssues ? 'cursor-pointer transition-transform hover:scale-[1.04]' : 'cursor-default',
          )}
        >
          <Badge tone="amber" pill>
            <AlertTriangle size={11} aria-hidden="true" />
            {count} point{count === 1 ? '' : 's'} to verify
            {hasIssues &&
              (expanded ? (
                <ChevronDown size={11} aria-hidden="true" />
              ) : (
                <ChevronRight size={11} aria-hidden="true" />
              ))}
          </Badge>
        </button>
        {hasIssues && expanded && (
          <ul className="mt-2 list-disc rounded-md border border-amber-400/25 bg-amber-400/[0.06] py-2 pl-7 pr-3 text-[12.5px] leading-relaxed text-amber-200/90 marker:text-amber-400/70">
            {verification.issues.map((issue, i) => (
              <li key={i} className="mb-1 last:mb-0">
                {issue}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  // unknown — keep it muted and unobtrusive.
  return (
    <div className="mt-3 font-mono text-[10px] uppercase tracking-[0.18em] text-fg-400/70">
      Not verified
    </div>
  );
};

// Hoisted to module scope: this object captures nothing dynamic, so re-creating
// it on every render needlessly forces react-markdown to re-render its subtree.
// Styling is class-based so it inherits the shared token palette.
// react-markdown passes a `node` prop that React doesn't recognize on DOM
// elements; strip it before spreading the rest onto the host element.
const omitNode = <T extends { node?: unknown }>(props: T) => {
  const rest = { ...props };
  delete rest.node;
  return rest;
};

const markdownComponents: Components = {
  a: (props) => (
    <a {...omitNode(props)} className="text-amber-300 underline-offset-2 hover:underline" target="_blank" rel="noreferrer" />
  ),
  p: (props) => <p {...omitNode(props)} className="mb-3 last:mb-0" />,
  ul: (props) => <ul {...omitNode(props)} className="mb-3 list-disc pl-5 marker:text-fg-400" />,
  ol: (props) => <ol {...omitNode(props)} className="mb-3 list-decimal pl-5 marker:text-fg-400" />,
  li: (props) => <li {...omitNode(props)} className="mb-1" />,
  code: (props) => (
    <code {...omitNode(props)} className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[0.88em] text-amber-200" />
  ),
  table: (props) => (
    <div className="mb-4 overflow-x-auto rounded-md border border-line">
      <table {...omitNode(props)} className="w-full border-collapse font-mono text-[13px] tabular-nums" />
    </div>
  ),
  th: (props) => (
    <th {...omitNode(props)} className="border-b border-line bg-white/[0.03] px-3 py-2 text-left font-semibold text-fg-300" />
  ),
  td: (props) => (
    <td {...omitNode(props)} className="border-b border-line-soft px-3 py-2" />
  ),
};

const Message: React.FC<MessageProps> = ({ role, content, chartData, sources, isStreaming, verification, onCitationClick }) => {
  const isUser = role === 'user';

  // Extract chart data from content if it contains <chart> tags.
  // Memoized on `content` so the (potentially expensive) regex + JSON.parse
  // only runs when the text actually changes.
  const { cleanContent, inlineChartData, inlineChartTitle } = useMemo(() => {
    let cleanContent = content;
    let inlineChartData = chartData;
    let inlineChartTitle = 'Analysis';

    if (!isUser && content.includes('<chart>')) {
      try {
        const chartMatch = content.match(/<chart>([\s\S]*?)<\/chart>/);
        if (chartMatch) {
          const parsed = JSON.parse(chartMatch[1]);
          inlineChartData = parsed.data;
          if (parsed.title) inlineChartTitle = parsed.title;
          cleanContent = content.replace(/<chart>[\s\S]*?<\/chart>/, '').trim();
        }
      } catch (e) {
        console.error('Failed to parse inline chart data', e);
      }
    }

    return { cleanContent, inlineChartData, inlineChartTitle };
  }, [content, chartData, isUser]);

  return (
    <div className="vr-rise flex max-w-full items-start gap-4">
      <div
        className={cn(
          'grid h-8 w-8 shrink-0 place-items-center rounded-full border',
          isUser
            ? 'border-line-strong bg-ink-700'
            : 'border-amber-400/45 bg-gradient-to-b from-ink-700 to-ink-850 shadow-[inset_0_0_0_2px_var(--color-ink-900),inset_0_0_0_3px_rgba(210,173,82,0.3)]',
        )}
        aria-hidden="true"
      >
        <span
          className={cn(
            isUser
              ? 'font-mono text-[9px] font-semibold uppercase tracking-widest text-fg-300'
              : 'font-display text-[14px] leading-none text-amber-300',
          )}
        >
          {isUser ? 'YOU' : 'V'}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-baseline gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400">
            {isUser ? 'Inquiry' : 'The Analyst'}
          </span>
          <span className="h-px flex-1 bg-line-soft" aria-hidden="true" />
        </div>
        <div
          className={cn(
            'overflow-hidden text-[14.5px] leading-[1.75] text-fg-100 [overflow-wrap:anywhere]',
            isUser
              ? 'rounded-md border border-line bg-ink-800/50 px-4 py-3 font-serif text-[15px] text-fg-200'
              : 'rounded-md border border-line border-l-2 border-l-amber-500/60 bg-ink-800/70 px-5 py-4',
          )}
        >
          {cleanContent ? (
            <div className="markdown-content">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {cleanContent}
              </ReactMarkdown>
            </div>
          ) : (
            isStreaming ? '' : <span className="italic text-fg-400">No response</span>
          )}
          {isStreaming && (
            <span
              className="ml-1 inline-block h-[14px] w-[2px] align-middle bg-amber-400"
              style={{ animation: 'blink 1s step-end infinite' }}
            />
          )}
        </div>

        {inlineChartData && inlineChartData.length > 0 && (
          <div className="mt-4">
            <FinancialChart title={inlineChartTitle} data={inlineChartData} />
          </div>
        )}

        {sources && sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {sources.map((s, i) => (
              <button
                key={i}
                type="button"
                onClick={onCitationClick ? () => onCitationClick(sources, i) : undefined}
                aria-label={`Show source ${i + 1}: ${s.ticker} ${s.year}`}
                title="Show in source panel"
                className={cn(
                  'rounded-full outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60',
                  onCitationClick ? 'cursor-pointer transition-transform hover:scale-[1.04]' : 'cursor-default',
                )}
              >
                <Badge tone="ledger" pill mono>
                  <ExternalLink size={10} aria-hidden="true" />
                  [{i + 1}] {s.ticker} {s.year} {s.section || s.chunk_type}
                </Badge>
              </button>
            ))}
          </div>
        )}

        {!isUser && !isStreaming && verification && (
          <VerificationBadge verification={verification} />
        )}
      </div>
    </div>
  );
};

export default React.memo(Message);
