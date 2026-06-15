import { describe, it, expect } from 'vitest';
import { stageLabel } from './IngestModal';

describe('stageLabel', () => {
  it('maps summarizing_tables with a count', () => {
    expect(stageLabel('summarizing_tables', { tables: 31 })).toBe('Summarizing 31 tables…');
  });

  it('maps embedding with a chunk count', () => {
    expect(stageLabel('embedding', { chunks: 94 })).toBe('Embedding 94 chunks…');
  });

  it('falls back gracefully when counts are missing', () => {
    expect(stageLabel('summarizing_tables', {})).toBe('Summarizing tables…');
    expect(stageLabel('embedding')).toBe('Embedding chunks…');
  });

  it('handles known stages and an unknown stage', () => {
    expect(stageLabel('fetching')).toBe('Fetching filing from SEC EDGAR…');
    expect(stageLabel('resolving')).toBe('Resolving filing on SEC EDGAR…');
    expect(stageLabel(null)).toBe('Processing SEC filing…');
    expect(stageLabel('something_new')).toBe('Processing SEC filing…');
  });
});
