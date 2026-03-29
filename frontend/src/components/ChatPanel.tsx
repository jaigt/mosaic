import React, { useState } from 'react';
import { Send, Upload, Sparkles } from 'lucide-react';
import Message from './Message';
import AgentState from './AgentState';

const ChatPanel: React.FC = () => {
  const [messages] = useState([
    {
      role: 'user' as const,
      content: 'Compare Microsoft\'s revenue growth over the last 3 years and summarize their R&D focus.'
    },
    {
      role: 'assistant' as const,
      content: 'Based on the 2022-2024 10-K filings, Microsoft has shown consistent double-digit revenue growth, primarily driven by Azure and the Cloud segments. Their R&D has increasingly shifted towards integrating Generative AI across the Office 365 and GitHub suites.',
      chartData: [
        { name: '2022', value: 198.3 },
        { name: '2023', value: 211.9 },
        { name: '2024', value: 245.1 }
      ],
      citations: [
        { id: 'msft-10k-2024', label: 'MSFT 2024 10-K, Item 7' },
        { id: 'msft-10k-2023', label: 'MSFT 2023 10-K, Item 1' }
      ]
    }
  ]);

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      backgroundColor: 'var(--bg-primary)',
      border: '1px solid var(--border-color)',
      borderRadius: '12px',
      overflow: 'hidden'
    }}>
      <header style={{
        padding: '16px 20px',
        borderBottom: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Sparkles size={18} style={{ color: 'var(--accent-color)' }} />
          <h2 style={{ fontSize: '15px', fontWeight: 'bold' }}>AI Analyst Chat</h2>
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Model: Claude 3.7 Sonnet</div>
      </header>

      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '20px'
      }}>
        {messages.map((msg, idx) => (
          <Message key={idx} {...msg} />
        ))}
        <AgentState />
      </div>

      <div style={{
        padding: '20px',
        borderTop: '1px solid var(--border-color)',
        backgroundColor: 'var(--bg-sidebar)'
      }}>
        <div style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center'
        }}>
          <textarea
            placeholder="Ask about financials, risk factors, or company performance..."
            style={{
              width: '100%',
              minHeight: '80px',
              maxHeight: '200px',
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border-color)',
              borderRadius: '12px',
              padding: '12px 16px',
              paddingRight: '120px',
              color: 'var(--text-primary)',
              fontSize: '14px',
              resize: 'none',
              outline: 'none',
              fontFamily: 'inherit'
            }}
          />
          <div style={{
            position: 'absolute',
            right: '12px',
            bottom: '12px',
            display: 'flex',
            gap: '8px'
          }}>
            <button style={{
              padding: '8px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: 'transparent',
              color: 'var(--text-secondary)',
              cursor: 'pointer'
            }}>
              <Upload size={18} />
            </button>
            <button style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              backgroundColor: 'var(--accent-color)',
              color: 'white',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}>
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
