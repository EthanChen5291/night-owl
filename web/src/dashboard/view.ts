import type { DashboardCard, DataRow, QueryResult } from './types'

export interface CardView {
  kind?: DashboardCard['kind']
  hidden?: string[]
  sortBy?: string
  sortDirection?: 'asc' | 'desc'
  page?: number
}

const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

export function visibleSeries(card: DashboardCard, view: CardView): string[] {
  return card.y.filter((key) => !view.hidden?.includes(key))
}

export function resolvedKind(card: DashboardCard, result: QueryResult | undefined, view: CardView): DashboardCard['kind'] {
  if (!result?.rows.length) return card.kind
  const keys = visibleSeries(card, view).filter((key) => result.rows.some((row) => number(row[key])))
  const xPresent = result.rows.some((row) => row[card.x] !== null && row[card.x] !== undefined)
  const xNumeric = result.rows.some((row) => number(row[card.x]))
  const requested = view.kind ?? card.kind
  if (requested === 'table') return 'table'
  if (requested === 'metric' && result.rows.length === 1 && keys.length) return 'metric'
  if (requested === 'scatter' && xNumeric && keys.length === 1) return 'scatter'
  if ((requested === 'bar' || requested === 'line') && xPresent && keys.length) return requested
  return 'table'
}

export function sortedRows(rows: DataRow[], view: CardView): DataRow[] {
  if (!view.sortBy) return rows
  const direction = view.sortDirection === 'desc' ? -1 : 1
  return [...rows].sort((a, b) => {
    const left = a[view.sortBy!]
    const right = b[view.sortBy!]
    if (left == null) return right == null ? 0 : 1
    if (right == null) return -1
    if (typeof left === 'number' && typeof right === 'number') return direction * (left - right)
    return direction * String(left).localeCompare(String(right), undefined, { numeric: true })
  })
}
