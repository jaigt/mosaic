import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import SourcePanel from './components/SourcePanel';
import IngestModal from './components/IngestModal';
import { Source, FilingInfo } from './api';
import './index.css';

const App: React.FC = () => {
  const [leftWidth, setLeftWidth] = useState(50);
  const [isResizing, setIsResizing] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [activeFiling, setActiveFiling] = useState<FilingInfo | null>(null);

  const startResizing = () => setIsResizing(true);
  const stopResizing = () => setIsResizing(false);

  const onResize = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isResizing) return;
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const sidebarWidth = 280;
    const containerWidth = window.innerWidth - sidebarWidth;
    const newLeftWidth = ((clientX - sidebarWidth) / containerWidth) * 100;
    
    if (newLeftWidth > 2 && newLeftWidth < 98) setLeftWidth(newLeftWidth);
  };

  return (
    <div
      className="app-container"
      onMouseMove={onResize}
      onMouseUp={stopResizing}
      onMouseLeave={stopResizing}
      onTouchMove={onResize}
      onTouchEnd={stopResizing}
      style={{
        display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden',
        cursor: isResizing ? 'col-resize' : 'default',
        userSelect: isResizing ? 'none' : 'auto'
      }}
    >
      <Sidebar 
        onIngestClick={() => setIngestOpen(true)} 
        activeFiling={activeFiling}
        onSelectFiling={setActiveFiling}
      />
      <main style={{
        display: 'flex', flex: 1, padding: '12px', gap: '8px',
        backgroundColor: 'var(--bg-primary)'
      }}>
        <div style={{ width: `${leftWidth}%`, display: 'flex', minWidth: 0, overflow: 'hidden' }}>
          <ChatPanel
            onSourcesUpdate={setSources}
            onIngestClick={() => setIngestOpen(true)}
            onClear={() => { setSources([]); setActiveFiling(null); }}
            activeFiling={activeFiling}
            onClearFiling={() => setActiveFiling(null)}
          />
        </div>

        <div
          onMouseDown={startResizing}
          onTouchStart={startResizing}
          style={{
            width: '4px', cursor: 'col-resize',
            backgroundColor: isResizing ? 'var(--accent-color)' : 'var(--border-color)',
            borderRadius: '2px', transition: 'background-color 0.2s', margin: '0 4px'
          }}
        />

        <div style={{ flex: 1, display: 'flex', minWidth: 0, overflow: 'hidden' }}>
          <SourcePanel sources={sources} />
        </div>
      </main>

      {ingestOpen && <IngestModal onClose={() => setIngestOpen(false)} />}
    </div>
  );
};

export default App;
