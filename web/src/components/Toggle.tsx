import { MODES } from '../colours'
import type { Mode, Preset } from '../types'

interface Props {
  mode: Mode
  onMode: (m: Mode) => void
  preset: Preset
  onPreset: (p: Preset) => void
}

export default function Toggle({ mode, onMode, preset, onPreset }: Props) {
  return (
    <div className="toggle panel">
      <div className="toggle-row" role="radiogroup" aria-label="Colour mode">
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
      <div className="toggle-hint">{MODES.find((m) => m.id === mode)?.hint}</div>
      <div className="toggle-row small">
        <span className="muted">lighting</span>
        <button className={preset === 'night' ? 'active' : ''} onClick={() => onPreset('night')}>
          night
        </button>
        <button className={preset === 'flat' ? 'active' : ''} onClick={() => onPreset('flat')}>
          flat
        </button>
      </div>
    </div>
  )
}
