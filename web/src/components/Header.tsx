import type { Source } from '../types'

interface Props {
  month: string
  cellCount: number
  source: Source | null // null = loading
  onMonth: (m: string) => void
}

/** Top right: the month being shown, how many cells, and whether the API is live. */
export default function Header({ month, cellCount, source, onMonth }: Props) {
  return (
    <header className="header">
      <div className="status panel">
        <label className="month" title="Model month">
          <input type="month" value={month} onChange={(e) => e.target.value && onMonth(e.target.value)} />
        </label>
        <span className="muted">{cellCount.toLocaleString()} cells</span>
        <span className={`pill ${source ?? 'loading'}`} title={source === 'live' ? 'Reading the model server' : source === 'fixture' ? 'Server unreachable: showing the fixture' : 'Connecting'}>
          {source === 'live' ? 'live' : source === 'fixture' ? 'fixture' : '…'}
        </span>
      </div>
    </header>
  )
}
