import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from './cn';

interface SpinnerProps {
  size?: number;
  className?: string;
  label?: string;
}

/** Accessible loading spinner. Announces itself to assistive tech via role. */
const Spinner: React.FC<SpinnerProps> = ({ size = 16, className, label = 'Loading' }) => (
  <span role="status" aria-label={label} className={cn('inline-flex', className)}>
    <Loader2 size={size} className="animate-spin" aria-hidden="true" />
  </span>
);

export default Spinner;
