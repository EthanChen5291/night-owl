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

/** A node spot inside a ranked hexagon (model/09_placements.py, GET /placements?h3=): a street tree to mount on. */
export interface Spot {
  rank: number
  spot_h3: string
  lat: number
  lon: number
  tree_id: string
  mount_address: string
  score: number
  reasons: string[]
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

// ---------------------------------------------------------------- city bake (city/build_city.py, city/make_tiles.py)

export interface Building {
  id: string
  h3: string
  footprint: [number, number][]
  height: number
  addr?: string // PLUTO address of the lot
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
  addr?: string // the street address the tree pit fronts
}

/** The citywide flat layers; a missing file just leaves that layer out. */
export interface CityLayers {
  land: Poly[] | null
  parks: Poly[] | null
  water: Poly[] | null
}

/** One r7 hex tile of the city: streamed in around the camera, dropped when it drifts away. */
export interface Tile {
  id: string
  buildings: Building[]
  roads: Poly[]
  trees: Tree[]
}

export interface TilesManifest {
  res: number
  centre: { lat: number; lon: number }
  tiles: Record<string, { b: number; r: number; t: number; a?: string | null }> // a: the area (borough) the tile belongs to
}

/** A city area (borough) the camera can fly to; only a starting point, tiles stream anywhere. */
export interface Area {
  id: string
  name: string
  lat: number
  lon: number
  outline: [number, number][] // borough shape in local metres
}

export interface AreasManifest {
  centre: { lat: number; lon: number }
  areas: Area[]
}

export interface CityMeta {
  centre: { lat: number; lon: number }
  counts?: Record<string, number>
}

// ---------------------------------------------------------------- owls (placed sensor nodes, kept in localStorage)

export interface OwlNode {
  id: string // owl-1, owl-2, ...
  nodeId: string // the node_id the Pi posts (the first owl takes demo-01 so the stage node lands on it)
  name: string // Owl 1
  lat: number
  lon: number
  h3: string
  addr: string
  placedAt: string
  treeId?: string
}

/** What the pointer is over, from the scene. x/y are client pixels. */
export interface HoverInfo {
  x: number
  y: number
  lat: number
  lon: number
  h3: string | null
  addr: string | null
  kind: 'cell' | 'building' | 'street' | 'node' | 'plan' | 'spot' | 'area' | 'ground'
  nodeId?: string
  planRank?: number
  spotRank?: number
  cellHit?: boolean // the pointer is on a prism (only from far enough away that the prisms are the thing you point at)
  areaId?: string
}

/** Where the camera is looking, reported by the scene as it moves. */
export interface ViewInfo {
  lat: number
  lon: number
  distance: number
}
