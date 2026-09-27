import type { Cell, OwlNode, RatEvent } from '../types'
import { CloseIcon, RatIcon } from './Icons'

interface Props {
  events: RatEvent[] // newest first
  nodes: OwlNode[]
  cells: Map<string, Cell> // for an owl outside the borough you are in: its neighbourhood instead of a raw cell id
  selected: string | null
  onClose: () => void
  onSelect: (id: string) => void
}

const fmt = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

/** Queue events with crops, locations, and times; filtered to the selected owl. */
export default function LogsDrawer({ events, nodes, cells, selected, onClose, onSelect }: Props) {
  const placeOf = (h3: string) => {
    const c = cells.get(h3)
    return c?.neighborhood ? `${c.neighborhood}${c.borough ? `, ${c.borough}` : ''}` : `block ${h3.slice(-5)}`
  }
  const byNodeId = new Map(nodes.map((n) => [n.nodeId, n]))
  const owl = selected ? nodes.find((n) => n.id === selected) : null
  const rows = owl ? events.filter((e) => e.node_id === owl.nodeId) : events
  return (
    <section className="logs panel">
      <div className="logs-head">
        <span className="nodes-title">
          <RatIcon size={20} />
          Events
          <span className="count">{rows.length}</span>
          {owl && <span className="muted small"> · {owl.name}</span>}
        </span>
        <button className="icon-btn" onClick={onClose} aria-label="Close log">
          <CloseIcon size={16} />
        </button>
      </div>
      {rows.length === 0 && <div className="muted logs-empty">No events yet. Queue events and their crops appear here.</div>}
      <ul className="logs-list">
        {rows.map((e) => {
          const n = byNodeId.get(e.node_id)
          return (
            <li key={`${e.node_id}|${e.ts}`} className="log" onClick={() => n && onSelect(n.id)}>
              {e.crop_b64 ? <img className="log-crop" alt="event crop" src={`data:image/jpeg;base64,${e.crop_b64}`} /> : <div className="log-crop empty" />}
              <div className="log-text">
                <div className="owl-row">
                  <b>{n?.name ?? e.node_id}</b>
                  <span className="muted small">{fmt(e.ts)}</span>
                </div>
                <div className="owl-addr">{n?.addr ?? placeOf(e.h3)}</div>
                <div className="small muted">
                  {e.class} · {Math.round(e.conf * 100)}% · {e.n_hits} frames
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
