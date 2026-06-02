import React, { useState, useRef, useEffect } from 'react';
import { Send, Upload, Sparkles, Trash2, X, FileText, Square } from 'lucide-react';
import Message from './Message';
import AgentState, { AgentStep } from './AgentState';
import { streamChat, Source, FilingInfo } from '../api';

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
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      backgroundColor: 'var(--bg-primary)',
      border: '1px solid var(--border-color)', borderRadius: '12px', overflow: 'hidden'
    }}>
      <header style={{
        padding: '12px 20px', borderBottom: '1px solid var(--border-color)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        minHeight: '60px', minWidth: 0, gap: '8px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0, overflow: 'hidden' }}>
          <Sparkles size={18} style={{ color: 'var(--accent-color)' }} />
          <div style={{ minWidth: 0, overflow: 'hidden' }}>
            <h2 style={{ fontSize: '15px', fontWeight: 'bold', lineHeight: '1.2', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>AI Analyst Chat</h2>
            {activeFiling ? (
              <div style={{ 
                display: 'flex', alignItems: 'center', gap: '4px', 
                backgroundColor: 'rgba(0, 123, 255, 0.1)', border: '1px solid rgba(0, 123, 255, 0.2)',
                padding: '2px 8px', borderRadius: '4px', marginTop: '2px'
              }}>
                <FileText size={10} style={{ color: 'var(--accent-color)' }} />
                <span style={{ fontSize: '11px', fontWeight: '600', color: 'var(--accent-color)' }}>
                  {activeFiling.ticker} {activeFiling.filing_year} {activeFiling.document_type}
                </span>
                <X 
                  size={10} 
                  style={{ cursor: 'pointer', color: 'var(--accent-color)', marginLeft: '2px' }} 
                  onClick={onClearFiling}
                />
              </div>
            ) : (
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>Global Search Mode</div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button
            onClick={onIngestClick}
            style={{
              padding: '6px 14px', borderRadius: '6px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'transparent', color: 'var(--text-secondary)',
              cursor: 'pointer', fontSize: '12px', fontWeight: '500'
            }}
          >
            + Ingest Filing
          </button>
          {isStreaming && (
            <button
              onClick={handleStop}
              title="Stop generating"
              style={{
                padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--border-color)',
                backgroundColor: 'transparent', color: 'var(--text-secondary)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px',
                fontSize: '12px'
              }}
            >
              <Square size={13} />
              Stop
            </button>
          )}
          {messages.length > 0 && !isStreaming && (
            <button
              onClick={handleClear}
              title="Clear conversation"
              style={{
                padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--border-color)',
                backgroundColor: 'transparent', color: 'var(--text-secondary)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px',
                fontSize: '12px'
              }}
            >
              <Trash2 size={13} />
              Clear
            </button>
          )}
        </div>
      </header>

      <div ref={scrollContainerRef} style={{
        flex: 1, overflowY: 'auto', padding: '20px',
        display: 'flex', flexDirection: 'column', gap: '20px'
      }}>
        {messages.length === 0 && (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-secondary)', textAlign: 'center', gap: '12px', padding: '40px'
          }}>
            <Sparkles size={32} style={{ opacity: 0.4 }} />
            <div style={{ fontSize: '16px', fontWeight: '500' }}>
              {activeFiling 
                ? `Ask about ${activeFiling.ticker}'s ${activeFiling.filing_year} ${activeFiling.document_type}`
                : 'Ask about SEC filings'}
            </div>
            <div style={{ fontSize: '13px', opacity: 0.7 }}>
              {activeFiling 
                ? 'Your queries are currently focused on this specific document.'
                : 'First ingest a filing or select one from the sidebar, then ask questions.'}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <Message key={msg.id} role={msg.role} content={msg.content} sources={msg.sources} isStreaming={msg.isStreaming} />
        ))}
        {isStreaming && <AgentState steps={agentSteps} isActive={true} />}
        <div ref={messagesEndRef} />
      </div>

      <div style={{
        padding: '20px', borderTop: '1px solid var(--border-color)',
        backgroundColor: 'var(--bg-sidebar)'
      }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={activeFiling ? `Search in ${activeFiling.ticker} ${activeFiling.filing_year}...` : "Ask about financials, risk factors... (Enter to send)"}
            disabled={isStreaming}
            style={{
              width: '100%', minHeight: '80px', maxHeight: '200px',
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border-color)', borderRadius: '12px',
              padding: '12px 16px', paddingRight: '120px',
              color: 'var(--text-primary)', fontSize: '14px',
              resize: 'none', outline: 'none', fontFamily: 'inherit',
              opacity: isStreaming ? 0.6 : 1
            }}
          />
          <div style={{ position: 'absolute', right: '12px', bottom: '12px', display: 'flex', gap: '8px' }}>
            <button
              onClick={onIngestClick}
              style={{
                padding: '8px', borderRadius: '8px', border: 'none',
                backgroundColor: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer'
              }}
              title="Ingest a filing"
            >
              <Upload size={18} />
            </button>
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              style={{
                padding: '8px 16px', borderRadius: '8px', border: 'none',
                backgroundColor: 'var(--accent-color)', color: 'white',
                cursor: !input.trim() || isStreaming ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: '6px',
                opacity: !input.trim() || isStreaming ? 0.5 : 1
              }}
            >
              <Send size={16} />
              <span style={{ fontSize: '14px', fontWeight: '500' }}>Send</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
