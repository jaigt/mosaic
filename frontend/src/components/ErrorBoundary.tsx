import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from './ui';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * App-root error boundary. Catches render-time errors anywhere below it and
 * shows an in-theme fallback (engraved-ledger styling) with a reload affordance
 * instead of unmounting to a blank screen.
 */
class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('Unhandled render error', error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          className="flex h-screen w-screen flex-col items-center justify-center gap-6 p-8 text-center"
        >
          <div
            aria-hidden="true"
            className="grid h-14 w-14 place-items-center rounded-full border border-crimson-500/50 bg-gradient-to-b from-ink-700 to-ink-850 text-crimson-400 shadow-[inset_0_0_0_3px_var(--color-ink-900)]"
          >
            <AlertTriangle size={24} />
          </div>
          <div className="max-w-md">
            <div className="font-mono text-[10px] uppercase tracking-[0.32em] text-crimson-400/90">
              The study went dark
            </div>
            <h1 className="mt-3 font-display text-[clamp(24px,3vw,32px)] leading-tight text-paper-100">
              Something came off the rails.
            </h1>
            <p className="mt-3 font-serif text-[14.5px] leading-relaxed text-fg-300">
              An unexpected error interrupted the page. Reloading usually sets the
              ledger straight.
            </p>
          </div>
          <Button variant="primary" size="lg" onClick={this.handleReload}>
            Reload the study
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
