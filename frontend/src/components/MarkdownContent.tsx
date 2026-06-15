import React from 'react';
import ReactMarkdown, { Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

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

interface MarkdownContentProps {
  children: string;
}

/** Renders assistant markdown. Split into its own module so react-markdown +
 *  remark-gfm land in a lazily-loaded async chunk (see Message.tsx). */
const MarkdownContent: React.FC<MarkdownContentProps> = ({ children }) => (
  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
    {children}
  </ReactMarkdown>
);

export default MarkdownContent;
