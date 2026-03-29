import React, { useState } from 'react';
import { X, Download, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { ingestFiling, getIngestStatus } from '../api';

interface IngestModalProps {
  onClose: () => void;
}

const IngestModal: React.FC<IngestModalProps> = ({ onClose }) => {
  const [ticker, setTicker] = useState('');
  const [docType, setDocType] = useState('10-K');
  const [year, setYear] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker.trim()) return;
    setStatus('loading');
    setMessage('Starting ingestion...');
    try {
      const result = await ingestFiling(
        ticker.trim().toUpperCase(),
        docType,
        year ? parseInt(year) : undefined
      );
      const taskId = result.task_id;
      // Poll for completion
      const poll = async (): Promise<void> => {
        const statusResp = await getIngestStatus(taskId);
        if (statusResp.status === 'running') {
          setMessage('Processing SEC filing...');
          return new Promise(resolve => setTimeout(() => resolve(poll()), 2500));
        } else if (statusResp.status.startsWith('completed:')) {
          const chunks = statusResp.status.split(':')[1];
          setStatus('success');
          setMessage(`Successfully ingested ${chunks} chunks for ${ticker.trim().toUpperCase()}`);
        } else if (statusResp.status.startsWith('failed:')) {
          const reason = statusResp.status.slice('failed:'.length);
          setStatus('error');
          setMessage(reason || 'Ingestion failed');
        } else {
          setStatus('error');
          setMessage(`Unexpected status: ${statusResp.status}`);
        }
      };
      await poll();
    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Unknown error');
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      backgroundColor: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center'
    }}>
      <div style={{
        backgroundColor: 'var(--bg-primary)',
        border: '1px solid var(--border-color)',
        borderRadius: '12px',
        padding: '24px',
        width: '400px',
        maxWidth: '90vw'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: '600' }}>Ingest SEC Filing</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Ticker Symbol *
            </label>
            <input
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
              disabled={status === 'loading'}
              style={{
                width: '100%', padding: '10px 12px', boxSizing: 'border-box',
                backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                borderRadius: '8px', color: 'var(--text-primary)', fontSize: '14px', outline: 'none'
              }}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Document Type
            </label>
            <select
              value={docType}
              onChange={e => setDocType(e.target.value)}
              disabled={status === 'loading'}
              style={{
                width: '100%', padding: '10px 12px', boxSizing: 'border-box',
                backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                borderRadius: '8px', color: 'var(--text-primary)', fontSize: '14px', outline: 'none'
              }}
            >
              <option value="10-K">10-K (Annual)</option>
              <option value="10-Q">10-Q (Quarterly)</option>
            </select>
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
              Year (optional — leave blank for latest)
            </label>
            <input
              type="number"
              value={year}
              onChange={e => setYear(e.target.value)}
              placeholder="e.g. 2024"
              disabled={status === 'loading'}
              min="2000"
              max="2025"
              style={{
                width: '100%', padding: '10px 12px', boxSizing: 'border-box',
                backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-color)',
                borderRadius: '8px', color: 'var(--text-primary)', fontSize: '14px', outline: 'none'
              }}
            />
          </div>

          {message && (
            <div style={{
              marginBottom: '16px', padding: '12px',
              backgroundColor: status === 'success' ? 'rgba(0,200,100,0.1)' : 'rgba(255,80,80,0.1)',
              border: `1px solid ${status === 'success' ? 'var(--success-color)' : '#ff5050'}`,
              borderRadius: '8px',
              display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px'
            }}>
              {status === 'success'
                ? <CheckCircle size={16} style={{ color: 'var(--success-color)', flexShrink: 0 }} />
                : <AlertCircle size={16} style={{ color: '#ff5050', flexShrink: 0 }} />
              }
              {message}
            </div>
          )}

          <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '10px 20px', borderRadius: '8px', border: '1px solid var(--border-color)',
                backgroundColor: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '14px'
              }}
            >
              {status === 'success' ? 'Close' : 'Cancel'}
            </button>
            {status !== 'success' && (
              <button
                type="submit"
                disabled={!ticker.trim() || status === 'loading'}
                style={{
                  padding: '10px 20px', borderRadius: '8px', border: 'none',
                  backgroundColor: 'var(--accent-color)', color: 'white',
                  cursor: ticker.trim() && status !== 'loading' ? 'pointer' : 'not-allowed',
                  fontSize: '14px', fontWeight: '500',
                  display: 'flex', alignItems: 'center', gap: '8px',
                  opacity: !ticker.trim() || status === 'loading' ? 0.6 : 1
                }}
              >
                {status === 'loading' ? (
                  <Loader2 size={16} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
                ) : (
                  <Download size={16} />
                )}
                {status === 'loading' ? 'Ingesting...' : 'Ingest Filing'}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};

export default IngestModal;
