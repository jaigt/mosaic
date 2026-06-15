import React from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

/** A single row of chart data: a `name` label plus one or more numeric series. */
export type ChartRow = { name: string } & Record<string, string | number>;

export type ChartType = 'bar' | 'line' | 'area';

/** The chart spec emitted by the backend inside <chart>…</chart>. */
export interface ChartSpec {
  type?: string;
  title?: string;
  data?: ChartRow[];
  series?: string[];
}

interface FinancialChartProps {
  title: string;
  data?: ChartRow[];
  /** Optional chart type; defaults to "bar". */
  type?: string;
  /** Optional explicit series + order. */
  series?: string[];
  /** Back-compat single-series override colour. */
  color?: string;
}

/**
 * In-theme series palette, CSS-var-backed and consistent with index.css:
 * brass-gold first (matches the legacy single-bar `#d2ad52`), then a
 * complementary ledger-mint, azure, amber-light, crimson and deep brass.
 * Series colours cycle through this list in order.
 */
export const SERIES_COLORS = [
  '#d2ad52', // amber-400  — brass gold (primary / legacy default)
  '#5cc488', // ledger-400 — mint
  '#6fa6cf', // azure-400  — slate blue
  '#e6cd83', // amber-300  — pale brass
  '#dd7158', // crimson-400 — clay
  '#99dfb0', // ledger-300 — pale mint
] as const;

const VALID_TYPES: ReadonlySet<string> = new Set(['bar', 'line', 'area']);

export interface ResolvedSeries {
  type: ChartType;
  series: string[];
}

/**
 * Resolve the ordered series keys + chart type from a chart spec, applying the
 * inference and backward-compatibility rules:
 *
 *  - `type`: "bar" | "line" | "area"; anything else (or omitted) → "bar".
 *  - `series`: when provided (non-empty array of strings) it's used verbatim,
 *    preserving order.
 *  - Otherwise series are inferred from the keys present across all data rows
 *    (excluding "name"), in first-seen order. The legacy single-series shape
 *    `[{name, value}]` therefore resolves to `["value"]`.
 *  - Empty / malformed data with no explicit series → `series: []`.
 */
export function resolveSeries(spec: ChartSpec | null | undefined): ResolvedSeries {
  const type: ChartType =
    spec && typeof spec.type === 'string' && VALID_TYPES.has(spec.type)
      ? (spec.type as ChartType)
      : 'bar';

  // Explicit series win — keep only non-empty string keys, preserving order.
  const explicit = spec?.series;
  if (Array.isArray(explicit)) {
    const cleaned = explicit.filter((s): s is string => typeof s === 'string' && s.length > 0);
    if (cleaned.length > 0) {
      return { type, series: cleaned };
    }
  }

  // Infer from data rows: every key except "name", in first-seen order.
  const rows = Array.isArray(spec?.data) ? spec!.data : [];
  const seen: string[] = [];
  const seenSet = new Set<string>();
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    for (const key of Object.keys(row)) {
      if (key === 'name' || seenSet.has(key)) continue;
      seenSet.add(key);
      seen.push(key);
    }
  }

  return { type, series: seen };
}

const AXIS_PROPS = {
  stroke: '#66745f',
  fontSize: 11,
  fontFamily: 'Spline Sans Mono, monospace',
  tickLine: false,
  axisLine: false,
} as const;

const TOOLTIP_PROPS = {
  contentStyle: {
    backgroundColor: '#0f1611',
    border: '1px solid #32483a',
    borderRadius: '6px',
    fontFamily: 'Spline Sans Mono, monospace',
    fontSize: '12px',
    color: '#e9e6d7',
  },
  labelStyle: { color: '#8e9a83' },
  itemStyle: { color: '#e6cd83' },
} as const;

const LEGEND_PROPS = {
  wrapperStyle: {
    fontFamily: 'Spline Sans Mono, monospace',
    fontSize: '11px',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.12em',
    color: '#8e9a83',
    paddingTop: '6px',
  },
  iconType: 'square' as const,
  iconSize: 9,
};

const FinancialChart: React.FC<FinancialChartProps> = React.memo(({ title, data, type, series, color }) => {
  const rows: ChartRow[] = Array.isArray(data) ? data : [];
  const { type: chartType, series: keys } = resolveSeries({ type, data: rows, series });

  const hasChart = rows.length > 0 && keys.length > 0;
  const showLegend = keys.length > 1;

  // Honour the legacy single-series colour override only when there's one
  // series; otherwise series cycle through the in-theme palette.
  const colorFor = (index: number): string => {
    if (keys.length === 1 && color) return color;
    return SERIES_COLORS[index % SERIES_COLORS.length];
  };

  return (
    <div className="rounded-lg border border-line bg-ink-850/80 p-4 shadow-panel">
      <div className="mb-3 flex items-center gap-2.5">
        <span className="h-2 w-2 rotate-45 bg-amber-400" aria-hidden="true" />
        <h4 className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-fg-300">{title}</h4>
        <span className="h-px flex-1 bg-line" aria-hidden="true" />
      </div>
      <div style={{ height: '240px' }}>
        {hasChart ? (
          <ResponsiveContainer width="100%" height="100%">
            {chartType === 'line' ? (
              <LineChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="#23362a" vertical={false} />
                <XAxis dataKey="name" {...AXIS_PROPS} />
                <YAxis {...AXIS_PROPS} tickFormatter={(value) => `$${value}B`} />
                <Tooltip cursor={{ stroke: 'rgba(210,173,82,0.25)' }} {...TOOLTIP_PROPS} />
                {showLegend && <Legend {...LEGEND_PROPS} />}
                {keys.map((key, i) => (
                  <Line
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={colorFor(i)}
                    strokeWidth={2}
                    dot={{ r: 2, fill: colorFor(i), strokeWidth: 0 }}
                    activeDot={{ r: 4 }}
                  />
                ))}
              </LineChart>
            ) : chartType === 'area' ? (
              <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  {keys.map((key, i) => (
                    <linearGradient key={key} id={`vr-area-${i}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={colorFor(i)} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={colorFor(i)} stopOpacity={0.04} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="#23362a" vertical={false} />
                <XAxis dataKey="name" {...AXIS_PROPS} />
                <YAxis {...AXIS_PROPS} tickFormatter={(value) => `$${value}B`} />
                <Tooltip cursor={{ stroke: 'rgba(210,173,82,0.25)' }} {...TOOLTIP_PROPS} />
                {showLegend && <Legend {...LEGEND_PROPS} />}
                {keys.map((key, i) => (
                  <Area
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={colorFor(i)}
                    strokeWidth={2}
                    fill={`url(#vr-area-${i})`}
                  />
                ))}
              </AreaChart>
            ) : (
              <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 4" stroke="#23362a" vertical={false} />
                <XAxis dataKey="name" {...AXIS_PROPS} />
                <YAxis {...AXIS_PROPS} tickFormatter={(value) => `$${value}B`} />
                <Tooltip cursor={{ fill: 'rgba(210,173,82,0.07)' }} {...TOOLTIP_PROPS} />
                {showLegend && <Legend {...LEGEND_PROPS} />}
                {keys.map((key, i) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    fill={colorFor(i)}
                    radius={[2, 2, 0, 0]}
                    maxBarSize={38}
                  />
                ))}
              </BarChart>
            )}
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center font-mono text-[10px] uppercase tracking-[0.18em] text-fg-400">
            No chart data
          </div>
        )}
      </div>
    </div>
  );
});

FinancialChart.displayName = 'FinancialChart';

export default FinancialChart;
