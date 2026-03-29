const BASE = '/api';

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

export type SseEvent =
  | { type: 'status'; data: string }
  | { type: 'chunk'; data: string }
  | { type: 'sources'; data: Source[] }
  | { type: 'done'; data: null }
  | { type: 'error'; data: string };

export async function* streamChat(
  message: string,
  history: { role: string; content: string }[],
  filters?: { ticker?: string; year?: number; document_type?: string }
): AsyncGenerator<SseEvent> {
  const resp = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      message, 
      conversation_history: history,
      ticker: filters?.ticker,
      year: filters?.year,
      document_type: filters?.document_type
    }),
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticker, document_type: documentType, year: year || null }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: 'Ingest failed' }));
    throw new Error(err.detail || 'Ingest failed');
  }
  return resp.json();
}

export async function getIngestStatus(taskId: string): Promise<{ status: string }> {
  const resp = await fetch(`${BASE}/ingest/status/${taskId}`);
  if (!resp.ok) throw new Error('Failed to get status');
  return resp.json();
}

export async function listFilings(): Promise<{ filings: FilingInfo[] }> {
  const resp = await fetch(`${BASE}/filings`);
  if (!resp.ok) throw new Error('Failed to list filings');
  return resp.json();
}
