import React from 'react';
import { BookOpen, Sun, Moon } from 'lucide-react';
import { useTheme, Theme } from '../hooks/useTheme';
import { cn } from './ui';

const OPTIONS: { value: Theme; label: string; Icon: typeof Sun }[] = [
  { value: 'study', label: 'Study', Icon: BookOpen },
  { value: 'modern-light', label: 'Light', Icon: Sun },
  { value: 'modern-dark', label: 'Dark', Icon: Moon },
];

/**
 * A compact 3-way segmented control for switching themes. On-theme and
 * unobtrusive: icon-only on narrow widths, icon+label otherwise.
 */
const ThemeToggle: React.FC<{ className?: string }> = ({ className }) => {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className={cn(
        'inline-flex shrink-0 items-center gap-0.5 rounded-md border border-line bg-ink-850/60 p-0.5',
        className,
      )}
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={`${label} theme`}
            onClick={() => setTheme(value)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-[5px] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors',
              active
                ? 'bg-amber-400/[0.14] text-amber-300'
                : 'text-fg-400 hover:bg-white/[0.04] hover:text-fg-200',
            )}
          >
            <Icon size={12} aria-hidden="true" />
            <span className="hidden sm:inline">{label}</span>
          </button>
        );
      })}
    </div>
  );
};

export default ThemeToggle;
