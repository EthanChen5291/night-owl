import type { Cell, Source } from '../types'
import SearchBar, { type Place } from './SearchBar'

interface Props {
  month: string
  servedMonth: string | null
  cellCount: number
  source: Source | null // null = loading
  planBudget: number
  onMonth: (m: string) => void
  onPlanBudget: (k: number) => void
  onDemo: () => void
  cells: Cell[]
  onPick: (p: Place) => void
}

/** Top right: address search, then the month being shown, how many cells, and whether the API is live. */
export default function Header({ month, servedMonth, cellCount, source, planBudget, onMonth, onPlanBudget, onDemo, cells, onPick }: Props) {
  return (
    <header className="header">
      <SearchBar cells={cells} onPick={onPick} />
      <div className="header-status">
        <div className="status panel">
          <label className="month" title="Model month">
            <input aria-label="Model month" type="month" value={month} onChange={(e) => e.target.value && onMonth(e.target.value)} />
          </label>
          <label className="budget" title="Number of suggested sensor sites">
            sites <select aria-label="Plan budget" value={planBudget} onChange={(e) => onPlanBudget(Number(e.target.value))}>
              {[5, 10, 20].map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </label>
          <span className="muted">{cellCount.toLocaleString()} cells</span>
          <button className="demo-link" onClick={onDemo} title="Fly to the live demo cell">Demo cell</button>
          <span className={`pill ${source ?? 'loading'}`} title={source === 'live' ? 'Reading model data from the server' : source === 'fixture' ? 'Showing fixture data' : source === 'stale' ? 'Server unavailable; showing last response' : 'Connecting'}>
            {source === 'live' ? 'live' : source === 'fixture' ? 'fixture' : source === 'stale' ? 'stale' : '…'}
          </span>
        </div>
        {servedMonth && servedMonth !== month && <div className="month-note panel" role="status">Showing {servedMonth} data; {month} is unavailable.</div>}
      </div>
    </header>
  )
}
