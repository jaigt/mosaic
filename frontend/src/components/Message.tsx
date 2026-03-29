import React from 'react';
import { User, Bot, FileText, ExternalLink } from 'lucide-react';
import FinancialChart from './Visualizer/FinancialChart';

interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  chartData?: { name: string; value: number }[];
  citations?: { id: string; label: string }[];
}

const Message: React.FC<MessageProps> = ({ role, content, chartData, citations }) => {
  const isUser = role === 'user';

  return (
    <div style={{
      display: 'flex',
      gap: '16px',
      marginBottom: '24px',
      padding: '12px',
      borderRadius: '8px',
      backgroundColor: isUser ? 'transparent' : 'var(--bg-secondary)',
      border: isUser ? 'none' : '1px solid var(--border-color)'
    }}>
      <div style={{
        width: '32px',
        height: '32px',
        borderRadius: '4px',
        backgroundColor: isUser ? 'var(--accent-color)' : '#4a5568',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0
      }}>
        {isUser ? <User size={18} color="white" /> : <Bot size={18} color="white" />}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: '600',
          fontSize: '12px',
          color: 'var(--text-secondary)',
          marginBottom: '4px',
          textTransform: 'uppercase',
          letterSpacing: '0.05em'
        }}>
          {isUser ? 'You' : 'Analyst'}
        </div>
        
        <div style={{
          fontSize: '15px',
          lineHeight: '1.6',
          color: 'var(--text-primary)',
          whiteSpace: 'pre-wrap'
        }}>
          {content}
        </div>

        {chartData && (
          <FinancialChart 
            title="Year-over-Year Revenue (Billions USD)" 
            data={chartData} 
          />
        )}

        {citations && citations.length > 0 && (
          <div style={{ marginTop: '16px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {citations.map((cite) => (
              <button
                key={cite.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  backgroundColor: '#2d333b',
                  border: '1px solid var(--border-color)',
                  borderRadius: '4px',
                  color: 'var(--accent-color)',
                  fontSize: '12px',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s'
                }}
              >
                <FileText size={12} />
                {cite.label}
                <ExternalLink size={10} />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Message;
