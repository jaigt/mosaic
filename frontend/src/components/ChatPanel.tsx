import React, { useState, useRef, useEffect } from 'react';
import { Send, Upload, Trash2, X, FileText, Square, LineChart } from 'lucide-react';
import Message from './Message';
import AgentState, { AgentStep } from './AgentState';
import { streamChat, Source, FilingInfo } from '../api';
import { Button, Badge, Textarea, Card } from './ui';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  isStreaming?: boolean;
}

interface ChatPanelProps {
  onSourcesUpdate: (sources: Source[]) => void;
  onIngestClick: () => void;
  onClear: () => void;
  activeFiling: FilingInfo | null;
  onClearFiling: () => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({ onSourcesUpdate, onIngestClick, onClear, activeFiling, onClearFiling }) => {
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
            { id: String(Date.now()), label: event.data, status: 'running' as const },
          ]);
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
      <header className="flex min-h-[60px] min-w-0 items-center justify-between gap-2 border-b border-line px-5 py-3">
        <div className="flex min-w-0 items-center gap-3 overflow-hidden">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-amber-400/25 bg-amber-400/10">
            <LineChart size={17} className="text-amber-400" aria-hidden="true" />
          </div>
          <div className="min-w-0 overflow-hidden">
            <h2 className="truncate font-display text-[15px] font-semibold leading-tight text-paper-100">
              Analyst Desk
            </h2>
            {activeFiling ? (
              <Badge tone="amber" mono className="mt-1 max-w-full">
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
              <div className="mt-0.5 text-[11px] font-mono uppercase tracking-wider text-fg-400">
                Global Search Mode
              </div>
            )}
          </div>
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
          <div className="flex flex-1 flex-col items-center justify-center gap-4 p-10 text-center">
            <div className="relative grid h-16 w-16 place-items-center rounded-xl border border-line-strong bg-ink-800">
              <LineChart size={28} className="text-amber-400/70" aria-hidden="true" />
              <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-ledger-400 shadow-[0_0_12px_2px_rgba(69,197,133,0.5)]" />
            </div>
            <div className="max-w-sm">
              <div className="font-display text-lg font-semibold text-paper-100">
                {activeFiling
                  ? `${activeFiling.ticker} · ${activeFiling.filing_year} ${activeFiling.document_type}`
                  : 'Interrogate the filings'}
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-fg-300">
                {activeFiling
                  ? 'Your queries are focused on this document. Ask about margins, risk factors, or guidance.'
                  : 'Ingest a filing or pick one from the sidebar, then ask about financials, risk factors, and management discussion.'}
              </p>
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <Message key={msg.id} role={msg.role} content={msg.content} sources={msg.sources} isStreaming={msg.isStreaming} />
        ))}
        {isStreaming && <AgentState steps={agentSteps} isActive={true} />}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-line bg-ink-850/60 p-4">
        <div className="relative">
          <Textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={activeFiling ? `Search in ${activeFiling.ticker} ${activeFiling.filing_year}...` : 'Ask about financials, risk factors... (Enter to send)'}
            disabled={isStreaming}
            rows={3}
            className="min-h-[84px] max-h-[200px] pr-32 text-sm leading-relaxed"
          />
          <div className="absolute bottom-3 right-3 flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={onIngestClick} title="Ingest a filing" aria-label="Ingest a filing">
              <Upload size={17} />
            </Button>
            <Button variant="primary" size="md" onClick={handleSend} disabled={!input.trim() || isStreaming}>
              <Send size={15} /> Send
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
};

export default ChatPanel;
