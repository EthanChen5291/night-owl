import { memo, useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { BacktestResponse } from '../types'
import { ChevronIcon } from './Icons'

interface Props {
  data: BacktestResponse | null | undefined // undefined = still loading, null = not available
  open: boolean
  onToggle: () => void
  wide: boolean // the owls panel is collapsed, so the strip can use the full width
}

// The JSON calls the model's line `precision_silent` and the complaints line `precision_311`.
const OURS = '#c8731e'
const COMPLAINTS = '#3a7dbd'
const PRIOR = '#2a9180'
const RANDOM = '#8f95a6'
const COVID: [string, string] = ['2020-03', '2021-06']

const fmtPct = (v: number) => `${Math.round(v * 100)}%`
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Bottom strip: inspection results for each way of picking blocks, month by month. */
function BacktestChart({ data, open, onToggle, wide }: Props) {
  const summary = data?.summary ?? {}
  const ours = num(summary.mean_precision_silent)
  const complaints = num(summary.mean_precision_311)
  const beating = num(summary.months_beating_311)
  const months = num(summary.n_months) ?? data?.series.length ?? null
  const years = data?.window.length === 2 ? `${data.window[0].slice(0, 4)}–${data.window[1].slice(0, 4)}` : ''
  const ticks = useMemo(() => (data ? data.series.filter((p) => p.month.endsWith('-01')).map((p) => p.month) : []), [data])
  const hasPrior = data?.series.some((point) => typeof point.precision_positives === 'number') ?? false
  const hasRandom = data?.series.some((point) => typeof point.precision_random === 'number') ?? false
  return (
    <section className={`backtest panel ${open ? '' : 'collapsed'} ${wide ? 'wide' : ''}`}>
      <button className="tab tab-top" onClick={onToggle} title={open ? 'Hide' : 'Does it work? Ten years of real inspections'} aria-expanded={open}>
        <ChevronIcon size={16} dir={open ? 'down' : 'up'} />
        <span>Track record</span>
      </button>
      <div className="backtest-body">
        <div className="kpis">
          <div className="kpi">
            <span className="kpi-label">
              <i className="dot" style={{ background: OURS }} /> Rats found, our picks
            </span>
            <span className="kpi-value">{ours !== null ? fmtPct(ours) : '—'}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">
              <i className="dot" style={{ background: COMPLAINTS }} /> Rats found, by complaints
            </span>
            <span className="kpi-value">{complaints !== null ? fmtPct(complaints) : '—'}</span>
          </div>
          <div className="kpi">
            <span className="kpi-label">Months we did better</span>
            <span className="kpi-value">{beating !== null && months !== null ? `${beating} of ${months}` : '—'}</span>
          </div>
          <div className="kpi grow">
            <span className="kpi-label">Each month, pick the 50 likeliest blocks, then check what city inspectors actually found there{years ? `, ${years}` : ''}.</span>
            {data?.synthetic && <span className="kpi-sub"><span className="badge synthetic">sample data</span></span>}
          </div>
        </div>
        {data === undefined && <div className="muted">loading…</div>}
        {data === null && <div className="muted">Track record not available right now.</div>}
        {data && (
          <div className="chart">
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={data.series} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
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
                <Line type="monotone" dataKey="precision_silent" name="Our picks" stroke={OURS} dot={false} strokeWidth={2.2} isAnimationActive={false} activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--glass-strong)' }} />
                <Line type="monotone" dataKey="precision_311" name="By complaints" stroke={COMPLAINTS} dot={false} strokeWidth={2.2} isAnimationActive={false} activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--glass-strong)' }} />
                {hasPrior && <Line type="monotone" dataKey="precision_positives" name="By past findings" stroke={PRIOR} dot={false} strokeWidth={1.6} isAnimationActive={false} />}
                {hasRandom && <Line type="monotone" dataKey="precision_random" name="Random" stroke={RANDOM} dot={false} strokeWidth={1.4} strokeDasharray="4 3" isAnimationActive={false} />}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </section>
  )
}

export default memo(BacktestChart)
