import React from 'react';
import { FileText, Download, Maximize2, Search } from 'lucide-react';

const SourcePanel: React.FC = () => {
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      backgroundColor: 'var(--bg-secondary)',
      border: '1px solid var(--border-color)',
      borderRadius: '12px',
      overflow: 'hidden'
    }}>
      <header style={{
        padding: '12px 20px',
        borderBottom: '1px solid var(--border-color)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: '#222831'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '4px' }}>
            <Tab label="MSFT 2024 10-K" active />
            <Tab label="MSFT 2023 10-K" />
          </div>
        </div>
        <div style={{ display: 'flex', gap: '12px', color: 'var(--text-secondary)' }}>
          <Search size={18} cursor="pointer" />
          <Download size={18} cursor="pointer" />
          <Maximize2 size={18} cursor="pointer" />
        </div>
      </header>

      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '30px',
        color: 'var(--text-primary)',
        fontFamily: 'serif',
        lineHeight: '1.8',
        fontSize: '16px',
        backgroundColor: '#f9fafb',
        color: '#1a202c'
      }}>
        <div style={{ maxWidth: '800px', margin: '0 auto' }}>
          <h2 style={{ fontSize: '24px', fontWeight: 'bold', borderBottom: '2px solid #2d3748', paddingBottom: '8px', marginBottom: '24px' }}>
            Item 7. Management’s Discussion and Analysis of Financial Condition and Results of Operations
          </h2>

          <p style={{ marginBottom: '20px' }}>
            The following Management’s Discussion and Analysis (“MD&A”) is intended to help the reader understand Microsoft Corporation. MD&A is provided as a supplement to, and should be read in conjunction with, our consolidated financial statements and the accompanying notes.
          </p>

          <h3 style={{ fontSize: '20px', fontWeight: 'bold', marginTop: '32px', marginBottom: '16px' }}>RESULTS OF OPERATIONS</h3>
          
          <div style={{
            backgroundColor: 'white',
            border: '1px solid #e2e8f0',
            borderRadius: '4px',
            padding: '20px',
            margin: '20px 0',
            fontFamily: 'var(--font-mono)',
            fontSize: '13px',
            overflowX: 'auto'
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #cbd5e0' }}>
                  <th style={{ textAlign: 'left', padding: '8px' }}>Revenue (in millions)</th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>2024</th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>2023</th>
                  <th style={{ textAlign: 'right', padding: '8px' }}>Change</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid #edf2f7' }}>
                  <td style={{ padding: '8px' }}>Productivity and Business Processes</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$77,349</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$69,274</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: 'green' }}>12%</td>
                </tr>
                <tr style={{ borderBottom: '1px solid #edf2f7' }}>
                  <td style={{ padding: '8px' }}>Intelligent Cloud</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$105,362</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$87,907</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: 'green' }}>20%</td>
                </tr>
                <tr style={{ borderBottom: '1px solid #edf2f7' }}>
                  <td style={{ padding: '8px' }}>More Personal Computing</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$62,391</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$54,711</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: 'green' }}>14%</td>
                </tr>
                <tr style={{ fontWeight: 'bold', backgroundColor: '#f7fafc' }}>
                  <td style={{ padding: '8px' }}>Total</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$245,102</td>
                  <td style={{ textAlign: 'right', padding: '8px' }}>$211,915</td>
                  <td style={{ textAlign: 'right', padding: '8px', color: 'green' }}>16%</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p style={{ marginBottom: '20px' }}>
            <mark style={{ backgroundColor: '#fff3cd', padding: '0 4px' }}>
              Intelligent Cloud revenue increased $17.5 billion or 20%, driven by growth in Azure and other cloud services.
            </mark>
            Azure and other cloud services revenue grew 30% (up 30% in constant currency), driven by growth in our consumption-based services.
          </p>

          <p style={{ marginBottom: '20px' }}>
            Research and development expenses increased $2.1 billion or 8%, primarily driven by investments in cloud engineering and 
            <mark style={{ backgroundColor: '#fff3cd', padding: '0 4px' }}>
              AI infrastructure to support our long-term strategic growth.
            </mark>
          </p>
        </div>
      </div>
    </div>
  );
};

const Tab: React.FC<{ label: string; active?: boolean }> = ({ label, active }) => (
  <div style={{
    padding: '8px 16px',
    fontSize: '13px',
    fontWeight: '500',
    color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
    backgroundColor: active ? 'var(--bg-secondary)' : 'transparent',
    borderRadius: '6px 6px 0 0',
    borderBottom: active ? '2px solid var(--accent-color)' : 'none',
    cursor: 'pointer'
  }}>
    {label}
  </div>
);

export default SourcePanel;
