import type { Area } from '../types'
import { CityIcon } from './Icons'

interface Props {
  areas: Area[]
  hovered: string | null
  onPick: (id: string) => void
}

/** Citywide view: the boroughs you can fly into. Hovering a card lights its shape on the map and vice versa. */
export default function AreaPicker({ areas, hovered, onPick }: Props) {
  return (
    <div className="picker panel">
      <div className="picker-head">
        <CityIcon size={18} />
        <span>Fly to</span>
      </div>
      <div className="picker-grid">
        {areas.map((a) => (
          <button key={a.id} className={`picker-card ${hovered === a.id ? 'hot' : ''}`} onClick={() => onPick(a.id)}>
            <b>{a.name}</b>
          </button>
        ))}
      </div>
      <div className="muted small picker-hint">Select a borough to load its city tiles. Click another name tag to move across. Use WASD to move and J/K to change height.</div>
    </div>
  )
}
