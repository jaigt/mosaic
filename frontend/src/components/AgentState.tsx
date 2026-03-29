import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Search, Database, FileText } from 'lucide-react';

interface Step {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'completed';
}

const AgentState: React.FC = () => {
  const [isExpanded, setIsExpanded] = useState(true);
  
  const steps: Step[] = [
    { id: '1', label: 'Extracting ticker: MSFT', status: 'completed' },
    { id: '2', label: 'Searching LanceDB (2024 10-K)', status: 'completed' },
    { id: '3', label: 'Analyzing R&D Expenditure Trends', status: 'running' },
    { id: '4', label: 'Synthesizing Final Analysis', status: 'pending' },
  ];

  return (
    <div style={{
      margin: '10px 0',
      border: '1px solid var(--border-color)',
      borderRadius: '8px',
      overflow: 'hidden',
      backgroundColor: 'var(--bg-secondary)'
    }}>
      <div 
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          backgroundColor: '#222831'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent-color)' }} />
          <span style={{ fontSize: '14px', fontWeight: '600' }}>Analyst is thinking...</span>
        </div>
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </div>
      
      {isExpanded && (
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border-color)' }}>
          {steps.map((step) => (
            <div key={step.id} style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '12px', 
              marginBottom: '10px',
              opacity: step.status === 'pending' ? 0.5 : 1
            }}>
              <div style={{
                width: '18px',
                height: '18px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                {step.status === 'completed' && <div style={{ width: '8px', height: '8px', backgroundColor: 'var(--success-color)', borderRadius: '50%' }} />}
                {step.status === 'running' && <Loader2 size={14} className="animate-spin" />}
                {step.status === 'pending' && <div style={{ width: '8px', height: '8px', border: '1px solid var(--text-secondary)', borderRadius: '50%' }} />}
              </div>
              <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{step.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default AgentState;
