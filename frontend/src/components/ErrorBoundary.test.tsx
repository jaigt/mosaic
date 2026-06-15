import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ErrorBoundary from './ErrorBoundary';

const Boom: React.FC = () => {
  throw new Error('kaboom');
};

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // React logs caught errors to console.error; silence it for clean output.
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <p>all good</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText('all good')).toBeInTheDocument();
  });

  it('renders the in-theme fallback when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/something came off the rails/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reload the study/i })).toBeInTheDocument();
  });
});
