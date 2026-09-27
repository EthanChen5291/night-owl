import { useState } from 'react'
import { colourFor } from '../colours'
import type { Cell, Mode } from '../types'
import { CloseIcon } from './Icons'

interface Props {
  cell: Cell
  mode: Mode
  addr: string | null
  city: { avgB: number; avgPerYear: number } // citywide averages, so a number on this card has something to stand against
  onClose: () => void
}

// Model feature ids -> what a person would call them.
const REASON_NAMES: Record<string, string> = {
  trash_bins_required: 'trash bin rules',
  building_height: 'building height',
  building_age: 'building age',
  pre_1940_buildings: 'pre-1940 buildings',
  median_income: 'median income',
  street_trees: 'street trees',
  many_properties: 'many small lots',
  restaurants: 'restaurants',
  demolitions: 'demolitions',
  litter_baskets: 'litter baskets',
  catch_basins: 'storm drains',
}
const reasonName = (id: string) => REASON_NAMES[id] ?? id.replace(/_/g, ' ')
const fmt = (v: number, d = 0) => (Number.isFinite(v) ? v.toFixed(d) : '-')
const pct = (v: number) => `${Math.round(v * 100)}%`

// Community district codes are borough digit + two-digit district: "112" is Manhattan CD 12.
const BOROUGHS: Record<string, string> = { '1': 'Manhattan', '2': 'Bronx', '3': 'Brooklyn', '4': 'Queens', '5': 'Staten Island' }
const districtName = (cd: string) => (cd && BOROUGHS[cd[0]] ? `${BOROUGHS[cd[0]]} CD ${Number(cd.slice(1))}` : cd)

const ago = (iso: string) => {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

function Bar({ label, value, tone }: { label: string; value: number; tone: 'a' | 'b' | 'silence' }) {
  const w = Math.max(0, Math.min(100, Math.abs(value)))
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-bar">
        <span className={`stat-fill ${tone} ${value < 0 ? 'neg' : ''}`} style={{ width: `${w}%` }} />
      </span>
      <b className="stat-val">{tone === 'silence' ? (value > 0 ? '+' : '') + fmt(value) : fmt(value)}</b>
    </div>
  )
}

/** Pinned by clicking a cell: the three scores as bars, sightings from owls, and why the model thinks so. */
export default function CellPopup({ cell, mode, addr, city, onClose }: Props) {
  const maxShap = Math.max(1e-6, ...cell.reasons.map((r) => Math.abs(r.shap)))
  const place = [cell.neighborhood, cell.borough].filter(Boolean).join(', ')
  const n = cell.posterior.n_events
  const [more, setMore] = useState(false)
  const perYear = cell.score_a * 12
  const times = (v: number, avg: number) => (avg > 0 ? `${(v / avg).toFixed(1)}× the city average` : '')
  const estimate = cell.posterior.alpha / (cell.posterior.alpha + cell.posterior.beta) // Beta-Binomial mean: the model's prior moved by sightings
  return (
    <div className="cellcard panel">
      <div className="cellcard-head">
        <span className="swatch" style={{ background: colourFor(mode, cell) }} />
        <div className="cellcard-title">
          <b>{addr ?? cell.neighborhood ?? 'This block'}</b>
          {place && addr && <span className="muted small">{place}</span>}
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <CloseIcon size={15} />
        </button>
      </div>
      <Bar label="Complaints" value={cell.pct_a} tone="a" />
      <Bar label="Likelihood of rats" value={cell.pct_b} tone="b" />
      <Bar label="Silence" value={cell.silence} tone="silence" />
      <div className="muted small cellcard-hint">Scores out of 100, ranked against every block in the city. Silence is how far rats outrun complaints.</div>
      <div className="cellcard-detail small">
        <span>Owl sightings</span>
        <b>{n === 0 ? 'none yet' : `${n}${cell.last_event_at ? `, last ${ago(cell.last_event_at)}` : ''}`}</b>
      </div>
      <button className="cellcard-more" onClick={() => setMore((m) => !m)} aria-expanded={more}>
        {more ? 'Hide details' : 'Details'}
      </button>
      {more && (
        <div className="cellcard-more-body small">
          <div className="cellcard-detail"><span>311 rat complaints, expected</span><b>{perYear < 0.5 ? 'under 1 a year' : `about ${Math.round(perYear)} a year`}</b></div>
          <div className="cellcard-detail"><span></span><span className="muted">{times(perYear, city.avgPerYear)}</span></div>
          <div className="cellcard-detail"><span>Chance an inspection finds rats</span><b>{pct(cell.score_b)}</b></div>
          <div className="cellcard-detail"><span></span><span className="muted">{times(cell.score_b, city.avgB)}; likely between {pct(cell.ci_b[0])} and {pct(cell.ci_b[1])}</span></div>
          {n > 0 && <div className="cellcard-detail"><span>Updated by {n} owl sighting{n === 1 ? '' : 's'}</span><b>{pct(estimate)}</b></div>}
          <div className="cellcard-detail"><span>City inspections here</span><b>{cell.n_inspections === 0 ? 'none on record' : cell.n_inspections}</b></div>
          <div className="cellcard-detail"><span>Rat mitigation zone</span><b>{cell.rmz ? 'yes' : 'no'}</b></div>
          <div className="cellcard-detail"><span>Community district</span><b>{districtName(cell.cd)}</b></div>
        </div>
      )}
      {cell.reasons.length > 0 && (
        <div className="popup-reasons">
          <div className="muted small">Why the model thinks so</div>
          {cell.reasons.slice(0, 3).map((r) => (
            <div key={r.feature} className="reason" title={r.shap >= 0 ? 'raises the likelihood' : 'lowers the likelihood'}>
              <span className="reason-name">{reasonName(r.feature)}</span>
              <span className="reason-bar">
                <span className={r.shap >= 0 ? 'pos' : 'neg'} style={{ width: `${(Math.abs(r.shap) / maxShap) * 100}%` }} />
              </span>
              <span className="reason-val">{r.shap >= 0 ? '▲' : '▼'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
