import type { OwlNode, PlanNode, RatEvent, Source, Spot } from '../types'
import Gauge from './Gauge'
import { ChevronIcon, OwlIcon, PinPlusIcon, SparkIcon, TrashIcon } from './Icons'

interface Props {
  nodes: OwlNode[]
  sightings: Map<string, RatEvent[]> // by owl id, newest first
  rates: Map<string, number> // by owl id, 0..1
  selected: string | null
  plan: PlanNode[]
  openRank: number | null
  openSpots: Spot[] | undefined // undefined while loading
  onOpenRank: (rank: number | null) => void
  onFlySpot: (spot: Spot) => void
  onPlaceSpot: (spot: Spot) => void
  onPlacePlan: (site: PlanNode) => void
  inArea: boolean
  source: Source
  streaming: boolean
  open: boolean
  onToggle: () => void
  onSelect: (id: string | null) => void
  onRemove: (id: string) => void
  onStartPlacing: () => void
}

const titleCase = (s: string) => s.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase())

const ago = (iso: string | undefined) => {
  if (!iso) return 'never'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${Math.round(s)}s ago`
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

/** Right side: one card per owl with its activity ring around a node icon; suggested sites underneath. Slides away on its tab. */
export default function NodesPanel({ nodes, sightings, rates, selected, plan, openRank, openSpots, onOpenRank, onFlySpot, onPlaceSpot, onPlacePlan, inArea, source, streaming, open, onToggle, onSelect, onRemove, onStartPlacing }: Props) {
  const placedCells = new Set(nodes.map((n) => n.h3))
  return (
    <aside className={`nodes panel ${open ? '' : 'collapsed'}`}>
      <button className="tab tab-left" onClick={onToggle} title={open ? 'Hide owls' : 'Show owls'} aria-expanded={open}>
        <ChevronIcon size={16} dir={open ? 'right' : 'left'} />
      </button>
      <div className="nodes-head">
        <span className="nodes-title">
          <OwlIcon size={18} />
          Owls
          <span className="count">{nodes.length}</span>
        </span>
        <span className={`pill ${source === 'live' ? 'live' : 'fixture'}`}>{source === 'live' ? (streaming ? 'streaming' : 'polling') : source}</span>
      </div>
      <div className="nodes-body">
        {nodes.length === 0 && (
          <button className="empty" onClick={onStartPlacing} disabled={!inArea}>
            <PinPlusIcon size={22} />
            <span>{inArea ? 'No owls yet. Place one on the map.' : 'Fly into an area to place owls.'}</span>
          </button>
        )}
        <ul className="owl-list">
          {nodes.map((n) => {
            const s = sightings.get(n.id) ?? []
            const last = s[0]
            return (
              <li key={n.id} className={`owl ${selected === n.id ? 'selected' : ''}`} onClick={() => onSelect(selected === n.id ? null : n.id)}>
                <Gauge value={rates.get(n.id) ?? 0} label={s.length} />
                <div className="owl-text">
                  <div className="owl-row">
                    <b>{n.name}</b>
                    <button className="icon-btn" title="Remove owl" aria-label={`Remove ${n.name}`} onClick={(e) => (e.stopPropagation(), onRemove(n.id))}>
                      <TrashIcon size={15} />
                    </button>
                  </div>
                  <div className="owl-addr">{n.addr}</div>
                  <div className="owl-row small muted">
                    <span>{last ? `last event ${ago(last.ts)}` : 'no events'}</span>
                    <span>{n.nodeId}</span>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
        {inArea && (
          <div className="suggested">
            <div className="suggested-head muted small">
              <SparkIcon size={14} /> suggested sites
            </div>
            {plan.length === 0 && <div className="small muted">No suggested sites for this view.</div>}
            <ul className="owl-list compact">
              {plan.map((p) => {
                const isOpen = openRank === p.rank
                return (
                  <li key={p.rank} className={`owl compact ${placedCells.has(p.h3) ? 'done' : ''} ${isOpen ? 'open' : ''}`} onClick={() => onOpenRank(isOpen ? null : p.rank)} title={p.reason}>
                    <span className="rank">{p.rank}</span>
                    <div className="owl-text">
                      <div className="owl-row">
                        <b>silence {p.silence > 0 ? '+' : ''}{Math.round(p.silence)}</b>
                        <span className="muted small">gain {p.expected_gain.toFixed(2)}</span>
                      </div>
                      <div className="small muted">{placedCells.has(p.h3) ? 'owl placed' : isOpen ? 'spots inside this hexagon' : 'click for spots inside this hexagon'}</div>
                      {isOpen && !placedCells.has(p.h3) && <button className="plan-place" onClick={(e) => (e.stopPropagation(), onPlacePlan(p))}>Place at planned tree</button>}
                      {isOpen && (
                        <ul className="spots" onClick={(e) => e.stopPropagation()}>
                          {openSpots === undefined && <li className="small muted">finding street trees…</li>}
                          {openSpots && openSpots.length === 0 && <li className="small muted">no spots scored for this hexagon</li>}
                          {openSpots?.map((s, i) => (
                            <li key={s.rank} className="spot" onClick={() => onFlySpot(s)} title={s.reasons.join(' · ')}>
                              <span className="spot-letter">{String.fromCharCode(65 + i)}</span>
                              <div className="owl-text">
                                <div className="owl-row">
                                  <b>{titleCase(s.mount_address)}</b>
                                  <span className="muted small">{Math.round(s.score * 100)}</span>
                                </div>
                                <div className="small muted">{s.reasons.slice(0, 2).join(' · ')}</div>
                              </div>
                              <button className="icon-btn" title="Place an owl on this tree" aria-label={`Place an owl at ${s.mount_address}`} onClick={(e) => (e.stopPropagation(), onPlaceSpot(s))}>
                                <PinPlusIcon size={15} />
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>
    </aside>
  )
}
