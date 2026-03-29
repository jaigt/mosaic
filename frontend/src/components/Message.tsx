import React from 'react';
import { User, Bot, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import FinancialChart from './Visualizer/FinancialChart';
import { Source } from '../api';

interface Citation {
  id: string;
  label: string;
}

interface MessageProps {
  role: 'user' | 'assistant';
  content: string;
  chartData?: { name: string; value: number }[];
  citations?: Citation[];
  sources?: Source[];
  isStreaming?: boolean;
}

const Message: React.FC<MessageProps> = ({ role, content, chartData, citations, sources, isStreaming }) => {
  const isUser = role === 'user';

  // Extract chart data from content if it contains <chart> tags
  // This is a simple parser for the "Generative UI" feature
  let cleanContent = content;
  let inlineChartData = chartData;

  if (!isUser && content.includes('<chart>')) {
    try {
      const chartMatch = content.match(/<chart>([\s\S]*?)<\/chart>/);
      if (chartMatch) {
        const parsed = JSON.parse(chartMatch[1]);
        inlineChartData = parsed.data;
        cleanContent = content.replace(/<chart>[\s\S]*?<\/chart>/, '').trim();
      }
    } catch (e) {
      console.error('Failed to parse inline chart data', e);
    }
  }

  return (
    <div style={{ 
      display: 'flex', 
      gap: '16px', 
      alignItems: 'flex-start',
      maxWidth: '100%',
      marginBottom: '8px'
    }}>
      <div style={{
        width: '36px', height: '36px', borderRadius: '8px', flexShrink: 0,
        backgroundColor: isUser ? 'var(--bg-secondary)' : 'rgba(0, 123, 255, 0.1)',
        border: `1px solid ${isUser ? 'var(--border-color)' : 'rgba(0, 123, 255, 0.2)'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center'
      }}>
        {isUser
          ? <User size={18} style={{ color: 'var(--text-secondary)' }} />
          : <Bot size={18} style={{ color: 'var(--accent-color)' }} />
        }
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          padding: isUser ? '0' : '16px', 
          borderRadius: '12px',
          backgroundColor: isUser ? 'transparent' : 'var(--bg-secondary)',
          border: isUser ? 'none' : '1px solid var(--border-color)',
          fontSize: '15px', 
          lineHeight: '1.7', 
          color: 'var(--text-primary)',
          overflowWrap: 'anywhere'
        }}>
          {cleanContent ? (
            <div className="markdown-content">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ node, ...props }) => (
                    <a {...props} style={{ color: 'var(--accent-color)', textDecoration: 'none' }} target="_blank" rel="noreferrer" />
                  ),
                  p: ({ node, ...props }) => <p {...props} style={{ marginBottom: '12px' }} />,
                  ul: ({ node, ...props }) => <ul {...props} style={{ marginBottom: '12px', paddingLeft: '20px' }} />,
                  li: ({ node, ...props }) => <li {...props} style={{ marginBottom: '4px' }} />,
                  code: ({ node, ...props }) => (
                    <code {...props} style={{ 
                      backgroundColor: 'rgba(255,255,255,0.05)', 
                      padding: '2px 4px', 
                      borderRadius: '4px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '0.9em'
                    }} />
                  ),
                  table: ({ node, ...props }) => (
                    <div style={{ overflowX: 'auto', marginBottom: '16px' }}>
                      <table {...props} style={{ 
                        width: '100%', 
                        borderCollapse: 'collapse', 
                        fontSize: '13px',
                        border: '1px solid var(--border-color)' 
                      }} />
                    </div>
                  ),
                  th: ({ node, ...props }) => (
                    <th {...props} style={{ 
                      padding: '8px', 
                      backgroundColor: 'rgba(255,255,255,0.02)', 
                      border: '1px solid var(--border-color)',
                      textAlign: 'left'
                    }} />
                  ),
                  td: ({ node, ...props }) => (
                    <td {...props} style={{ 
                      padding: '8px', 
                      border: '1px solid var(--border-color)' 
                    }} />
                  )
                }}
              >
                {cleanContent}
              </ReactMarkdown>
            </div>
          ) : (
            isStreaming ? '' : <span style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>No response</span>
          )}
          {isStreaming && (
            <span style={{
              display: 'inline-block', width: '2px', height: '14px',
              backgroundColor: 'var(--accent-color)', marginLeft: '4px',
              animation: 'blink 1s step-end infinite', verticalAlign: 'middle'
            }} />
          )}
        </div>

        {inlineChartData && inlineChartData.length > 0 && (
          <div style={{ marginTop: '16px' }}>
            <FinancialChart title="Revenue & Performance Analysis" data={inlineChartData} />
          </div>
        )}

        {sources && sources.length > 0 && (
          <div style={{ marginTop: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {sources.map((s, i) => (
              <div key={i} style={{
                padding: '4px 10px', borderRadius: '16px', fontSize: '11px', fontWeight: '500',
                backgroundColor: 'rgba(0, 200, 100, 0.08)', border: '1px solid rgba(0, 200, 100, 0.2)',
                color: '#4ade80', display: 'flex', alignItems: 'center', gap: '4px'
              }}>
                <ExternalLink size={10} />
                {s.ticker} {s.year} {s.section || s.chunk_type}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Message;
