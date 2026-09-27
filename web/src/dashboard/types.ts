export type DataRow = Record<string, string | number | null>
export interface DataQuery {
  dataset: string
  group_by?: string
  split_by?: string
  metrics: string[]
  aggregation: 'mean' | 'sum' | 'count' | 'raw'
  borough?: string
  filters?: Record<string, string | number | (string | number)[]>
  start?: string
  end?: string
  limit?: number
  sort_by?: string
  direction?: 'asc' | 'desc'
}
export interface DataSource {
  label: string
  as_of: string
  kind: 'model' | 'events' | 'fixture' | 'history'
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
/** One finished tool step in an assistant turn: a query or the dashboard build. */
export interface AgentStep { text: string; detail?: string; error?: boolean }
export type DashboardEvent =
  | { type: 'status'; text: string }
  | { type: 'step'; text: string; detail?: string; error?: boolean }
  | { type: 'thinking'; text: string }
  | { type: 'delta'; text: string }
  | { type: 'dashboard'; dashboard: DashboardArtifact }
  | { type: 'done' }
  | { type: 'error'; text: string }
