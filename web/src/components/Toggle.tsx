import { MODES } from '../colours'
import type { Mode, Preset } from '../types'

interface Props {
  mode: Mode
  onMode: (m: Mode) => void
  preset: Preset
  onPreset: (p: Preset) => void
}

const PRESETS: { id: Preset; label: string }[] = [
  { id: 'day', label: 'day' },
  { id: 'night', label: 'night' },
]

export default function Toggle({ mode, onMode, preset, onPreset }: Props) {
  return (
    <div className="toggle">
      <div className="segmented panel" role="radiogroup" aria-label="Colour mode">
        {MODES.map((m) => (
          <button
            key={m.id}
            role="radio"
            aria-checked={mode === m.id}
            className={mode === m.id ? 'active' : ''}
            title={m.hint}
            onClick={() => onMode(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="toggle-sub">
        <span className="chip panel muted">{MODES.find((m) => m.id === mode)?.hint}</span>
        <div className="segmented small panel" role="radiogroup" aria-label="Lighting">
          {PRESETS.map((p) => (
            <button key={p.id} role="radio" aria-checked={preset === p.id} className={preset === p.id ? 'active' : ''} onClick={() => onPreset(p.id)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
