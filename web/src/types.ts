// The frozen JSON contract (plan/master-plan.md §6). Field names are the wire names.

export interface Reason {
  feature: string
  shap: number
}

export interface Posterior {
  alpha: number
  beta: number
  n_events: number
}

export interface Cell {
  h3: string
  score_a: number
  score_b: number
  pct_a: number
  pct_b: number
  silence: number
  ci_b: [number, number]
  posterior: Posterior
  reasons: Reason[]
  cd: string
  rmz: string | null
  n_inspections: number
  last_event_at: string | null
}

export interface CellsResponse {
  month: string
  generated_at: string
  cells: Cell[]
}

export interface PlanNode {
  rank: number
  h3: string
  lat: number
  lon: number
  tree_id: string
  expected_gain: number
  silence: number
  reason: string
}

export interface PlanResponse {
  month: string
  k: number
  nodes: PlanNode[]
}

export interface RatEvent {
  node_id: string
  h3: string
  ts: string
  class: string
  conf: number
  n_hits: number
  bbox: [number, number, number, number]
  crop_b64: string
  fw: string
  received_at?: string
}

export interface QueueResponse {
  events: RatEvent[]
}

export interface BacktestPoint {
  month: string
  precision_silent: number
  precision_311: number
  n_positives: number
}

export interface BacktestResponse {
  window: string[]
  k: number
  series: BacktestPoint[]
  summary: Record<string, number | string>
  synthetic: boolean
}

export type Mode = 'a' | 'b' | 'silence'
export type Preset = 'day' | 'night'
export type Source = 'live' | 'fixture'

// Shapes of city/build_city.py's outputs, served from public/city/ when present.
export interface Building {
  id: string
  h3: string
  footprint: [number, number][]
  height: number
}

/** One exterior ring of a flat layer (land, roads, parks, water), local metres. */
export interface Poly {
  id: string
  ring: [number, number][]
}

export interface Tree {
  id: string
  x: number
  y: number
  h3: string
}

/** The optional flat layers under the buildings; a missing file just leaves that layer out. */
export interface CityLayers {
  land: Poly[] | null
  roads: Poly[] | null
  parks: Poly[] | null
  water: Poly[] | null
  trees: Tree[] | null
}

export interface CityMeta {
  centre: { lat: number; lon: number }
  counts?: Record<string, number>
}
