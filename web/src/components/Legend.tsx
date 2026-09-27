import { colourForValue, MODES, rangeFor } from '../colours'
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
  const label = MODES.find((m) => m.id === mode)?.label ?? ''
  return (
    <div className={`legend panel ${lifted ? 'lifted' : ''}`}>
      <div className="legend-title">{label}</div>
      <div className="legend-bar" style={{ background: gradient }} />
      <div className="legend-ticks">
        <span>{mode === 'silence' ? 'more complaints than rats' : 'fewer'}</span>
        <span>{mode === 'silence' ? 'more rats than complaints' : 'more'}</span>
      </div>
    </div>
  )
}
