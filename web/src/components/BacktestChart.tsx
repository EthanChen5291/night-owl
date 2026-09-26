import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { BacktestResponse } from '../types'
import { ChevronIcon } from './Icons'

interface Props {
  data: BacktestResponse | null | undefined // undefined = still loading, null = not available
  open: boolean
  onToggle: () => void
  wide: boolean // the owls panel is collapsed, so the strip can use the full width
}

// Two series, fixed order, validated on both surfaces (dataviz palette check): orange = silent blocks, blue = 311.
const SILENT = '#c8731e'
const BASELINE = '#3a7dbd'
const COVID: [string, string] = ['2020-03', '2021-06']

const fmtPct = (v: number) => `${Math.round(v * 100)}%`
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Bottom strip: KPI tiles, then precision per month for the two rankings. Slides away on its tab. */
export default function BacktestChart({ data, open, onToggle, wide }: Props) {
  const summary = data?.summary ?? {}
  const lift = num(summary.lift ?? summary.lift_vs_311 ?? summary.mean_lift ?? summary.precision_lift)
  const meanSilent = num(summary.mean_precision_silent)
  const mean311 = num(summary.mean_precision_311)
  const beating = num(summary.months_beating_311)
  const months = num(summary.n_months) ?? data?.series.length ?? null
  const ticks = useMemo(() => (data ? data.series.filter((p) => p.month.endsWith('-01')).map((p) => p.month) : []), [data])
  const last = data?.series[data.series.length - 1]
  return (
    <section className={`backtest panel ${open ? '' : 'collapsed'} ${wide ? 'wide' : ''}`}>
      <button className="tab tab-top" onClick={onToggle} title={open ? 'Hide backtest' : 'Show backtest'} aria-expanded={open}>
        <ChevronIcon size={16} dir={open ? 'down' : 'up'} />
        <span>Backtest</span>
      </button>
      <div className="backtest-body">
        <div className="kpis">
          <div className="kpi">
            <span className="kpi-label">lift vs 311</span>
            <span className="kpi-value">{lift !== null ? `${lift.toFixed(2)}×` : '—'}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">
              <i className="dot" style={{ background: SILENT }} /> silent blocks
            </span>
            <span className="kpi-value">{meanSilent !== null ? fmtPct(meanSilent) : '—'}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">
              <i className="dot" style={{ background: BASELINE }} /> 311 baseline
            </span>
            <span className="kpi-value">{mean311 !== null ? fmtPct(mean311) : '—'}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">months ahead</span>
            <span className="kpi-value">{beating !== null && months !== null ? `${beating} / ${months}` : '—'}</span>
          </div>
          <div className="kpi grow">
            <span className="kpi-label">precision@{data?.k ?? '?'} on proactive inspections the following month</span>
            <span className="kpi-sub muted">
              {data?.window.length === 2 ? `${data.window[0]} → ${data.window[1]}` : ''}
              {data?.synthetic && <span className="badge synthetic">synthetic</span>}
            </span>
          </div>
        </div>
        {data === undefined && <div className="muted">loading...</div>}
        {data === null && <div className="muted">backtest not available (no /api/backtest)</div>}
        {data && (
          <div className="chart">
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={data.series} margin={{ top: 10, right: 92, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="rgba(128, 140, 155, 0.22)" vertical={false} />
                <ReferenceArea x1={COVID[0]} x2={COVID[1]} fill="rgba(128, 140, 155, 0.12)" strokeOpacity={0} label={{ value: 'COVID', position: 'insideTop', fontSize: 11, fill: '#7c8794' }} />
                <XAxis dataKey="month" ticks={ticks} tickFormatter={(m: string) => m.slice(0, 4)} tick={{ fontSize: 12, fill: '#7c8794' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 0.6]} ticks={[0, 0.2, 0.4, 0.6]} tickFormatter={fmtPct} tick={{ fontSize: 12, fill: '#7c8794' }} width={40} axisLine={false} tickLine={false} />
                <Tooltip
                  cursor={{ stroke: 'rgba(128,140,155,0.5)', strokeDasharray: '3 3' }}
                  contentStyle={{ background: 'var(--glass-strong)', border: '1px solid var(--glass-line)', borderRadius: 12, color: 'var(--ink)', fontSize: 12, boxShadow: 'var(--glass-shadow)' }}
                  labelStyle={{ fontWeight: 600, marginBottom: 4 }}
                  formatter={(v: unknown, name: unknown) => [typeof v === 'number' ? fmtPct(v) : String(v), String(name)]}
                />
                <Line type="monotone" dataKey="precision_silent" name="silent blocks" stroke={SILENT} dot={false} strokeWidth={2.2} isAnimationActive={false} activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--glass-strong)' }} />
                <Line type="monotone" dataKey="precision_311" name="311 baseline" stroke={BASELINE} dot={false} strokeWidth={2.2} isAnimationActive={false} activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--glass-strong)' }} />
              </LineChart>
            </ResponsiveContainer>
            {last && (
              <div className="chart-labels" aria-hidden>
                <span style={{ color: SILENT }}>silent blocks {fmtPct(last.precision_silent)}</span>
                <span style={{ color: BASELINE }}>311 baseline {fmtPct(last.precision_311)}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
