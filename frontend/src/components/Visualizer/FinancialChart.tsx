import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
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

const FinancialChart: React.FC<FinancialChartProps> = React.memo(({ title, data, color = '#e8a838' }) => {
  return (
    <div className="rounded-lg border border-line bg-ink-850/80 p-4 shadow-panel">
      <div className="mb-3 flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-sm bg-amber-400" aria-hidden="true" />
        <h4 className="font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-fg-300">{title}</h4>
      </div>
      <div style={{ height: '240px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#1f2733" vertical={false} />
            <XAxis
              dataKey="name"
              stroke="#5e6877"
              fontSize={11}
              fontFamily="IBM Plex Mono, monospace"
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#5e6877"
              fontSize={11}
              fontFamily="IBM Plex Mono, monospace"
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `$${value}B`}
            />
            <Tooltip
              cursor={{ fill: 'rgba(232,168,56,0.06)' }}
              contentStyle={{
                backgroundColor: '#0d1118',
                border: '1px solid #2b3543',
                borderRadius: '8px',
                fontFamily: 'IBM Plex Mono, monospace',
                fontSize: '12px',
                color: '#e8ebf0',
              }}
              labelStyle={{ color: '#8a94a3' }}
              itemStyle={{ color: '#f3c969' }}
            />
            <Bar dataKey="value" fill={color} radius={[3, 3, 0, 0]} barSize={38} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
});

FinancialChart.displayName = 'FinancialChart';

export default FinancialChart;
