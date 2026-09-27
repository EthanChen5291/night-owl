import type { ReactElement } from 'react'
import { MODES, valueFor } from '../colours'
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

/** A chip above the cursor: the address (or what would happen on click), the cell's score underneath. */
export default function HoverTip({ info, mode, cell, node, area, placing }: Props) {
  let icon: ReactElement | null = null
  let title: string
  if (placing) {
    icon = <PinPlusIcon size={14} />
    title = info.addr ? `Place owl · ${info.addr}` : 'Place owl here'
  } else if (info.kind === 'node' && node) {
    icon = <OwlIcon size={14} />
    title = `${node.name} · ${node.addr}`
  } else if (info.kind === 'plan') {
    icon = <SparkIcon size={14} />
    title = `Suggested site #${info.planRank} · click to see street trees`
  } else if (info.kind === 'spot') {
    icon = <PinPlusIcon size={14} />
    title = `Tree ${String.fromCharCode(64 + (info.spotRank ?? 1))} · ${info.addr ?? ''} · click to place an owl`
  } else if (info.kind === 'area' && area) {
    title = `${area.name} · click to fly there`
  } else if (info.addr) {
    title = info.kind === 'street' ? `near ${info.addr}` : info.addr
  } else {
    title = cell?.neighborhood ?? 'Block'
  }
  const v = cell ? valueFor(mode, cell) : null
  const label = mode === 'silence' ? 'silence' : (MODES.find((m) => m.id === mode)?.label.toLowerCase() ?? '')
  return (
    <div className="hovertip panel" style={{ left: info.x, top: info.y - 14 }}>
      <div className="hovertip-title">
        {icon}
        <span>{title}</span>
      </div>
      {v !== null && (
        <div className="hovertip-sub muted">
          {label} <b>{mode === 'silence' ? (v > 0 ? '+' : '') + v.toFixed(0) : `${v.toFixed(0)} / 100`}</b>
          {cell && cell.posterior.n_events > 0 && <span> · {cell.posterior.n_events} sighting{cell.posterior.n_events === 1 ? '' : 's'}</span>}
        </div>
      )}
    </div>
  )
}
