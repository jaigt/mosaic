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

const FinancialChart: React.FC<FinancialChartProps> = React.memo(({ title, data, color = '#d2ad52' }) => {
  return (
    <div className="rounded-lg border border-line bg-ink-850/80 p-4 shadow-panel">
      <div className="mb-3 flex items-center gap-2.5">
        <span className="h-2 w-2 rotate-45 bg-amber-400" aria-hidden="true" />
        <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-fg-300">{title}</h4>
        <span className="h-px flex-1 bg-line" aria-hidden="true" />
      </div>
      <div style={{ height: '240px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="#23362a" vertical={false} />
            <XAxis
              dataKey="name"
              stroke="#66745f"
              fontSize={11}
              fontFamily="Spline Sans Mono, monospace"
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#66745f"
              fontSize={11}
              fontFamily="Spline Sans Mono, monospace"
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `$${value}B`}
            />
            <Tooltip
              cursor={{ fill: 'rgba(210,173,82,0.07)' }}
              contentStyle={{
                backgroundColor: '#0f1611',
                border: '1px solid #32483a',
                borderRadius: '6px',
                fontFamily: 'Spline Sans Mono, monospace',
                fontSize: '12px',
                color: '#e9e6d7',
              }}
              labelStyle={{ color: '#8e9a83' }}
              itemStyle={{ color: '#e6cd83' }}
            />
            <Bar dataKey="value" fill={color} radius={[2, 2, 0, 0]} barSize={38} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
});

FinancialChart.displayName = 'FinancialChart';

export default FinancialChart;
