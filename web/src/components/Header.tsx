import type { Source } from '../types'

interface Props {
  month: string
  cellCount: number
  source: Source | null // null = loading
  onMonth: (m: string) => void
}

export default function Header({ month, cellCount, source, onMonth }: Props) {
  return (
    <header className="header">
      <span className="brand">Barn Owl</span>
      <span className="muted">silent blocks, lower Manhattan</span>
      <label className="month">
        month
        <input type="month" value={month} onChange={(e) => e.target.value && onMonth(e.target.value)} />
      </label>
      <span className="muted">{cellCount} cells</span>
      <span className={`pill ${source ?? 'loading'}`}>API: {source ?? 'connecting'}</span>
    </header>
  )
}
