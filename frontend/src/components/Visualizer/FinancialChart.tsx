import React from 'react';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip,
  ResponsiveContainer
} from 'recharts';

interface ChartData {
  name: string;
  value: number;
}

interface FinancialChartProps {
  title: string;
  data: ChartData[];
  color?: string;
}

const FinancialChart: React.FC<FinancialChartProps> = ({ title, data, color = '#007bff' }) => {
  return (
    <div style={{
      width: '100%',
      height: '300px',
      backgroundColor: '#1a1f26',
      padding: '16px',
      borderRadius: '8px',
      marginTop: '12px',
      border: '1px solid var(--border-color)'
    }}>
      <h4 style={{ fontSize: '14px', marginBottom: '16px', color: 'var(--text-secondary)' }}>{title}</h4>
      <ResponsiveContainer width="100%" height="80%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2d333b" vertical={false} />
          <XAxis 
            dataKey="name" 
            stroke="#a0a0a0" 
            fontSize={12}
            tickLine={false}
            axisLine={false}
          />
          <YAxis 
            stroke="#a0a0a0" 
            fontSize={12}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => `$${value}B`}
          />
          <Tooltip 
            contentStyle={{ backgroundColor: '#0d1117', border: '1px solid var(--border-color)', color: '#fff' }}
            itemStyle={{ color: '#fff' }}
          />
          <Bar dataKey="value" fill={color} radius={[4, 4, 0, 0]} barSize={40} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default FinancialChart;
