import type { ReactElement } from 'react'
import { MODES } from '../colours'
import type { Mode, Preset } from '../types'
import { HomeIcon, MoonIcon, SignalIcon, SilenceIcon, SunIcon } from './Icons'

interface Props {
  mode: Mode
  onMode: (m: Mode) => void
  preset: Preset
  onPreset: (p: Preset) => void
}

const ICONS: Record<Mode, (p: { size?: number }) => ReactElement> = { a: HomeIcon, b: SignalIcon, silence: SilenceIcon }

/** Top centre: the three views as icons, the active one named underneath, day/night beside it. */
export default function ModeBar({ mode, onMode, preset, onPreset }: Props) {
  const active = MODES.find((m) => m.id === mode)
  return (
    <div className="modebar">
      <div className="modebar-row">
        <div className="segmented icons panel" role="radiogroup" aria-label="View">
          {MODES.map((m) => {
            const Icon = ICONS[m.id]
            return (
              <button key={m.id} role="radio" aria-checked={mode === m.id} aria-label={m.label} className={mode === m.id ? 'active' : ''} title={`${m.label} · ${m.hint}`} onClick={() => onMode(m.id)}>
                <Icon size={20} />
              </button>
            )
          })}
        </div>
        <div className="segmented icons panel" role="radiogroup" aria-label="Lighting">
          <button role="radio" aria-checked={preset === 'day'} aria-label="Day" className={preset === 'day' ? 'active' : ''} title="Day" onClick={() => onPreset('day')}>
            <SunIcon size={18} />
          </button>
          <button role="radio" aria-checked={preset === 'night'} aria-label="Night" className={preset === 'night' ? 'active' : ''} title="Night" onClick={() => onPreset('night')}>
            <MoonIcon size={18} />
          </button>
        </div>
      </div>
      <div className="chip panel modebar-hint">
        <b>{active?.label}</b>
        <span className="muted"> · {active?.hint}</span>
      </div>
    </div>
  )
}
