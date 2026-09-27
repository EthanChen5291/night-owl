import type { Cell, Source } from '../types'
import SearchBar, { type Place } from './SearchBar'

interface Props {
  source: Source | null // null = loading
  cells: Cell[]
  onPick: (p: Place) => void
}

/** Search, plus a warning only when the map is not showing live model data. */
export default function Header({ source, cells, onPick }: Props) {
  const offline = source === 'fixture' || source === 'stale'
  return (
    <header className="header">
      <SearchBar cells={cells} onPick={onPick} />
      {offline && (
        <div className="header-status">
          <span className="pill fixture panel" title="The model server is not reachable, so the map shows saved data">
            offline data
          </span>
        </div>
      )}
    </header>
  )
}
