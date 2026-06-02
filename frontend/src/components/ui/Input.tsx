import React from 'react';
import { cn } from './cn';

const fieldBase =
  'w-full bg-ink-850 text-fg-100 placeholder:text-fg-400 ' +
  'border border-line rounded-md px-3 text-sm ' +
  'transition-colors duration-150 outline-none ' +
  'hover:border-line-strong focus:border-amber-400/70 ' +
  'focus:shadow-[0_0_0_3px_rgba(232,168,56,0.12)] ' +
  'disabled:opacity-60 disabled:cursor-not-allowed';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, id, className, ...rest }, ref) => {
    const autoId = React.useId();
    const inputId = id ?? autoId;
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-xs font-medium text-fg-300">
            {label}
          </label>
        )}
        <input ref={ref} id={inputId} className={cn(fieldBase, 'h-10', className)} {...rest} />
        {hint && <span className="text-[11px] text-fg-400">{hint}</span>}
      </div>
    );
  },
);
Input.displayName = 'Input';

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...rest }, ref) => (
    <textarea ref={ref} className={cn(fieldBase, 'py-3 resize-none font-sans', className)} {...rest} />
  ),
);
Textarea.displayName = 'Textarea';

export default Input;
