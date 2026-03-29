import React from 'react';
import { LayoutDashboard, History, Settings, LogOut, PlusCircle } from 'lucide-react';

const Sidebar: React.FC = () => {
  return (
    <div style={{
      width: 'var(--sidebar-width)',
      backgroundColor: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border-color)',
      display: 'flex',
      flexDirection: 'column',
      padding: '20px 0'
    }}>
      <div style={{ padding: '0 20px 20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <div style={{ width: '32px', height: '32px', backgroundColor: 'var(--accent-color)', borderRadius: '4px' }}></div>
        <h1 style={{ fontSize: '18px', fontWeight: 'bold', color: 'var(--text-primary)' }}>ValueRAG</h1>
      </div>

      <button style={{
        margin: '10px 20px',
        padding: '10px',
        backgroundColor: 'var(--accent-color)',
        color: 'white',
        border: 'none',
        borderRadius: '6px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '8px',
        fontWeight: '500'
      }}>
        <PlusCircle size={18} />
        New Analysis
      </button>

      <nav style={{ flex: 1, padding: '10px 20px' }}>
        <NavItem icon={<LayoutDashboard size={20} />} label="Dashboard" active />
        <NavItem icon={<History size={20} />} label="History" />
        <NavItem icon={<Settings size={20} />} label="Settings" />
      </nav>

      <div style={{ padding: '20px', borderTop: '1px solid var(--border-color)' }}>
        <NavItem icon={<LogOut size={20} />} label="Logout" />
      </div>
    </div>
  );
};

interface NavItemProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
}

const NavItem: React.FC<NavItemProps> = ({ icon, label, active }) => (
  <div style={{
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px',
    color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
    backgroundColor: active ? 'var(--bg-secondary)' : 'transparent',
    borderRadius: '6px',
    cursor: 'pointer',
    marginBottom: '4px',
    transition: 'all 0.2s'
  }}>
    {icon}
    <span style={{ fontSize: '14px', fontWeight: '500' }}>{label}</span>
  </div>
);

export default Sidebar;
