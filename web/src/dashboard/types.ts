export type DataRow = Record<string, string | number | null>
export interface DataQuery {
  dataset: 'cells' | 'backtest' | 'events' | 'sites'
  group_by?: string
  metrics: string[]
  aggregation: 'mean' | 'sum' | 'count' | 'raw'
  borough?: string
  start?: string
  end?: string
  limit?: number
  sort_by?: string
  direction?: 'asc' | 'desc'
}
export interface DataSource {
  label: string
  as_of: string
  kind: 'model' | 'events' | 'fixture'
  notes: string[]
}
export interface QueryResult {
  rows: DataRow[]
  columns: { key: string; label: string; unit: string }[]
  source: DataSource
  total_rows: number
  query: DataQuery
}
export interface DashboardCard {
  id: string
  title: string
  kind: 'bar' | 'line' | 'scatter' | 'table' | 'metric'
  query: DataQuery
  x: string
  y: string[]
  description?: string
}
export interface DashboardSpec {
  title: string
  description: string
  cards: DashboardCard[]
}
export interface DashboardArtifact {
  id: string
  version: number
  created_at: string
  spec: DashboardSpec
  results: Record<string, QueryResult>
}
export interface ChartSelection { card_id: string; field: string; value: string | number }
export interface ChatMessage { role: 'user' | 'assistant'; content: string }
export type DashboardEvent =
  | { type: 'status'; text: string }
  | { type: 'delta'; text: string }
  | { type: 'dashboard'; dashboard: DashboardArtifact }
  | { type: 'done' }
  | { type: 'error'; text: string }
