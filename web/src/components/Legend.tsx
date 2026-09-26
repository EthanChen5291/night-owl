import { colourForValue, rangeFor } from '../colours'
import type { Mode } from '../types'

interface Props {
  mode: Mode
  showPlan: boolean
  onShowPlan: (v: boolean) => void
  planCount: number
}

const STEPS = 24

export default function Legend({ mode, showPlan, onShowPlan, planCount }: Props) {
  const [lo, hi] = rangeFor(mode)
  const stops = Array.from({ length: STEPS + 1 }, (_, i) => colourForValue(mode, lo + ((hi - lo) * i) / STEPS))
  const gradient = `linear-gradient(to right, ${stops.join(',')})`
  const label = mode === 'a' ? 'pct_a (percentile)' : mode === 'b' ? 'pct_b (percentile)' : 'silence = pct_b - pct_a'
  return (
    <div className="legend panel">
      <div className="legend-title">{label}</div>
      <div className="legend-bar" style={{ background: gradient }} />
      <div className="legend-ticks">
        <span>{lo}</span>
        {mode === 'silence' ? <span>0</span> : <span>50</span>}
        <span>{hi}</span>
      </div>
      {mode === 'silence' && (
        <div className="legend-ticks muted">
          <span>city over-sees</span>
          <span>silent blocks</span>
        </div>
      )}
      <label className="legend-check">
        <input type="checkbox" checked={showPlan} onChange={(e) => onShowPlan(e.target.checked)} />
        plan markers ({planCount} nodes)
      </label>
    </div>
  )
}
