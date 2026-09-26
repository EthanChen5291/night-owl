import { colourFor } from '../colours'
import type { Cell, Mode } from '../types'

interface Props {
  cell: Cell
  mode: Mode
  x: number
  y: number
}

const feature = (s: string) => s.replace(/_/g, ' ')
const fmt = (v: number, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : '-')
const fmtTs = (iso: string | null) => (iso ? iso.replace('T', ' ').replace(/\.\d+Z$/, 'Z') : 'none')

export default function CellPopup({ cell, mode, x, y }: Props) {
  const maxShap = Math.max(1e-6, ...cell.reasons.map((r) => Math.abs(r.shap)))
  // keep the card inside the viewport
  const w = 300
  const h = 330
  const left = Math.min(x + 16, window.innerWidth - w - 8)
  const top = Math.min(y + 16, window.innerHeight - h - 8)
  return (
    <div className="popup panel" style={{ left, top, width: w }}>
      <div className="popup-head">
        <span className="swatch" style={{ background: colourFor(mode, cell) }} />
        <code>{cell.h3}</code>
      </div>
      <div className="popup-grid">
        <span>cd</span>
        <b>{cell.cd}</b>
        <span>rmz</span>
        <b>{cell.rmz ?? 'none'}</b>
        <span>score_a</span>
        <b>{fmt(cell.score_a)} complaints/mo</b>
        <span>score_b</span>
        <b>{fmt(cell.score_b, 3)} P(active)</b>
        <span>pct_a / pct_b</span>
        <b>
          {fmt(cell.pct_a, 1)} / {fmt(cell.pct_b, 1)}
        </b>
        <span>silence</span>
        <b className={cell.silence > 0 ? 'pos' : 'neg'}>
          {cell.silence > 0 ? '+' : ''}
          {fmt(cell.silence, 1)}
        </b>
        <span>ci_b</span>
        <b>
          [{fmt(cell.ci_b[0], 3)}, {fmt(cell.ci_b[1], 3)}]
        </b>
        <span>posterior</span>
        <b>
          α {fmt(cell.posterior.alpha)} / β {fmt(cell.posterior.beta)}, {cell.posterior.n_events} events
        </b>
        <span>n_inspections</span>
        <b>{cell.n_inspections}</b>
        <span>last_event_at</span>
        <b>{fmtTs(cell.last_event_at)}</b>
      </div>
      <div className="popup-reasons">
        {cell.reasons.slice(0, 3).map((r) => (
          <div key={r.feature} className="reason">
            <span className="reason-name">{feature(r.feature)}</span>
            <span className="reason-bar">
              <span
                className={r.shap >= 0 ? 'pos' : 'neg'}
                style={{ width: `${(Math.abs(r.shap) / maxShap) * 100}%` }}
              />
            </span>
            <span className="reason-val">
              {r.shap >= 0 ? '+' : ''}
              {fmt(r.shap, 3)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
