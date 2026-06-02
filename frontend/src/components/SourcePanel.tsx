import React, { useEffect, useState } from 'react';
import DOMPurify from 'dompurify';
import { FileText, Download, Maximize2, Search, Info } from 'lucide-react';
import { Source } from '../api';

interface SourcePanelProps {
  sources: Source[];
}

// Allowlist for SEC table HTML: structural table tags only, no scripts/styles/
// event handlers. Backstops the backend cleanup against stored XSS.
const TABLE_SANITIZE = {
  ALLOWED_TAGS: ['table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption', 'colgroup', 'col', 'span', 'br'],
  ALLOWED_ATTR: ['colspan', 'rowspan', 'scope'],
  FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'svg', 'img', 'link'],
  FORBID_ATTR: ['onerror', 'onload', 'onclick', 'style'],
};

const SourcePanel: React.FC<SourcePanelProps> = ({ sources }) => {
  const [activeIdx, setActiveIdx] = useState(0);

  // Reset the active tab whenever a new result set arrives, so a previously
  // selected (now out-of-range) index can't blank the panel.
  useEffect(() => { setActiveIdx(0); }, [sources]);

  const hasRealSources = sources.length > 0;
  const activeSource = hasRealSources ? sources[activeIdx] : null;

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      backgroundColor: 'var(--bg-sidebar)', border: '1px solid var(--border-color)',
      borderRadius: '12px', overflow: 'hidden'
    }}>
      <header style={{
        padding: '0 12px', borderBottom: '1px solid var(--border-color)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        backgroundColor: 'var(--bg-sidebar)', height: '48px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', height: '100%', gap: '2px', overflowX: 'auto', flex: 1 }}>
          {hasRealSources ? sources.map((s, i) => (
            <Tab
              key={i}
              label={`Source ${i + 1}`}
              sublabel={`${s.ticker} ${s.year}`}
              active={i === activeIdx}
              onClick={() => setActiveIdx(i)}
            />
          )) : (
            <Tab label="Source Viewer" active />
          )}
        </div>
        <div style={{ display: 'flex', gap: '12px', color: 'var(--text-secondary)', flexShrink: 0, marginLeft: '12px' }}>
          <Search size={16} style={{ cursor: 'pointer' }} />
          <Download size={16} style={{ cursor: 'pointer' }} />
          <Maximize2 size={16} style={{ cursor: 'pointer' }} />
        </div>
      </header>

      <div style={{
        flex: 1, overflowY: 'auto', padding: '0',
        backgroundColor: '#0d1117', color: '#c9d1d9'
      }}>
        {!hasRealSources ? (
          <EmptyState />
        ) : activeSource ? (
          <SourceChunkView source={activeSource} index={activeIdx} total={sources.length} />
        ) : null}
      </div>
    </div>
  );
};

const EmptyState: React.FC = () => (
  <div style={{
    maxWidth: '800px', margin: '0 auto',
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', height: '100%', gap: '20px',
    color: 'var(--text-secondary)', textAlign: 'center', padding: '40px'
  }}>
    <div style={{ 
      width: '64px', height: '64px', borderRadius: '16px', 
      backgroundColor: 'var(--bg-secondary)', display: 'flex', 
      alignItems: 'center', justifyContent: 'center', opacity: 0.5
    }}>
      <FileText size={32} />
    </div>
    <div>
      <div style={{ fontSize: '18px', fontWeight: '600', color: 'var(--text-primary)', marginBottom: '8px' }}>No sources selected</div>
      <div style={{ fontSize: '14px', maxWidth: '300px', margin: '0 auto', opacity: 0.7 }}>
        Retrieved SEC excerpts and tables will be displayed here for verification.
      </div>
    </div>
  </div>
);

interface SourceChunkViewProps {
  source: Source;
  index: number;
  total: number;
}

const SourceChunkView: React.FC<SourceChunkViewProps> = ({ source, index, total }) => (
  <div style={{ maxWidth: '900px', margin: '0 auto', padding: '40px' }}>
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      marginBottom: '32px', paddingBottom: '24px', borderBottom: '1px solid #30363d'
    }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <span style={{ 
            padding: '2px 8px', borderRadius: '4px', backgroundColor: 'var(--accent-color)', 
            color: 'white', fontSize: '11px', fontWeight: '700' 
          }}>
            {source.ticker}
          </span>
          <span style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            {source.year} {source.quarter && source.quarter !== 'FY' ? ` ${source.quarter}` : ''} • {source.chunk_type.toUpperCase()}
          </span>
        </div>
        <h2 style={{ fontSize: '24px', fontWeight: '700', margin: '0', color: '#f0f6fc' }}>
          {source.section}
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px', fontSize: '12px', color: '#8b949e' }}>
          <Info size={14} />
          Relevance Score: {(1 / (1 + source.score)).toFixed(4)}
        </div>
      </div>
      <div style={{ fontSize: '12px', color: '#8b949e', fontWeight: '500' }}>
        DOC {index + 1} OF {total}
      </div>
    </div>

    {source.chunk_type === 'table' ? (
      <div className="source-content">
        {/* LLM summary */}
        {source.text_content && (
          <div style={{
            marginBottom: '24px', padding: '16px 20px',
            backgroundColor: 'rgba(56, 139, 253, 0.1)', borderLeft: '4px solid #388bfd',
            borderRadius: '6px', fontSize: '14px', lineHeight: '1.6', color: '#adbac7'
          }}>
            <div style={{ fontSize: '11px', fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#58a6ff', marginBottom: '8px' }}>
              CONTEXTUAL SUMMARY
            </div>
            {source.text_content}
          </div>
        )}
        {/* Rendered HTML table — sanitized; styling lives in index.css */}
        <div
          className="sec-table-container"
          style={{ overflowX: 'auto', fontSize: '13px' }}
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(source.raw_payload, TABLE_SANITIZE) }}
        />
      </div>
    ) : (
      <div style={{ 
        fontSize: '16px', lineHeight: '1.8', whiteSpace: 'pre-wrap', 
        wordBreak: 'break-word', color: '#adbac7', fontFamily: 'serif' 
      }}>
        {source.raw_payload}
      </div>
    )}
  </div>
);

const Tab: React.FC<{ label: string; sublabel?: string; active?: boolean; onClick?: () => void }> = ({ label, sublabel, active, onClick }) => (
  <div
    onClick={onClick}
    style={{
      padding: '0 16px', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center',
      minWidth: '120px', cursor: onClick ? 'pointer' : 'default',
      backgroundColor: active ? '#0d1117' : 'transparent',
      borderBottom: active ? '2px solid var(--accent-color)' : 'none',
      borderRight: '1px solid var(--border-color)',
      transition: 'background-color 0.2s'
    }}
  >
    <div style={{ 
      fontSize: '12px', fontWeight: '600', 
      color: active ? 'var(--text-primary)' : 'var(--text-secondary)' 
    }}>
      {label}
    </div>
    {sublabel && (
      <div style={{ fontSize: '10px', color: 'var(--text-secondary)', opacity: 0.6 }}>
        {sublabel}
      </div>
    )}
  </div>
);

export default SourcePanel;
