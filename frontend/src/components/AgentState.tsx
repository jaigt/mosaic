import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Spinner, cn } from './ui';

export interface AgentStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'completed';
}

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
          {steps.map((step) => (
            <li
              key={step.id}
              className={cn(
                'flex items-center gap-3 py-1.5 text-[13px]',
                step.status === 'pending' ? 'opacity-50' : 'opacity-100',
              )}
            >
              <span className="grid h-4 w-4 place-items-center">
                {step.status === 'completed' && <span className="h-2 w-2 rounded-full bg-ledger-400" />}
                {step.status === 'running' && <Spinner size={13} className="text-amber-400" />}
                {step.status === 'pending' && (
                  <span className="h-2 w-2 rounded-full border border-fg-400" />
                )}
              </span>
              <span className={cn(step.status === 'completed' ? 'text-fg-300' : 'text-fg-200')}>
                {step.label}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
};

export default AgentState;
