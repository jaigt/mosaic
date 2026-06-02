import React from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from './cn';

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, id, className, children, ...rest }, ref) => {
    const autoId = React.useId();
    const selectId = id ?? autoId;
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={selectId} className="text-xs font-medium text-fg-300">
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            className={cn(
              'w-full appearance-none bg-ink-850 text-fg-100 h-10 pl-3 pr-9 text-sm',
              'border border-line rounded-md outline-none transition-colors duration-150',
              'hover:border-line-strong focus:border-amber-400/70',
              'focus:shadow-[0_0_0_3px_rgba(232,168,56,0.12)]',
              'disabled:opacity-60 disabled:cursor-not-allowed',
              className,
            )}
            {...rest}
          >
            {children}
          </select>
          <ChevronDown
            size={15}
            aria-hidden="true"
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-fg-400"
          />
        </div>
      </div>
    );
  },
);
Select.displayName = 'Select';

export default Select;
