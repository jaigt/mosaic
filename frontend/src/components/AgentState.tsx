import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Download, FileSearch, AlertTriangle } from 'lucide-react';
import { Spinner, cn } from './ui';

/** `status` = a plain progress line; the others are autonomous agent actions
 *  (fetching a missing filing from SEC EDGAR) and get amber emphasis. */
export type AgentStepKind = 'status' | 'ingest' | 'retry_search' | 'ingest_failed';

export interface AgentStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'completed';
  kind?: AgentStepKind;
}

// Agent-action kinds render with an icon + amber emphasis so they read as
// distinct from the subtle status dots.
const AGENT_KINDS = new Set<AgentStepKind>(['ingest', 'retry_search', 'ingest_failed']);

interface AgentStateProps {
  steps: AgentStep[];
  isActive: boolean;
}

const AgentState: React.FC<AgentStateProps> = ({ steps, isActive }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!isActive && steps.length === 0) return null;

  return (
    <div className="vr-rise overflow-hidden rounded-lg border border-line bg-ink-800/70">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        className="flex w-full items-center justify-between bg-white/[0.02] px-4 py-3 text-left transition-colors hover:bg-white/[0.04]"
      >
        <div className="flex items-center gap-2.5">
          {isActive ? (
            <Spinner size={15} className="text-amber-400" label="Analyst working" />
          ) : (
            <span className="h-2 w-2 rounded-full bg-ledger-400" />
          )}
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-fg-200">
            {isActive ? 'Working the filings…' : 'Analysis complete'}
          </span>
        </div>
        {isExpanded ? (
          <ChevronDown size={15} className="text-fg-400" />
        ) : (
          <ChevronRight size={15} className="text-fg-400" />
        )}
      </button>

      {isExpanded && steps.length > 0 && (
        <ol className="border-t border-line px-4 py-3">
          {steps.map((step) => {
            const isAgentAction = step.kind ? AGENT_KINDS.has(step.kind) : false;
            const isFailed = step.kind === 'ingest_failed';
            return (
              <li
                key={step.id}
                data-kind={step.kind ?? 'status'}
                className={cn(
                  'flex items-center gap-3 py-1.5 text-[13px]',
                  step.status === 'pending' ? 'opacity-50' : 'opacity-100',
                )}
              >
                <span className="grid h-4 w-4 place-items-center">
                  {isFailed ? (
                    <AlertTriangle size={13} className="text-crimson-400" aria-hidden="true" />
                  ) : step.status === 'running' ? (
                    <Spinner size={13} className="text-amber-400" />
                  ) : isAgentAction ? (
                    // Completed agent action: keep the amber EDGAR/fetch icon.
                    step.kind === 'ingest' ? (
                      <Download size={13} className="text-amber-400" aria-hidden="true" />
                    ) : (
                      <FileSearch size={13} className="text-amber-400" aria-hidden="true" />
                    )
                  ) : step.status === 'completed' ? (
                    <span className="h-2 w-2 rounded-full bg-ledger-400" />
                  ) : (
                    <span className="h-2 w-2 rounded-full border border-fg-400" />
                  )}
                </span>
                <span
                  className={cn(
                    isFailed
                      ? 'text-crimson-400'
                      : isAgentAction
                        ? 'font-medium text-amber-200'
                        : step.status === 'completed'
                          ? 'text-fg-300'
                          : 'text-fg-200',
                  )}
                >
                  {step.label}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
};

export default AgentState;
