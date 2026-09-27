import type { DashboardCard, DataRow, QueryResult } from './types'

export interface CardView {
  kind?: DashboardCard['kind']
  hidden?: string[]
  sortBy?: string
  sortDirection?: 'asc' | 'desc'
  page?: number
}

const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
type Kind = DashboardCard['kind']

export function visibleSeries(card: DashboardCard, view: CardView): string[] {
  return card.y.filter((key) => !view.hidden?.includes(key))
}

export function availableKinds(card: DashboardCard, result: QueryResult | undefined, view: CardView): Set<Kind> {
  const choices = new Set<Kind>(['table'])
  if (!result?.rows.length) return choices
  const keys = visibleSeries(card, view).filter((key) => result.rows.some((row) => number(row[key])))
  const xPresent = result.rows.some((row) => row[card.x] !== null && row[card.x] !== undefined)
  const xNumeric = result.rows.some((row) => number(row[card.x]))
  const units = card.y.map((key) => result.columns.find((column) => column.key === key)?.unit ?? '')
  const sameUnits = units.every((unit) => unit === units[0])
  if (result.rows.length === 1 && card.y.length === 1 && keys.length === 1) choices.add('metric')
  if (xPresent && keys.length && sameUnits) { choices.add('bar'); choices.add('line') }
  if (xNumeric && keys.length === 1) choices.add('scatter')
  return choices
}

export function resolvedKind(card: DashboardCard, result: QueryResult | undefined, view: CardView): Kind {
  const choices = availableKinds(card, result, view)
  const requested = view.kind ?? card.kind
  return choices.has(requested) ? requested : 'table'
}

export function rowFromChartClick(rows: DataRow[], event: unknown): DataRow | undefined {
  const data = event as { activePayload?: { payload?: DataRow }[]; activeIndex?: number | string | null } | null
  const payload = data?.activePayload?.[0]?.payload
  if (payload) return payload
  const raw = data?.activeIndex
  const index = typeof raw === 'number' ? raw : typeof raw === 'string' && /^(0|[1-9]\d*)$/.test(raw) ? Number(raw) : NaN
  return Number.isSafeInteger(index) && index >= 0 ? rows[index] : undefined
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
