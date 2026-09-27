import type { Area } from '../types'
import { BackIcon, ListIcon, PinPlusIcon, SparkIcon } from './Icons'

interface Props {
  area: Area | null
  noBake: boolean
  placing: boolean
  showPlan: boolean
  logsOpen: boolean
  onBack: () => void
  onPlace: () => void
  onShowPlan: () => void
  onLogs: () => void
}

/** Back to the city, place an owl, show suggested sites, or open the event log. */
export default function Toolbar({ area, noBake, placing, showPlan, logsOpen, onBack, onPlace, onShowPlan, onLogs }: Props) {
  return (
    <div className="toolbar">
      {area && (
        <button className="tool panel wide" title="Back to the whole city" onClick={onBack}>
          <BackIcon size={18} />
          <span>{area.name}</span>
        </button>
      )}
      {(area || noBake) && (
        <button className={`tool panel ${placing ? 'active' : ''}`} aria-pressed={placing} title={placing ? 'Click the map to place the owl (Esc cancels)' : 'Place an owl (rat camera)'} onClick={onPlace}>
          <PinPlusIcon size={20} />
        </button>
      )}
      {(area || noBake) && (
        <button className={`tool panel ${showPlan ? 'active' : ''}`} aria-pressed={showPlan} title="Suggested owl sites" onClick={onShowPlan}>
          <SparkIcon size={20} />
        </button>
      )}
      <button className={`tool panel ${logsOpen ? 'active' : ''}`} aria-pressed={logsOpen} aria-label="Sightings" title="Sightings" onClick={onLogs}>
        <ListIcon size={20} />
      </button>
    </div>
  )
}
