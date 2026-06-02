import React from 'react';
import { cn } from './cn';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Adds the soft panel elevation shadow. */
  elevated?: boolean;
}

/**
 * Surface primitive. Defaults to a flush bordered panel; pass `elevated` for
 * the floating look used by the main columns.
 */
const Card: React.FC<CardProps> = ({ elevated = false, className, children, ...rest }) => (
  <div
    className={cn(
      'bg-ink-900/80 border border-line rounded-lg overflow-hidden backdrop-blur-[2px]',
      elevated && 'shadow-panel',
      className,
    )}
    {...rest}
  >
    {children}
  </div>
);

export default Card;
