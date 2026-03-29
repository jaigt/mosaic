import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatPanel from './components/ChatPanel';
import SourcePanel from './components/SourcePanel';
import './index.css';

const App: React.FC = () => {
  const [leftWidth, setLeftWidth] = useState(50); // percentage
  const [isResizing, setIsResizing] = useState(false);

  const startResizing = () => {
    setIsResizing(true);
  };

  const stopResizing = () => {
    setIsResizing(false);
  };

  const onResize = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isResizing) return;
    
    let clientX;
    if ('touches' in e) {
      clientX = e.touches[0].clientX;
    } else {
      clientX = e.clientX;
    }

    const containerWidth = window.innerWidth - 280; // Subtract sidebar width
    const newLeftWidth = ((clientX - 280) / containerWidth) * 100;
    
    if (newLeftWidth > 20 && newLeftWidth < 80) {
      setLeftWidth(newLeftWidth);
    }
  };

  return (
    <div 
      className="app-container"
      onMouseMove={onResize}
      onMouseUp={stopResizing}
      onTouchMove={onResize}
      onTouchEnd={stopResizing}
      style={{
        display: 'flex',
        height: '100vh',
        width: '100vw',
        overflow: 'hidden',
        cursor: isResizing ? 'col-resize' : 'default'
      }}
    >
      <Sidebar />
      <main style={{ 
        display: 'flex', 
        flex: 1, 
        padding: '12px', 
        gap: '8px',
        backgroundColor: 'var(--bg-primary)'
      }}>
        <div style={{ width: `${leftWidth}%`, display: 'flex' }}>
          <ChatPanel />
        </div>
        
        <div 
          onMouseDown={startResizing}
          onTouchStart={startResizing}
          style={{
            width: '4px',
            cursor: 'col-resize',
            backgroundColor: isResizing ? 'var(--accent-color)' : 'var(--border-color)',
            borderRadius: '2px',
            transition: 'background-color 0.2s',
            margin: '0 4px'
          }}
        />

        <div style={{ flex: 1, display: 'flex' }}>
          <SourcePanel />
        </div>
      </main>
    </div>
  );
};

export default App;
