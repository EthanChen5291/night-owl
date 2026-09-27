import { colourFor } from '../colours'
import type { Cell, Mode } from '../types'
import { CloseIcon } from './Icons'

interface Props {
  cell: Cell
  mode: Mode
  addr: string | null
  onClose: () => void
}

const feature = (s: string) => s.replace(/_/g, ' ')
const fmt = (v: number, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : '-')

function Bar({ label, value, max = 100, tone }: { label: string; value: number; max?: number; tone: 'a' | 'b' | 'silence' }) {
  const w = Math.max(0, Math.min(100, (Math.abs(value) / max) * 100))
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-bar">
        <span className={`stat-fill ${tone} ${value < 0 ? 'neg' : ''}`} style={{ width: `${w}%` }} />
      </span>
      <b className="stat-val">{tone === 'silence' ? (value > 0 ? '+' : '') + fmt(value, 0) : fmt(value, 0)}</b>
    </div>
  )
}

/** Pinned by clicking a cell: the three views as bars, the posterior, the top reasons. */
export default function CellPopup({ cell, mode, addr, onClose }: Props) {
  const maxShap = Math.max(1e-6, ...cell.reasons.map((r) => Math.abs(r.shap)))
  return (
    <div className="cellcard panel">
      <div className="cellcard-head">
        <span className="swatch" style={{ background: colourFor(mode, cell) }} />
        <div className="cellcard-title">
          <b>{addr ?? `Block ${cell.h3.slice(-5)}`}</b>
          <span className="muted small">
            district {cell.cd}
            {cell.rmz ? ` · ${cell.rmz}` : ' · RMZ unavailable'} · {cell.n_inspections} inspections
          </span>
          <code className="muted small">{cell.h3}</code>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <CloseIcon size={15} />
        </button>
      </div>
      <Bar label="city sees" value={cell.pct_a} tone="a" />
      <Bar label="what's there" value={cell.pct_b} tone="b" />
      <Bar label="silence" value={cell.silence} tone="silence" />
      <div className="cellcard-detail small"><span>Complaints / month</span><b>{fmt(cell.score_a, 3)}</b></div>
      <div className="cellcard-detail small"><span>City percentile</span><b>{fmt(cell.pct_a, 1)}</b></div>
      <div className="cellcard-detail small"><span>Rat-sign percentile</span><b>{fmt(cell.pct_b, 1)}</b></div>
      <div className="cellcard-row muted small">
        <span>
          P(active signs | inspected) <b>{fmt(cell.score_b, 2)}</b> [{fmt(cell.ci_b[0], 2)}–{fmt(cell.ci_b[1], 2)}]
        </span>
        <span>
          <b>{cell.posterior.n_events}</b> accepted events
        </span>
      </div>
      <div className="cellcard-detail small"><span>Posterior α / β</span><b>{fmt(cell.posterior.alpha)} / {fmt(cell.posterior.beta)}</b></div>
      <div className="cellcard-detail small"><span>Last event</span><b>{cell.last_event_at ? new Date(cell.last_event_at).toLocaleString() : 'none'}</b></div>
      <div className="popup-reasons">
        {cell.reasons.slice(0, 3).map((r) => (
          <div key={r.feature} className="reason">
            <span className="reason-name">{feature(r.feature)}</span>
            <span className="reason-bar">
              <span className={r.shap >= 0 ? 'pos' : 'neg'} style={{ width: `${(Math.abs(r.shap) / maxShap) * 100}%` }} />
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
