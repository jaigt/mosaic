import React, { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import SourcePanel from './components/SourcePanel';
import IngestModal from './components/IngestModal';
import { Source, FilingInfo } from './api';
import { cn } from './components/ui';
import { useIsMobile } from './hooks/useMediaQuery';
import './index.css';

const App: React.FC = () => {
  const [leftWidth, setLeftWidth] = useState(50);
  const [isResizing, setIsResizing] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [activeSourceIdx, setActiveSourceIdx] = useState(0);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [activeFiling, setActiveFiling] = useState<FilingInfo | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const isMobile = useIsMobile();

  // Close the mobile drawer whenever we cross back to the desktop layout, so a
  // drawer left open on a narrow viewport doesn't linger after a resize.
  useEffect(() => {
    if (!isMobile) setDrawerOpen(false);
  }, [isMobile]);

  // Esc closes the mobile drawer.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  // New result set → reset the focused source so a stale index can't blank
  // the panel.
  const handleSourcesUpdate = (next: Source[]) => {
    setSources(next);
    setActiveSourceIdx(0);
  };

  // A citation pill in the chat focuses its source in the panel (loading that
  // message's source set if the panel currently shows a different one).
  const handleCitationClick = (msgSources: Source[], index: number) => {
    setSources(msgSources);
    setActiveSourceIdx(index);
  };

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

  const handleSelectFiling = (filing: FilingInfo) => {
    setActiveFiling(filing);
    setDrawerOpen(false);
  };

  return (
    <div
      className={cn(
        'flex h-screen w-screen overflow-hidden',
        'flex-col md:flex-row',
        isResizing ? 'cursor-col-resize select-none' : 'cursor-default',
      )}
      onMouseMove={onResize}
      onMouseUp={stopResizing}
      onMouseLeave={stopResizing}
      onTouchMove={onResize}
      onTouchEnd={stopResizing}
    >
      {/* Mobile drawer scrim */}
      {isMobile && drawerOpen && (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setDrawerOpen(false)}
          className="fixed inset-0 z-40 bg-ink-950/70 backdrop-blur-sm md:hidden"
        />
      )}

      <Sidebar
        onIngestClick={() => setIngestOpen(true)}
        activeFiling={activeFiling}
        onSelectFiling={handleSelectFiling}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onCloseDrawer={() => setDrawerOpen(false)}
      />

      <main className="flex min-h-0 flex-1 flex-col gap-2 p-2 md:flex-row md:p-3">
        <div
          className="flex min-h-0 min-w-0 flex-1 overflow-hidden md:flex-none"
          style={isMobile ? undefined : { width: `${leftWidth}%` }}
        >
          <ChatPanel
            onSourcesUpdate={handleSourcesUpdate}
            onCitationClick={handleCitationClick}
            onIngestClick={() => setIngestOpen(true)}
            onClear={() => { setSources([]); setActiveSourceIdx(0); setActiveFiling(null); }}
            activeFiling={activeFiling}
            onClearFiling={() => setActiveFiling(null)}
            showMenuButton={isMobile}
            onMenuClick={() => setDrawerOpen(true)}
          />
        </div>

        {/* Resizer — desktop only; vertical stacking has no draggable split. */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panels"
          onMouseDown={startResizing}
          onTouchStart={startResizing}
          className={cn(
            'group relative mx-1 hidden w-1 shrink-0 cursor-col-resize rounded-full transition-colors md:block',
            isResizing ? 'bg-amber-400' : 'bg-line hover:bg-line-strong',
          )}
        >
          <span className="absolute inset-y-0 -left-1.5 -right-1.5" />
        </div>

        <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
          <SourcePanel
            sources={sources}
            activeIdx={activeSourceIdx}
            onActiveIdxChange={setActiveSourceIdx}
          />
        </div>
      </main>

      <IngestModal open={ingestOpen} onClose={() => setIngestOpen(false)} />
    </div>
  );
};

export default App;
