import React, { useMemo } from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

// react-markdown passes a `node` prop that React doesn't recognize on DOM
// elements; strip it before spreading the rest onto the host element.
const omitNode = <T extends { node?: unknown }>(props: T) => {
  const rest = { ...props };
  delete rest.node;
  return rest;
};

/** Turn inline `[1]`/`[2]` markers inside rendered text into clickable chips
 *  that focus the matching source. Walks the (possibly mixed) children and
 *  splits only string nodes, leaving bold/code/etc. untouched. */
function linkifyCitations(
  children: React.ReactNode,
  onCitation: (index: number) => void,
): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child !== 'string') return child;
    const parts = child.split(/(\[\d+\])/g);
    if (parts.length === 1) return child;
    return parts.map((part, i) => {
      const m = part.match(/^\[(\d+)\]$/);
      if (!m) return part;
      const index = parseInt(m[1], 10) - 1; // [1] → source index 0
      return (
        <button
          key={i}
          type="button"
          onClick={() => onCitation(index)}
          aria-label={`Show source ${m[1]}`}
          className="mx-0.5 rounded bg-amber-400/15 px-1 align-baseline font-mono text-[0.78em] text-amber-300 transition-colors hover:bg-amber-400/30"
        >
          {part}
        </button>
      );
    });
  });
}

interface MarkdownContentProps {
  children: string;
  /** When provided, inline [n] markers become clickable (focus source n-1). */
  onCitation?: (index: number) => void;
}

/** Renders assistant markdown. Split into its own module so react-markdown +
 *  remark-gfm land in a lazily-loaded async chunk (see Message.tsx). */
const MarkdownContent: React.FC<MarkdownContentProps> = ({ children, onCitation }) => {
  const components = useMemo<Components>(() => {
    // Apply citation linkification to the text-bearing block elements.
    const cite = (kids: React.ReactNode) => (onCitation ? linkifyCitations(kids, onCitation) : kids);
    return {
      a: (props) => (
        <a {...omitNode(props)} className="text-amber-300 underline-offset-2 hover:underline" target="_blank" rel="noreferrer" />
      ),
      p: ({ children: kids, ...props }) => <p {...omitNode(props)} className="mb-3 last:mb-0">{cite(kids)}</p>,
      ul: (props) => <ul {...omitNode(props)} className="mb-3 list-disc pl-5 marker:text-fg-400" />,
      ol: (props) => <ol {...omitNode(props)} className="mb-3 list-decimal pl-5 marker:text-fg-400" />,
      li: ({ children: kids, ...props }) => <li {...omitNode(props)} className="mb-1">{cite(kids)}</li>,
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
      td: ({ children: kids, ...props }) => <td {...omitNode(props)} className="border-b border-line-soft px-3 py-2">{cite(kids)}</td>,
    };
  }, [onCitation]);

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  );
};

export default MarkdownContent;
