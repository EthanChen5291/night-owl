import { colourForValue, rangeFor } from '../colours'
import type { Mode } from '../types'

interface Props {
  mode: Mode
  lifted: boolean // the backtest strip is open underneath
}

const STEPS = 24

export default function Legend({ mode, lifted }: Props) {
  const [lo, hi] = rangeFor(mode)
  const stops = Array.from({ length: STEPS + 1 }, (_, i) => colourForValue(mode, lo + ((hi - lo) * i) / STEPS))
  const gradient = `linear-gradient(to right, ${stops.join(',')})`
  const label = mode === 'a' ? 'predicted complaints, percentile' : mode === 'b' ? 'Rat activity, percentile' : "what's there − city sees"
  return (
    <div className={`legend panel ${lifted ? 'lifted' : ''}`}>
      <div className="legend-title">{label}</div>
      <div className="legend-bar" style={{ background: gradient }} />
      <div className="legend-ticks">
        <span>{mode === 'silence' ? 'city over-sees' : 'low'}</span>
        {mode === 'silence' ? <span>0</span> : <span>50</span>}
        <span>{mode === 'silence' ? 'silent blocks' : 'high'}</span>
      </div>
    </div>
  )
}
