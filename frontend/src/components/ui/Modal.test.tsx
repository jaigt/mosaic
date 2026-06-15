import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Modal from './Modal';

describe('Modal', () => {
  it('renders nothing when closed', () => {
    render(
      <Modal open={false} onClose={() => {}} title="Hidden">
        <p>body</p>
      </Modal>,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders an accessible dialog with title and content when open', () => {
    render(
      <Modal open onClose={() => {}} title="Ingest SEC Filing" eyebrow="Data Ingestion">
        <p>form goes here</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('heading', { name: 'Ingest SEC Filing' })).toBeInTheDocument();
    expect(screen.getByText('form goes here')).toBeInTheDocument();
  });

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    );
    await userEvent.click(screen.getByRole('button', { name: /close dialog/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when Escape is pressed', async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    );
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose on backdrop mousedown', () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="T">
        <p>x</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog');
    // The backdrop is the dialog panel's parent (the fixed overlay).
    fireEvent.mouseDown(dialog.parentElement!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('traps focus: Tab from the last focusable wraps to the first', async () => {
    render(
      <Modal open onClose={() => {}} title="Focus">
        <button>first</button>
        <button>second</button>
      </Modal>,
    );
    const closeBtn = screen.getByRole('button', { name: /close dialog/i });
    const first = screen.getByRole('button', { name: 'first' });
    const last = screen.getByRole('button', { name: 'second' });

    last.focus();
    expect(last).toHaveFocus();
    await userEvent.tab();
    // Wraps back to the first focusable in the panel (the close button).
    expect(closeBtn).toHaveFocus();
    expect(first).not.toHaveFocus();
  });
});
