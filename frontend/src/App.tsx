import React, { useEffect, useMemo, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import SourcePanel from './components/SourcePanel';
import WatchlistView from './components/WatchlistView';
import { Source, FilingInfo } from './api';
import { cn } from './components/ui';
import { useIsMobile } from './hooks/useMediaQuery';
import './index.css';

/**
 * The ticker the conversation is "about": the most frequent non-empty ticker
 * across the latest answer's sources. Ties resolve to the first ticker seen
 * (stable insertion order). Returns null when there are no usable tickers.
 * Pure + exported so it can be unit-tested.
 */
export function dominantTicker(sources: Source[]): string | null {
  const counts = new Map<string, number>();
  for (const s of sources) {
    const t = s?.ticker?.trim();
    if (!t) continue;
    counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestCount = 0;
  // Map preserves insertion order, so the first-seen ticker wins ties.
  for (const [ticker, count] of counts) {
    if (count > bestCount) {
      best = ticker;
      bestCount = count;
    }
  }
  return best;
}

const App: React.FC = () => {
  const [leftWidth, setLeftWidth] = useState(62);
  const [isResizing, setIsResizing] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);
  const [activeSourceIdx, setActiveSourceIdx] = useState(0);
  const [activeFiling, setActiveFiling] = useState<FilingInfo | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [view, setView] = useState<'chat' | 'watchlist'>('chat');

  const isMobile = useIsMobile();

  // The ticker the insider/smart-money panels follow: whatever the latest
  // answer is mostly about, falling back to an explicitly focused filing.
  const activeTicker = useMemo(
    () => dominantTicker(sources) ?? activeFiling?.ticker ?? null,
    [sources, activeFiling],
  );

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
        'flex h-screen w-full overflow-hidden',
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
        activeFiling={activeFiling}
        activeTicker={activeTicker}
        onSelectFiling={handleSelectFiling}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onCloseDrawer={() => setDrawerOpen(false)}
        view={view}
        onViewChange={setView}
      />

      <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-2 p-2 md:flex-row md:p-3">
        {view === 'watchlist' ? (
          <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
            <WatchlistView />
          </div>
        ) : (
          <>
            <div
              className="flex min-h-0 min-w-0 flex-1 overflow-hidden md:flex-none"
              style={isMobile ? undefined : { width: `${leftWidth}%` }}
            >
              <ChatPanel
                onSourcesUpdate={handleSourcesUpdate}
                onCitationClick={handleCitationClick}
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
          </>
        )}
      </main>
    </div>
  );
};

export default App;
