import { useMemo, useState } from 'react'
import type { Cell } from '../types'

interface Props {
  cells: Cell[]
  onSelect: (h3: string) => void
}

type Tab = 'risk' | 'silent'
const TOP = 10

// Top-10 lists from the rank fields model/export.py writes into cells.json. Click = fly to cell.
export default function Hotspots({ cells, onSelect }: Props) {
  const [tab, setTab] = useState<Tab>('silent')
  const rows = useMemo(() => {
    const key = tab === 'risk' ? 'rank_risk' : 'rank_silent'
    return cells
      .filter((c) => typeof c[key] === 'number')
      .sort((a, b) => (a[key] as number) - (b[key] as number))
      .slice(0, TOP)
  }, [cells, tab])
  if (!cells.some((c) => typeof c.rank_risk === 'number')) return null // fixture data has no ranks

  return (
    <aside className="hotspots panel">
      <div className="hotspots-head">
        <span>NYC hotspots</span>
        <div className="toggle-row">
          <button className={tab === 'silent' ? 'active' : ''} onClick={() => setTab('silent')}
            title="rats likely, far fewer complaints than expected">
            Silent
          </button>
          <button className={tab === 'risk' ? 'active' : ''} onClick={() => setTab('risk')}
            title="where rats are most likely, whatever people report">
            Rat risk
          </button>
        </div>
      </div>
      <div className="muted small">
        {tab === 'silent' ? 'rats likely, nobody calling' : 'most likely to have rats'} · click to fly there
      </div>
      <ol>
        {rows.map((c) => (
          <li key={c.h3} onClick={() => onSelect(c.h3)}>
            <div className="feed-row">
              <b>
                {tab === 'risk' ? c.rank_risk : c.rank_silent}. {c.neighborhood ?? c.h3}
              </b>
              <span className="muted small">{c.borough}</span>
            </div>
            <div className="feed-row small">
              <span>risk {(c.score_b * 100).toFixed(1)}%</span>
              <span className={c.silence > 0 ? 'pos' : 'neg'}>silence {c.silence > 0 ? '+' : ''}{c.silence.toFixed(0)}</span>
              <span className="muted">{c.n_complaints_12m ?? '?'} calls/yr</span>
            </div>
          </li>
        ))}
      </ol>
    </aside>
  )
}
