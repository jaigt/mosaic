const BASE = '/api';

// Optional API key for the backend's cost-bearing endpoints (/chat, /ingest,
// /retrieve). Set VITE_API_KEY at build/dev time to match the backend's
// API_KEY setting; when unset (local dev default) no header is sent.
const API_KEY: string | undefined = import.meta.env.VITE_API_KEY;

function jsonHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_KEY) headers['X-API-Key'] = API_KEY;
  return headers;
}

export interface Source {
  ticker: string;
  year: number;
  quarter: string;
  section: string;
  chunk_type: string;
  text_content: string;
  raw_payload: string;
  score: number;
}

export interface FilingInfo {
  ticker: string;
  document_type: string;
  filing_year: number;
  chunks: number;
}

export interface VerificationResult {
  status: 'supported' | 'caveats' | 'unknown';
  issues: string[];
}

export type SseEvent =
  | { type: 'status'; data: string }
  | { type: 'chunk'; data: string }
  | { type: 'sources'; data: Source[] }
  | { type: 'done'; data: null }
  | { type: 'error'; data: string }
  | { type: 'agent_step'; data: { kind: string; label: string } }
  | { type: 'verification'; data: VerificationResult };

export async function* streamChat(
  message: string,
  history: { role: string; content: string }[],
  filters?: { ticker?: string; year?: number; document_type?: string },
  signal?: AbortSignal
): AsyncGenerator<SseEvent> {
  const resp = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({
      message,
      conversation_history: history,
      ticker: filters?.ticker,
      year: filters?.year,
      document_type: filters?.document_type
    }),
    signal,
  });
  if (!resp.ok) throw new Error(`Chat request failed: ${resp.status}`);
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6)) as SseEvent;
        } catch {
          // skip malformed lines
        }
      }
    }
  }
}

export async function ingestFiling(
  ticker: string,
  documentType: string,
  year?: number
): Promise<{ status: string; task_id: string }> {
  const resp = await fetch(`${BASE}/ingest`, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify({ ticker, document_type: documentType, year: year || null }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Ingest failed' }));
    throw new Error(err.detail || 'Ingest failed');
  }
  return resp.json();
}

export interface IngestStatus {
  status: string;
  state: string;
  chunks: number | null;
  error: string | null;
  stage: string | null;
  detail: Record<string, unknown>;
}

export async function getIngestStatus(taskId: string): Promise<IngestStatus> {
  const resp = await fetch(`${BASE}/ingest/status/${taskId}`);
  if (!resp.ok) throw new Error('Failed to get status');
  return resp.json();
}

export async function listFilings(): Promise<{ filings: FilingInfo[] }> {
  const resp = await fetch(`${BASE}/filings`);
  if (!resp.ok) throw new Error('Failed to list filings');
  return resp.json();
}
