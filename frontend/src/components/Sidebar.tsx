import React, { useEffect, useState } from 'react';
import { LayoutDashboard, History, Settings, LogOut, Database, FileText, RefreshCw, Loader2 } from 'lucide-react';
import { listFilings, FilingInfo, ingestFiling, getIngestStatus } from '../api';

interface SidebarProps {
  onIngestClick: () => void;
  activeFiling: FilingInfo | null;
  onSelectFiling: (filing: FilingInfo) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ onIngestClick, activeFiling, onSelectFiling }) => {
  const [filings, setFilings] = useState<FilingInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [reingesting, setReingesting] = useState<string | null>(null); // filing_id as ticker-year-type

  const fetchFilings = async () => {
    try {
      const data = await listFilings();
      setFilings(data.filings);
    } catch (err) {
      console.error('Failed to fetch filings', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFilings();
    // Poll every 30 seconds for updates
    const interval = setInterval(fetchFilings, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleReingest = async (e: React.MouseEvent, f: FilingInfo) => {
    e.stopPropagation();
    const taskId = `${f.ticker}-${f.document_type}-${f.filing_year}`;
    if (reingesting === taskId) return;

    try {
      const resp = await ingestFiling(f.ticker, f.document_type, f.filing_year);
      setReingesting(resp.task_id);
      
      // Start polling
      const poll = async () => {
        try {
          const statusResp = await getIngestStatus(resp.task_id);
          if (statusResp.status === 'running') {
            setTimeout(poll, 2000);
          } else {
            setReingesting(null);
            fetchFilings();
          }
        } catch (err) {
          console.error('Polling failed', err);
          setReingesting(null);
        }
      };
      setTimeout(poll, 2000);
    } catch (err) {
      alert(`Re-ingestion failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <div style={{
      width: 'var(--sidebar-width)',
      backgroundColor: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border-color)',
      display: 'flex', flexDirection: 'column', padding: '24px 0',
      overflow: 'hidden'
    }}>
      <div style={{ padding: '0 24px 24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{ 
          width: '32px', height: '32px', 
          backgroundColor: 'var(--accent-color)', 
          borderRadius: '8px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 4px 12px rgba(0, 123, 255, 0.3)'
        }}>
          <Database size={18} color="white" />
        </div>
        <h1 style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>ValueRAG</h1>
      </div>

      <div style={{ padding: '0 16px 20px' }}>
        <button
          onClick={onIngestClick}
          style={{
            width: '100%', padding: '12px',
            backgroundColor: 'var(--accent-color)', color: 'white',
            border: 'none', borderRadius: '10px', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: '8px', fontWeight: '600', fontSize: '14px',
            transition: 'transform 0.1s, background-color 0.2s'
          }}
          onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--accent-hover)'}
          onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'var(--accent-color)'}
        >
          <Database size={16} />
          Ingest New Filing
        </button>
      </div>

      <nav style={{ flex: 1, padding: '0 16px', overflowY: 'auto' }}>
        <div style={{ 
          fontSize: '11px', fontWeight: '700', color: 'var(--text-secondary)', 
          textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0 12px 12px'
        }}>
          Main Menu
        </div>
        <NavItem icon={<LayoutDashboard size={18} />} label="Analysis Lab" active />
        <NavItem icon={<History size={18} />} label="Query History" />
        
        <div style={{ 
          fontSize: '11px', fontWeight: '700', color: 'var(--text-secondary)', 
          textTransform: 'uppercase', letterSpacing: '0.05em', padding: '24px 12px 12px'
        }}>
          Ingested Filings
        </div>
        {loading && filings.length === 0 ? (
          <div style={{ padding: '12px', fontSize: '12px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
            Loading filings...
          </div>
        ) : filings.length === 0 ? (
          <div style={{ padding: '12px', fontSize: '12px', color: 'var(--text-secondary)', opacity: 0.6 }}>
            No filings ingested yet.
          </div>
        ) : (
          filings.map((f) => {
            const taskId = `${f.ticker}-${f.document_type}-${f.filing_year}`;
            const isActive = activeFiling?.ticker === f.ticker &&
                             activeFiling?.filing_year === f.filing_year &&
                             activeFiling?.document_type === f.document_type;
            const isReingesting = reingesting === taskId;

            return (
              <div key={taskId}
                onClick={() => onSelectFiling(f)}
                style={{
                  padding: '10px 12px', borderRadius: '8px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: '10px',
                  transition: 'background-color 0.2s', marginBottom: '2px',
                  backgroundColor: isActive ? 'rgba(0, 123, 255, 0.15)' : 'transparent',
                  border: isActive ? '1px solid rgba(0, 123, 255, 0.3)' : '1px solid transparent',
                  position: 'relative'
                }}
                onMouseEnter={(e) => !isActive && (e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.03)')}
                onMouseLeave={(e) => !isActive && (e.currentTarget.style.backgroundColor = 'transparent')}
              >
                <FileText size={16} style={{ color: isActive ? 'var(--accent-color)' : 'var(--text-secondary)', opacity: 0.8 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', fontWeight: '600', color: 'var(--text-primary)' }}>{f.ticker}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{f.filing_year} {f.document_type} • {f.chunks} chunks</div>
                </div>
                
                <button
                  onClick={(e) => handleReingest(e, f)}
                  disabled={isReingesting}
                  title="Re-ingest/Refresh"
                  style={{
                    padding: '6px', borderRadius: '4px', border: 'none',
                    backgroundColor: 'transparent', color: 'var(--text-secondary)',
                    cursor: isReingesting ? 'not-allowed' : 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)'}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  {isReingesting ? (
                    <Loader2 size={14} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
                  ) : (
                    <RefreshCw size={14} />
                  )}
                </button>
                
                {isActive && <div style={{ width: '4px', height: '4px', borderRadius: '50%', backgroundColor: 'var(--accent-color)', marginLeft: '4px' }} />}
              </div>
            );
          })
        )}
      </nav>

      <div style={{ padding: '16px', borderTop: '1px solid var(--border-color)', marginTop: 'auto' }}>
        <NavItem icon={<Settings size={18} />} label="Settings" />
        <NavItem icon={<LogOut size={18} />} label="Sign Out" />
      </div>
    </div>
  );
};

interface NavItemProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
}

const NavItem: React.FC<NavItemProps> = ({ icon, label, active, onClick }) => (
  <div
    onClick={onClick}
    style={{
      display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 12px',
      color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
      backgroundColor: active ? 'rgba(0, 123, 255, 0.1)' : 'transparent',
      borderLeft: active ? '3px solid var(--accent-color)' : '3px solid transparent',
      borderRadius: '4px', cursor: onClick || active ? 'pointer' : 'default',
      marginBottom: '4px', transition: 'all 0.2s'
    }}
    onMouseEnter={(e) => !active && (e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.03)')}
    onMouseLeave={(e) => !active && (e.currentTarget.style.backgroundColor = 'transparent')}
  >
    <span style={{ color: active ? 'var(--accent-color)' : 'inherit' }}>{icon}</span>
    <span style={{ fontSize: '14px', fontWeight: active ? '600' : '500' }}>{label}</span>
  </div>
);

export default Sidebar;
