import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AgentState, { AgentStep } from './AgentState';

describe('AgentState', () => {
  it('renders an ingest-kind step distinctly from a plain status step', () => {
    const steps: AgentStep[] = [
      { id: '1', label: 'Searching filings', status: 'completed', kind: 'status' },
      { id: '2', label: 'Fetching AAPL 10-K from EDGAR', status: 'running', kind: 'ingest' },
    ];
    render(<AgentState steps={steps} isActive={true} />);

    const statusItem = screen.getByText('Searching filings').closest('li');
    const ingestItem = screen.getByText('Fetching AAPL 10-K from EDGAR').closest('li');

    expect(statusItem).toHaveAttribute('data-kind', 'status');
    expect(ingestItem).toHaveAttribute('data-kind', 'ingest');
    // The agent action gets amber emphasis; the plain status step does not.
    expect(screen.getByText('Fetching AAPL 10-K from EDGAR').className).toContain('text-amber-200');
  });

  it('renders ingest_failed as a warning, not a success', () => {
    const steps: AgentStep[] = [
      { id: '1', label: 'Could not fetch filing', status: 'completed', kind: 'ingest_failed' },
    ];
    render(<AgentState steps={steps} isActive={false} />);
    const label = screen.getByText('Could not fetch filing');
    expect(label.className).toContain('text-crimson-400');
    expect(label.closest('li')).toHaveAttribute('data-kind', 'ingest_failed');
  });
});
