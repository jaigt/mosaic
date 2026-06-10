import React from 'react';
import { cn } from './cn';
import Spinner from './Spinner';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg' | 'icon';

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  /** Icon-only buttons MUST pass an aria-label for accessibility. */
}

const base =
  'inline-flex items-center justify-center gap-2 font-medium select-none ' +
  'transition-[background,border-color,color,box-shadow,transform] duration-150 ' +
  'rounded-md disabled:cursor-not-allowed disabled:opacity-50 ' +
  'active:translate-y-px focus-visible:outline-2 focus-visible:outline-amber-400 ' +
  'focus-visible:outline-offset-2 whitespace-nowrap';

const variants: Record<ButtonVariant, string> = {
  primary:
    // Gold-foil treatment: gradient surface + hover sheen sweep (see .vr-foil).
    'vr-foil text-ink-950 font-semibold border border-amber-500/80 ' +
    'hover:brightness-[1.06] ' +
    'shadow-[0_6px_18px_-8px_rgba(210,173,82,0.55)]',
  secondary:
    'bg-ink-700 text-fg-100 border border-line-strong ' +
    'hover:bg-ink-600 hover:border-amber-500/40',
  ghost:
    'bg-transparent text-fg-300 border border-transparent ' +
    'hover:bg-white/[0.04] hover:text-fg-100',
  danger:
    'bg-transparent text-crimson-400 border border-crimson-500/40 ' +
    'hover:bg-crimson-500/10 hover:border-crimson-500/60',
};

const sizes: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4 text-sm',
  lg: 'h-11 px-5 text-sm',
  icon: 'h-9 w-9 p-0',
};

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = 'secondary', size = 'md', loading, className, children, disabled, type = 'button', ...rest },
    ref,
  ) => (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(base, variants[variant], sizes[size], className)}
      {...rest}
    >
      {loading && <Spinner size={size === 'sm' ? 13 : 15} />}
      {children}
    </button>
  ),
);
Button.displayName = 'Button';

export default Button;
