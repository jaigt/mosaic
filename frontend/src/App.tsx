import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import SourcePanel from './components/SourcePanel';
import IngestModal from './components/IngestModal';
import { Source, FilingInfo } from './api';
import { cn } from './components/ui';
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
      className={cn(
        'flex h-screen w-screen overflow-hidden',
        isResizing ? 'cursor-col-resize select-none' : 'cursor-default',
      )}
      onMouseMove={onResize}
      onMouseUp={stopResizing}
      onMouseLeave={stopResizing}
      onTouchMove={onResize}
      onTouchEnd={stopResizing}
    >
      <Sidebar
        onIngestClick={() => setIngestOpen(true)}
        activeFiling={activeFiling}
        onSelectFiling={setActiveFiling}
      />
      <main className="flex flex-1 gap-2 p-3">
        <div className="flex min-w-0 overflow-hidden" style={{ width: `${leftWidth}%` }}>
          <ChatPanel
            onSourcesUpdate={setSources}
            onIngestClick={() => setIngestOpen(true)}
            onClear={() => { setSources([]); setActiveFiling(null); }}
            activeFiling={activeFiling}
            onClearFiling={() => setActiveFiling(null)}
          />
        </div>

        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panels"
          onMouseDown={startResizing}
          onTouchStart={startResizing}
          className={cn(
            'group relative mx-1 w-1 shrink-0 cursor-col-resize rounded-full transition-colors',
            isResizing ? 'bg-amber-400' : 'bg-line hover:bg-line-strong',
          )}
        >
          <span className="absolute inset-y-0 -left-1.5 -right-1.5" />
        </div>

        <div className="flex flex-1 min-w-0 overflow-hidden">
          <SourcePanel sources={sources} />
        </div>
      </main>

      <IngestModal open={ingestOpen} onClose={() => setIngestOpen(false)} />
    </div>
  );
};

export default App;
