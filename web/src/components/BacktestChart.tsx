import { useState } from 'react'
import { CartesianGrid, Legend as RLegend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { BacktestResponse } from '../types'

interface Props {
  data: BacktestResponse | null | undefined // undefined = still loading, null = not available
}

// validated against the dark surface (dataviz skill): CVD dE 23, contrast >= 3:1
const SILENT = '#c8731e'
const BASELINE = '#3a7dbd'

const fmtNum = (v: unknown) => (typeof v === 'number' ? v.toFixed(3) : String(v))

export default function BacktestChart({ data }: Props) {
  const [open, setOpen] = useState(true)
  const summary = data?.summary ?? {}
  const lift = summary.lift ?? summary.mean_lift ?? summary.precision_lift
  return (
    <section className={`backtest panel ${open ? '' : 'collapsed'}`}>
      <button className="backtest-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span>
          Backtest: precision@{data?.k ?? '?'} per origin month, silent blocks vs 311 baseline
          {data?.synthetic && <span className="badge synthetic">SYNTHETIC</span>}
        </span>
        <span className="muted small">
          {data && lift !== undefined && (
            <span className="lift">lift {typeof lift === 'number' ? lift.toFixed(2) : String(lift)} </span>
          )}
          {open ? 'hide' : 'show'}
        </span>
      </button>
      {open && (
        <div className="backtest-body">
          {data === undefined && <div className="muted">loading...</div>}
          {data === null && <div className="muted">backtest not available (no /api/backtest)</div>}
          {data && (
            <>
              <ResponsiveContainer width="100%" height={170}>
                <LineChart data={data.series} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                  <CartesianGrid stroke="#242938" vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 10, fill: '#9aa0b0' }} minTickGap={24} stroke="#333a4d" />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#9aa0b0' }} width={32} stroke="#333a4d" />
                  <Tooltip
                    contentStyle={{ background: '#12151f', border: '1px solid #2a2f40', fontSize: 12 }}
                    formatter={(v) => fmtNum(v)}
                  />
                  <RLegend wrapperStyle={{ fontSize: 11 }} />
                  <Line
                    type="monotone"
                    dataKey="precision_silent"
                    name="silent blocks"
                    stroke={SILENT}
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="precision_311"
                    name="311 baseline"
                    stroke={BASELINE}
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
              <div className="summary muted small">
                {Object.entries(summary).map(([k, v]) => (
                  <span key={k}>
                    {k}: <b>{fmtNum(v)}</b>
                  </span>
                ))}
                {data.window.length === 2 && (
                  <span>
                    window: <b>{data.window[0]} to {data.window[1]}</b>
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  )
}
