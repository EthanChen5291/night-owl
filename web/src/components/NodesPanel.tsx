import type { OwlNode, PlanNode, RatEvent, Spot } from '../types'
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
  planBudget: number
  onPlanBudget: (k: number) => void
  open: boolean
  onToggle: () => void
  onSelect: (id: string | null) => void
  onRemove: (id: string) => void
  onStartPlacing: () => void
}

const titleCase = (s: string) => s.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase())

// The planner's reason string ends in "mount: <ADDRESS>"; that address is the one thing a person wants to see.
const mountOf = (p: PlanNode) => {
  const m = /mount:\s*(.+)$/i.exec(p.reason)
  return m ? titleCase(m[1].trim()) : null
}

const ago = (iso: string | undefined) => {
  if (!iso) return 'never'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${Math.round(s)}s ago`
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

/** Right side: one card per owl with its activity ring around a node icon; suggested sites underneath. Slides away on its tab. */
export default function NodesPanel({ nodes, sightings, rates, selected, plan, openRank, openSpots, onOpenRank, onFlySpot, onPlaceSpot, onPlacePlan, inArea, planBudget, onPlanBudget, open, onToggle, onSelect, onRemove, onStartPlacing }: Props) {
  const placedCells = new Set(nodes.map((n) => n.h3))
  return (
    <aside className={`nodes panel ${open ? '' : 'collapsed'}`}>
      <button className="tab tab-left" onClick={onToggle} title={open ? 'Hide owls' : 'Owls: your rat cameras'} aria-expanded={open}>
        <ChevronIcon size={16} dir={open ? 'right' : 'left'} />
      </button>
      <div className="nodes-head">
        <span className="nodes-title">
          <OwlIcon size={18} />
          Owls
          <span className="count">{nodes.length}</span>
          <span className="muted small nodes-sub">rat cameras</span>
        </span>
      </div>
      <div className="nodes-body">
        {nodes.length === 0 && (
          <button className="empty" onClick={onStartPlacing} disabled={!inArea}>
            <PinPlusIcon size={22} />
            <span>{inArea ? 'No owls yet. Click here, then click a spot on the map.' : 'Fly into a borough to place an owl.'}</span>
          </button>
        )}
        <ul className="owl-list">
          {nodes.map((n) => {
            const s = sightings.get(n.id) ?? []
            const last = s[0]
            return (
              <li key={n.id} className={`owl owl-card ${selected === n.id ? 'selected' : ''}`}>
                <button type="button" className="owl-select" aria-label={`Fly to ${n.name}`} aria-pressed={selected === n.id} onClick={() => onSelect(selected === n.id ? null : n.id)}>
                  <Gauge value={rates.get(n.id) ?? 0} label={s.length} />
                  <div className="owl-text">
                    <div className="owl-row"><b>{n.name}</b></div>
                    <div className="owl-addr">{n.addr}</div>
                    <div className="owl-row small muted">
                      <span>{last ? `last sighting ${ago(last.ts)}` : 'no sightings yet'}</span>
                    </div>
                  </div>
                </button>
                <button type="button" className="icon-btn owl-remove" title="Remove owl" aria-label={`Remove ${n.name}`} onClick={() => onRemove(n.id)}>
                  <TrashIcon size={15} />
                </button>
              </li>
            )
          })}
        </ul>
        {inArea && (
          <div className="suggested">
            <div className="suggested-head muted small">
              <SparkIcon size={14} /> suggested sites
              <select className="budget-select" aria-label="How many suggested sites" value={planBudget} onChange={(e) => onPlanBudget(Number(e.target.value))}>
                {[5, 10, 20].map((k) => <option key={k} value={k}>top {k}</option>)}
              </select>
            </div>
            {plan.length === 0 && <div className="small muted">No suggested sites here.</div>}
            <ul className="owl-list compact">
              {plan.map((p) => {
                const isOpen = openRank === p.rank
                return (
                  <li key={p.rank} className={`owl compact ${placedCells.has(p.h3) ? 'done' : ''} ${isOpen ? 'open' : ''}`} onClick={() => onOpenRank(isOpen ? null : p.rank)} title={p.reason}>
                    <span className="rank">{p.rank}</span>
                    <div className="owl-text">
                      <div className="owl-row">
                        <b>{mountOf(p) ?? `Site ${p.rank}`}</b>
                        <span className="muted small">silence {p.silence > 0 ? '+' : ''}{Math.round(p.silence)}</span>
                      </div>
                      <div className="small muted">{placedCells.has(p.h3) ? 'owl placed' : isOpen ? 'street trees to mount on' : 'click for street trees to mount on'}</div>
                      {isOpen && !placedCells.has(p.h3) && <button className="plan-place" onClick={(e) => (e.stopPropagation(), onPlacePlan(p))}>Place at planned tree</button>}
                      {isOpen && (
                        <ul className="spots" onClick={(e) => e.stopPropagation()}>
                          {openSpots === undefined && <li className="small muted">finding street trees…</li>}
                          {openSpots && openSpots.length === 0 && <li className="small muted">no street trees scored here</li>}
                          {openSpots?.map((s, i) => (
                            <li key={s.rank} className="spot" onClick={() => onFlySpot(s)} title={s.reasons.join(' · ')}>
                              <span className="spot-letter">{String.fromCharCode(65 + i)}</span>
                              <div className="owl-text">
                                <div className="owl-row">
                                  <b>{titleCase(s.mount_address)}</b>
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
