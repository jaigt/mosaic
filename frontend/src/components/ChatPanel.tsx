import React, { useState, useRef, useEffect } from 'react';
import { Send, Upload, Trash2, X, FileText, Square } from 'lucide-react';
import Message from './Message';
import AgentState, { AgentStep, AgentStepKind } from './AgentState';
import { streamChat, Source, FilingInfo, VerificationResult } from '../api';
import { Button, Badge, Textarea, Card } from './ui';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  isStreaming?: boolean;
  verification?: VerificationResult;
}

// Order slips — clickable starters shown on the empty desk.
const SUGGESTED_PROMPTS = [
  'Summarize the key risk factors',
  'What drove revenue growth this period?',
  'Chart revenue over the last three years',
];

interface ChatPanelProps {
  onSourcesUpdate: (sources: Source[]) => void;
  onCitationClick: (sources: Source[], index: number) => void;
  onIngestClick: () => void;
  onClear: () => void;
  activeFiling: FilingInfo | null;
  onClearFiling: () => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({ onSourcesUpdate, onCitationClick, onIngestClick, onClear, activeFiling, onClearFiling }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRafRef = useRef<number | null>(null);
  // Tracks whether the latest scroll request was triggered by a brand-new
  // message (smooth) vs. a streaming token (auto / jump).
  const smoothScrollRef = useRef(true);

  const requestScroll = (smooth: boolean) => {
    if (smooth) smoothScrollRef.current = true;
    if (scrollRafRef.current !== null) return;
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null;
      const container = scrollContainerRef.current;
      // Only auto-scroll when already near the bottom, so we don't yank the
      // viewport away from a user who has scrolled up to read.
      if (container) {
        const nearBottom =
          container.scrollHeight - container.scrollTop - container.clientHeight < 120;
        if (!nearBottom && !smoothScrollRef.current) return;
      }
      messagesEndRef.current?.scrollIntoView({
        behavior: smoothScrollRef.current ? 'smooth' : 'auto',
      });
      smoothScrollRef.current = false;
    });
  };

  // Smooth-scroll only when the number of messages changes (a new bubble was
  // added). Per-token scrolling is handled imperatively in handleSend.
  useEffect(() => {
    requestScroll(true);
  }, [messages.length]);

  // Abort any in-flight stream on unmount.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (scrollRafRef.current !== null) cancelAnimationFrame(scrollRafRef.current);
    };
  }, []);

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const handleClear = () => {
    abortRef.current?.abort();
    setMessages([]);
    setAgentSteps([]);
    onClear();
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    const history = messages.map(m => ({ role: m.role, content: m.content }));

    const assistantId = crypto.randomUUID();
    setMessages(prev => [
      ...prev,
      { id: crypto.randomUUID(), role: 'user', content: text },
      { id: assistantId, role: 'assistant', content: '', isStreaming: true },
    ]);
    setInput('');
    setIsStreaming(true);
    setAgentSteps([]);

    const controller = new AbortController();
    abortRef.current = controller;

    let accumulated = '';

    try {
      const filters = activeFiling ? {
        ticker: activeFiling.ticker,
        year: activeFiling.filing_year,
        document_type: activeFiling.document_type
      } : undefined;

      for await (const event of streamChat(text, history, filters, controller.signal)) {
        if (event.type === 'status') {
          setAgentSteps(prev => [
            ...prev.map(s => s.status === 'running' ? { ...s, status: 'completed' as const } : s),
            { id: crypto.randomUUID(), label: event.data, status: 'running' as const, kind: 'status' },
          ]);
        } else if (event.type === 'agent_step') {
          // Autonomous agent actions. `ingest` reads as in-progress until the
          // following `retry_search`/`ingest_failed` step resolves it; an
          // `ingest_failed` lands as a completed (warning) step.
          const kind = event.data.kind as AgentStepKind;
          const completesIngest = kind === 'retry_search' || kind === 'ingest_failed';
          const stepStatus = kind === 'ingest' ? ('running' as const) : ('completed' as const);
          setAgentSteps(prev => [
            ...prev.map(s =>
              s.status === 'running' && (completesIngest || s.kind !== 'ingest')
                ? { ...s, status: 'completed' as const }
                : s,
            ),
            { id: crypto.randomUUID(), label: event.data.label, status: stepStatus, kind },
          ]);
        } else if (event.type === 'verification') {
          const verSnap = event.data;
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, verification: verSnap } : m
          ));
        } else if (event.type === 'chunk') {
          accumulated += event.data;
          const snap = accumulated;
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, content: snap } : m
          ));
          requestScroll(false);
        } else if (event.type === 'sources') {
          onSourcesUpdate(event.data);
          const sourceSnap = event.data;
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, sources: sourceSnap } : m
          ));
        } else if (event.type === 'done') {
          setAgentSteps(prev => prev.map(s => ({ ...s, status: 'completed' as const })));
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, isStreaming: false } : m
          ));
        } else if (event.type === 'error') {
          setMessages(prev => prev.map(m =>
            m.id === assistantId ? { ...m, content: `Error: ${event.data}`, isStreaming: false } : m
          ));
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // Stream was intentionally stopped by the user — finalize gracefully.
        setAgentSteps(prev => prev.map(s =>
          s.status === 'running' ? { ...s, status: 'completed' as const } : s
        ));
        setMessages(prev => prev.map(m =>
          m.id === assistantId ? { ...m, isStreaming: false } : m
        ));
      } else {
        setMessages(prev => prev.map(m =>
          m.id === assistantId
            ? { ...m, content: `Connection error: ${err instanceof Error ? err.message : String(err)}`, isStreaming: false }
            : m
        ));
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <Card elevated className="flex flex-1 flex-col bg-ink-900/70">
      <header className="vr-rule-b flex min-h-[62px] min-w-0 items-center justify-between gap-2 px-6 py-3.5">
        <div className="flex min-w-0 items-baseline gap-3 overflow-hidden">
          <h2 className="shrink-0 font-display text-[17px] leading-tight tracking-[0.01em] text-paper-100">
            The Analyst's Desk
          </h2>
          {activeFiling ? (
            <Badge tone="amber" mono className="max-w-full">
              <FileText size={10} aria-hidden="true" />
              <span className="truncate">{activeFiling.ticker} {activeFiling.filing_year} {activeFiling.document_type}</span>
              <button
                type="button"
                onClick={onClearFiling}
                aria-label="Clear filing focus"
                className="ml-0.5 grid place-items-center rounded-sm hover:text-amber-200"
              >
                <X size={11} />
              </button>
            </Badge>
          ) : (
            <span className="truncate font-mono text-[10px] uppercase tracking-[0.2em] text-fg-400">
              All filings
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onIngestClick}>
            <Upload size={13} /> Ingest
          </Button>
          {isStreaming && (
            <Button variant="danger" size="sm" onClick={handleStop} title="Stop generating">
              <Square size={12} /> Stop
            </Button>
          )}
          {messages.length > 0 && !isStreaming && (
            <Button variant="ghost" size="sm" onClick={handleClear} title="Clear conversation">
              <Trash2 size={13} /> Clear
            </Button>
          )}
        </div>
      </header>

      <div ref={scrollContainerRef} className="flex flex-1 flex-col gap-6 overflow-y-auto p-6">
        {messages.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center px-10 py-8 text-center">
            <div className="vr-rise font-mono text-[10px] uppercase tracking-[0.32em] text-amber-400/90" style={{ animationDelay: '60ms' }}>
              {activeFiling
                ? `${activeFiling.ticker} · ${activeFiling.filing_year} ${activeFiling.document_type}`
                : 'SEC EDGAR · Primary Sources'}
            </div>
            <h3 className="vr-rise mt-4 max-w-md font-display text-[clamp(28px,3.2vw,40px)] leading-[1.12] tracking-[0.005em] text-paper-100" style={{ animationDelay: '140ms' }}>
              Read the filings.
              <br />
              <span className="font-serif italic text-amber-300">Not the headlines.</span>
            </h3>
            <p className="vr-rise mt-4 max-w-sm font-serif text-[14.5px] leading-relaxed text-fg-300" style={{ animationDelay: '220ms' }}>
              {activeFiling
                ? 'Queries are focused on this document. Ask about margins, risk factors, or guidance — every answer cites the page it came from.'
                : 'Pick a filing from the ledger or ingest a new one, then ask. Every answer cites the exact excerpt it came from.'}
            </p>

            <div className="vr-rise mt-8 flex w-full max-w-md flex-col gap-2" style={{ animationDelay: '300ms' }}>
              {SUGGESTED_PROMPTS.map((prompt, i) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setInput(prompt)}
                  className="group flex items-center gap-3 rounded-md border border-line bg-ink-850/60 px-4 py-2.5 text-left transition-all hover:border-amber-500/40 hover:bg-amber-400/[0.05]"
                >
                  <span className="font-mono text-[10px] tabular-nums text-fg-400 transition-colors group-hover:text-amber-400">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <span className="flex-1 text-[13px] text-fg-200 transition-colors group-hover:text-fg-100">
                    {prompt}
                  </span>
                  <span className="font-mono text-[11px] text-fg-400 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true">
                    ↵
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <Message
            key={msg.id}
            role={msg.role}
            content={msg.content}
            sources={msg.sources}
            isStreaming={msg.isStreaming}
            verification={msg.verification}
            onCitationClick={onCitationClick}
          />
        ))}
        {isStreaming && <AgentState steps={agentSteps} isActive={true} />}
        <div ref={messagesEndRef} />
      </div>

      <div className="vr-rule-t bg-ink-850/60 p-4">
        <div className="relative">
          <Textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={activeFiling ? `Ask the ${activeFiling.ticker} ${activeFiling.filing_year} filing…` : 'Ask the filings — margins, risks, guidance…'}
            disabled={isStreaming}
            rows={3}
            className="min-h-[84px] max-h-[200px] pr-32 font-serif text-[14.5px] leading-relaxed placeholder:italic"
          />
          <div className="absolute bottom-3 right-3 flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={onIngestClick} title="Ingest a filing" aria-label="Ingest a filing">
              <Upload size={17} />
            </Button>
            <Button variant="primary" size="md" onClick={handleSend} disabled={!input.trim() || isStreaming}>
              <Send size={14} /> Ask
            </Button>
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between px-1 font-mono text-[9.5px] uppercase tracking-[0.18em] text-fg-400/70">
          <span>Enter to send · Shift+Enter for newline</span>
          <span>Answers cite their sources</span>
        </div>
      </div>
    </Card>
  );
};

export default ChatPanel;
