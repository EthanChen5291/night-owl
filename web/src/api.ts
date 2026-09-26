import cellsFixture from '../../city/cells.fixture.json'
import planFixture from '../../city/plan.fixture.json'
import queueFixture from '../../city/queue.fixture.json'
import type { BacktestResponse, CellsResponse, PlanResponse, QueueResponse, Source, Spot } from './types'

export const API = '/api'

async function getJson<T>(path: string, timeoutMs = 8000): Promise<T> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const res = await fetch(`${API}${path}`, { signal: ctl.signal, headers: { accept: 'application/json' } })
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export interface Loaded<T> {
  data: T
  source: Source
}

async function withFallback<T>(path: string, fixture: T): Promise<Loaded<T>> {
  try {
    return { data: await getJson<T>(path), source: 'live' }
  } catch {
    return { data: fixture, source: 'fixture' }
  }
}

export const fetchCells = (month: string) =>
  withFallback<CellsResponse>(`/cells?month=${encodeURIComponent(month)}`, cellsFixture as CellsResponse)

export const fetchPlan = (month: string, k = 8) =>
  withFallback<PlanResponse>(`/plan?month=${encodeURIComponent(month)}&k=${k}`, planFixture as PlanResponse)

export const fetchQueue = (limit = 20) =>
  withFallback<QueueResponse>(`/queue?limit=${limit}`, queueFixture as QueueResponse)

/** No fixture for /backtest: null means "backtest not available". */
export async function fetchBacktest(): Promise<BacktestResponse | null> {
  try {
    return await getJson<BacktestResponse>('/backtest')
  } catch {
    return null
  }
}

/** Optional static city bake (public/city/*.json). Missing files resolve to null, silently. */
export async function fetchPublic<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(path, { headers: { accept: 'application/json' } })
    if (!res.ok) return null
    const type = res.headers.get('content-type') ?? ''
    if (!type.includes('json')) return null // Vite dev serves index.html for unknown paths
    return (await res.json()) as T
  } catch {
    return null
  }
}

/** Node spot options inside one hexagon; empty when the API or its placements file is missing. */
export async function fetchPlacements(h3: string): Promise<Spot[]> {
  try {
    return (await getJson<{ spots: Spot[] }>(`/placements?h3=${encodeURIComponent(h3)}`)).spots ?? []
  } catch {
    return []
  }
}
