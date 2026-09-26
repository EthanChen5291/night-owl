import type { ReactElement } from 'react'
import { valueFor } from '../colours'
import type { Area, Cell, HoverInfo, Mode, OwlNode } from '../types'
import { OwlIcon, PinPlusIcon, SparkIcon } from './Icons'

interface Props {
  info: HoverInfo
  mode: Mode
  cell: Cell | undefined
  node: OwlNode | undefined
  area: Area | undefined
  placing: boolean
}

const MODE_UNIT: Record<Mode, string> = { a: 'city sees', b: "what's there", silence: 'silence' }

/** A chip above the cursor: the address (or what would happen on click), the cell's value underneath. */
export default function HoverTip({ info, mode, cell, node, area, placing }: Props) {
  let icon: ReactElement | null = null
  let title: string
  if (placing) {
    icon = <PinPlusIcon size={14} />
    title = info.addr ? `Place owl · ${info.addr}` : 'Place owl here'
  } else if (info.kind === 'node' && node) {
    icon = <OwlIcon size={14} />
    title = `${node.name} · ${node.addr} · click to fly there`
  } else if (info.kind === 'plan') {
    icon = <SparkIcon size={14} />
    title = `Suggested hexagon #${info.planRank} · click for spots inside it`
  } else if (info.kind === 'spot') {
    icon = <PinPlusIcon size={14} />
    title = `Spot ${String.fromCharCode(64 + (info.spotRank ?? 1))} · ${info.addr ?? ''} · click to place an owl`
  } else if (info.kind === 'area' && area) {
    title = `${area.name} · click to fly there`
  } else if (info.addr) {
    title = info.kind === 'street' ? `near ${info.addr}` : info.addr
  } else {
    title = info.h3 ?? ''
  }
  const v = cell ? valueFor(mode, cell) : null
  return (
    <div className="hovertip panel" style={{ left: info.x, top: info.y - 14 }}>
      <div className="hovertip-title">
        {icon}
        <span>{title}</span>
      </div>
      {v !== null && (
        <div className="hovertip-sub muted">
          {MODE_UNIT[mode]} <b>{mode === 'silence' ? (v > 0 ? '+' : '') + v.toFixed(0) : v.toFixed(0) + '%'}</b>
          {cell && cell.posterior.n_events > 0 && <span> · {cell.posterior.n_events} sightings</span>}
        </div>
      )}
    </div>
  )
}
