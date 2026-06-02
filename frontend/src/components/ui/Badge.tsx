import React from 'react';
import { cn } from './cn';

type BadgeTone = 'neutral' | 'amber' | 'ledger' | 'azure' | 'crimson';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  /** Pill = fully rounded; otherwise a tight tag shape. */
  pill?: boolean;
  mono?: boolean;
}

const tones: Record<BadgeTone, string> = {
  neutral: 'bg-white/[0.04] text-fg-200 border-line-strong',
  amber: 'bg-amber-400/10 text-amber-300 border-amber-400/25',
  ledger: 'bg-ledger-400/10 text-ledger-300 border-ledger-400/25',
  azure: 'bg-azure-400/10 text-azure-400 border-azure-400/25',
  crimson: 'bg-crimson-500/10 text-crimson-400 border-crimson-500/25',
};

const Badge: React.FC<BadgeProps> = ({
  tone = 'neutral',
  pill = false,
  mono = false,
  className,
  children,
  ...rest
}) => (
  <span
    className={cn(
      'inline-flex items-center gap-1.5 border px-2 py-0.5 text-[11px] font-medium leading-none',
      'tracking-wide',
      pill ? 'rounded-full' : 'rounded',
      mono && 'font-mono uppercase tracking-wider',
      tones[tone],
      className,
    )}
    {...rest}
  >
    {children}
  </span>
);

export default Badge;
