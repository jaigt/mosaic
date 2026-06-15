import React, { useState } from 'react';
import { Download, CheckCircle2, AlertCircle } from 'lucide-react';
import { ingestFiling, getIngestStatus, IngestStatus } from '../api';
import { Modal, Input, Select, Button, cn } from './ui';

interface IngestModalProps {
  open: boolean;
  onClose: () => void;
}

/** Turn the backend's live `stage` (+ `detail` counts) into a human-readable
 *  progress line. Exported for unit testing. */
export function stageLabel(stage: string | null, detail: Record<string, unknown> = {}): string {
  const num = (key: string): number | null => {
    const v = detail[key];
    return typeof v === 'number' ? v : null;
  };
  switch (stage) {
    case 'resolving':
      return 'Resolving filing on SEC EDGAR…';
    case 'fetching':
      return 'Fetching filing from SEC EDGAR…';
    case 'parsing':
      return 'Parsing document…';
    case 'summarizing_tables': {
      const t = num('tables');
      return t != null ? `Summarizing ${t} tables…` : 'Summarizing tables…';
    }
    case 'embedding': {
      const c = num('chunks');
      return c != null ? `Embedding ${c} chunks…` : 'Embedding chunks…';
    }
    case 'storing':
      return 'Storing chunks…';
    case 'done':
      return 'Finishing up…';
    default:
      return 'Processing SEC filing…';
  }
}

const IngestModal: React.FC<IngestModalProps> = ({ open, onClose }) => {
  const [ticker, setTicker] = useState('');
  const [docType, setDocType] = useState('10-K');
  const [year, setYear] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const reset = () => {
    setStatus('idle');
    setMessage('');
  };

  const handleClose = () => {
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker.trim()) return;
    setStatus('loading');
    setMessage('Starting ingestion...');
    try {
      const result = await ingestFiling(
        ticker.trim().toUpperCase(),
        docType,
        year ? parseInt(year) : undefined,
      );
      const taskId = result.task_id;
      const isDone = (s: IngestStatus) =>
        s.state === 'completed' || s.status.startsWith('completed:');
      const isFailed = (s: IngestStatus) =>
        s.state === 'failed' || s.status.startsWith('failed:');

      const poll = async (): Promise<void> => {
        const statusResp = await getIngestStatus(taskId);
        if (isDone(statusResp)) {
          const chunks =
            statusResp.chunks ?? statusResp.status.split(':')[1] ?? '';
          setStatus('success');
          setMessage(`Successfully ingested ${chunks} chunks for ${ticker.trim().toUpperCase()}`);
        } else if (isFailed(statusResp)) {
          const reason =
            statusResp.error ?? statusResp.status.slice('failed:'.length);
          setStatus('error');
          setMessage(reason || 'Ingestion failed');
        } else {
          // Still running — surface the live stage as a progress line.
          setMessage(stageLabel(statusResp.stage, statusResp.detail ?? {}));
          return new Promise((resolve) => setTimeout(() => resolve(poll()), 2500));
        }
      };
      await poll();
    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  const loading = status === 'loading';

  return (
    <Modal open={open} onClose={handleClose} eyebrow="Data Ingestion" title="Ingest SEC Filing">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Ticker symbol *"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="e.g. AAPL"
          disabled={loading}
          className="font-mono tracking-wider"
          autoFocus
        />

        <Select label="Document type" value={docType} onChange={(e) => setDocType(e.target.value)} disabled={loading}>
          <option value="10-K">10-K (Annual)</option>
          <option value="10-Q">10-Q (Quarterly)</option>
        </Select>

        <Input
          label="Year"
          hint="Optional — leave blank for the latest available filing."
          type="number"
          value={year}
          onChange={(e) => setYear(e.target.value)}
          placeholder="e.g. 2024"
          disabled={loading}
          min="2000"
          max={new Date().getFullYear()}
          className="font-mono"
        />

        {message && (
          <div
            className={cn(
              'flex items-start gap-2 rounded-md border px-3 py-2.5 text-[13px] leading-snug',
              status === 'success'
                ? 'border-ledger-400/40 bg-ledger-400/10 text-ledger-300'
                : status === 'error'
                  ? 'border-crimson-500/40 bg-crimson-500/10 text-crimson-400'
                  : 'border-line-strong bg-white/[0.03] text-fg-200',
            )}
          >
            {status === 'success' ? (
              <CheckCircle2 size={16} className="mt-px shrink-0" />
            ) : status === 'error' ? (
              <AlertCircle size={16} className="mt-px shrink-0" />
            ) : null}
            <span>{message}</span>
          </div>
        )}

        <div className="mt-1 flex justify-end gap-3">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              if (status === 'success') reset();
              handleClose();
            }}
          >
            {status === 'success' ? 'Close' : 'Cancel'}
          </Button>
          {status !== 'success' && (
            <Button type="submit" variant="primary" disabled={!ticker.trim()} loading={loading}>
              {!loading && <Download size={16} />}
              {loading ? 'Ingesting...' : 'Ingest Filing'}
            </Button>
          )}
        </div>
      </form>
    </Modal>
  );
};

export default IngestModal;
