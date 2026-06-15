import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { cn } from './cn';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * Accessible dialog: role=dialog + aria-modal, Escape-to-close, backdrop click,
 * and initial focus moved into the panel. Body scroll is locked while open.
 */
const Modal: React.FC<ModalProps> = ({ open, onClose, title, eyebrow, children, className }) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = React.useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      // Focus trap: keep Tab / Shift+Tab cycling within the dialog panel.
      if (e.key === 'Tab') {
        const panel = panelRef.current;
        if (!panel) return;
        const focusable = panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) {
          e.preventDefault();
          panel.focus();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (e.shiftKey) {
          if (active === first || active === panel) {
            e.preventDefault();
            last.focus();
          }
        } else if (active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    panelRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center p-4 bg-ink-950/75 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        className={cn(
          'vr-rise w-full max-w-md outline-none',
          'bg-ink-850 border border-line-strong rounded-xl shadow-panel',
          className,
        )}
      >
        {(title || eyebrow) && (
          <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-line">
            <div className="min-w-0">
              {eyebrow && (
                <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-amber-400/80 mb-1">
                  {eyebrow}
                </div>
              )}
              {title && (
                <h2 id={titleId} className="font-display text-lg font-semibold text-paper-100 leading-tight">
                  {title}
                </h2>
              )}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close dialog"
              className="shrink-0 -mt-0.5 -mr-1 grid h-8 w-8 place-items-center rounded-md text-fg-400 hover:bg-white/5 hover:text-fg-100 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        )}
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
};

export default Modal;
