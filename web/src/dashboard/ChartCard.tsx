import { useMemo, useSyncExternalStore, type CSSProperties } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import { BarIcon, InfoIcon, LineIcon, MetricIcon, ScatterIcon, TableIcon } from './icons'
import type { ChartSelection, DashboardCard, DataRow, QueryResult } from './types'
import { availableKinds, resolvedKind, rowFromChartClick, sortedRows, visibleSeries, type CardView } from './view'

interface Props {
  card: DashboardCard
  result?: QueryResult
  view: CardView
  selection: ChartSelection | null
  index: number
  onView: (view: CardView) => void
  onSelect: (selection: ChartSelection) => void
}

// Series colours in a fixed order: owl amber, then blue, green, violet. Both lists pass the
// dataviz palette validator (lightness band, chroma, CVD and normal-vision separation, 3:1
// contrast) against the light and dark card surfaces. A card has at most three series.
const LIGHT = ['#c8731e', '#2f6fae', '#2a9a70', '#8a63c9', '#c2477a', '#4e8f9c']
const DARK = ['#cf7f30', '#4585cc', '#3fa060', '#8f74d4', '#d0608f', '#5ea3b0']
const KIND_LABEL: Record<DashboardCard['kind'], string> = { bar: 'Bar', line: 'Line', scatter: 'Scatter', table: 'Table', metric: 'Value' }
const ORDER: DashboardCard['kind'][] = ['bar', 'line', 'scatter', 'metric', 'table']
const KIND_ICON = { bar: BarIcon, line: LineIcon, scatter: ScatterIcon, table: TableIcon, metric: MetricIcon }
const SOURCE_LABEL = { fixture: 'Sample data', events: 'Event data', model: 'Model data', history: 'NYC Open Data' } as const
const PLOT_HEIGHT = 220

const darkQuery = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null
const subscribeDark = (notify: () => void) => { darkQuery?.addEventListener('change', notify); return () => darkQuery?.removeEventListener('change', notify) }
const useDark = () => useSyncExternalStore(subscribeDark, () => darkQuery?.matches ?? false, () => false)

const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const isFraction = (unit: string) => unit === 'probability' || unit === 'fraction'
const valueFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 })
const largeTickFormat = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 })
const compact = (value: number) => valueFormat.format(value)
const compactTick = (value: number) => Math.abs(value) >= 1000 ? largeTickFormat.format(value) : valueFormat.format(value)
const unitLabel = (unit: string) => isFraction(unit) ? '%' : unit === 'percentile 0–100' ? 'percentile' : unit === 'year' ? '' : unit

function axisTick(value: string | number | null, unit = ''): string {
  if (value === null) return ''
  if (unit === 'year') return String(value)
  if (typeof value === 'number') return `${compactTick(isFraction(unit) ? value * 100 : value)}${isFraction(unit) || unit === '%' ? '%' : ''}`
  return value.length > 14 ? `${value.slice(0, 13)}…` : value
}

function display(value: string | number | null | undefined, unit = ''): string {
  if (value === null || value === undefined) return '—'
  if (typeof value !== 'number') return value
  if (unit === 'year') return String(value)
  if (isFraction(unit)) return `${compact(value * 100)}%`
  return `${compact(value)}${unit === '%' ? '%' : unit ? ` ${unitLabel(unit)}` : ''}`
}

interface TipProps {
  active?: boolean
  label?: unknown
  payload?: readonly { name?: unknown; value?: unknown; color?: string; payload?: DataRow }[]
}

export default function ChartCard({ card, result, view, selection, index, onView, onSelect }: Props) {
  const colors = useDark() ? DARK : LIGHT
  const columns = result?.columns ?? []
  const label = (key: string) => columns.find((column) => column.key === key)?.label ?? key
  const unit = (key: string) => columns.find((column) => column.key === key)?.unit ?? ''
  const rows = useMemo(() => sortedRows(result?.rows ?? [], view), [result?.rows, view])
  const numericY = card.y.filter((key) => rows.some((row) => number(row[key])))
  const activeY = visibleSeries(card, view).filter((key) => numericY.includes(key))
  const kind = resolvedKind(card, result, view)
  const choices = availableKinds(card, result, view)
  const selectedHere = selection?.card_id === card.id && selection.field === card.x
  const dimmed = (row: DataRow) => selectedHere && row[card.x] !== selection.value
  const selectRow = (row?: DataRow) => {
    const value = row?.[card.x]
    if (typeof value === 'string' || number(value)) onSelect({ card_id: card.id, field: card.x, value })
  }
  const chartClick = (event: unknown) => {
    selectRow(rowFromChartClick(rows, event))
  }
  const toggleSeries = (key: string) => {
    const hidden = new Set(view.hidden ?? [])
    if (hidden.has(key)) hidden.delete(key)
    else if (activeY.length > 1) hidden.add(key)
    const next = { ...view, hidden: [...hidden] }
    if (kind === 'scatter' && visibleSeries(card, next).length !== 1) {
      next.kind = availableKinds(card, result, next).has('bar') ? 'bar' : 'table'
    }
    onView(next)
  }
  const sort = (key: string) => onView({ ...view, page: 0, sortBy: key, sortDirection: view.sortBy === key && view.sortDirection === 'asc' ? 'desc' : 'asc' })
  const axisUnit = activeY.length && activeY.every((key) => unit(key) === unit(activeY[0])) ? unit(activeY[0]) : ''
  // Colour follows the series, not its position among the visible ones, so hiding one never repaints the rest.
  const color = (key: string) => colors[Math.max(0, numericY.indexOf(key)) % colors.length]
  const pageSize = 50
  const pages = Math.max(1, Math.ceil(rows.length / pageSize))
  const page = Math.min(Math.max(0, view.page ?? 0), pages - 1)
  const shownRows = rows.slice(page * pageSize, (page + 1) * pageSize)
  const numericColumn = (key: string) => rows.some((row) => number(row[key]))
  const wide = kind === 'table' || ((kind === 'bar' || kind === 'line') && rows.length > 12)
  const tile = kind === 'metric'

  const tip = ({ active, label: at, payload }: TipProps) => {
    if (!active || !payload?.length) return null
    const row = payload[0].payload
    const x = kind === 'scatter' ? row?.[card.x] : at
    const entries = kind === 'scatter' ? activeY.map((key) => ({ key, value: row?.[key] })) : payload.map((entry) => ({ key: String(entry.name), value: entry.value }))
    return <div className="dx-tip">
      <div className="dx-tip-head">{display(x as string | number | null, unit(card.x))}</div>
      {entries.map(({ key, value }) => <div className="dx-tip-row" key={key}>
        <i className={kind === 'line' ? 'line' : ''} style={{ background: color(key) }} /><span>{label(key)}</span><b>{display(value as string | number | null, unit(key))}</b>
      </div>)}
    </div>
  }
  const axes = <>
    <CartesianGrid vertical={false} />
    <XAxis dataKey={card.x} tickLine={false} axisLine={false} tickFormatter={(value: string | number) => axisTick(value, unit(card.x))} interval="preserveStartEnd" minTickGap={16} tickMargin={8} />
    <YAxis tickLine={false} axisLine={false} tickFormatter={(value: number) => axisTick(value, axisUnit)} width={40} tickMargin={4} />
    <Tooltip content={tip} cursor={kind === 'bar' ? { className: 'dx-cursor' } : { className: 'dx-cursor-line' }} isAnimationActive={false} />
  </>
  const margin = { top: 8, right: 4, left: 0, bottom: 0 }

  return (
    <article className={`dx-card${wide ? ' wide' : ''}${tile ? ' tile' : ''}${selectedHere ? ' selected' : ''}`} style={{ '--i': index } as CSSProperties}>
      <header className="dx-card-head">
        <div className="dx-card-title">
          <h3>{card.title}</h3>
          {card.description && <p>{card.description}</p>}
        </div>
        {result && choices.size > 1 && <div className="dx-seg" role="radiogroup" aria-label={`Chart type for ${card.title}`}>
          {ORDER.filter((choice) => choices.has(choice)).map((choice) => {
            const Icon = KIND_ICON[choice]
            return <button key={choice} type="button" role="radio" aria-checked={kind === choice} aria-label={KIND_LABEL[choice]} title={KIND_LABEL[choice]}
              onClick={() => onView({ ...view, kind: choice })}><Icon size={14} /></button>
          })}
        </div>}
      </header>

      {!result && <div className="dx-empty">No result for this card.</div>}
      {result && rows.length === 0 && <div className="dx-empty">No rows match.</div>}
      {result && rows.length > 0 && <>
        {kind === 'metric' && <div className="dx-metrics">{activeY.map((key) => {
          const value = rows[0][key]
          const suffix = number(value) && unit(key) && !isFraction(unit(key)) && unit(key) !== '%' ? unitLabel(unit(key)) : ''
          return <div key={key} className="dx-metric">
            <span>{label(key)}</span><strong>{suffix ? compact(value as number) : display(value, unit(key))}{suffix && <small>{suffix}</small>}</strong>
          </div>
        })}</div>}

        {(kind === 'bar' || kind === 'line' || kind === 'scatter') && <div className="dx-plot" role="group" aria-label={`${card.title} ${KIND_LABEL[kind].toLowerCase()} chart`}>
          {numericY.length > 1 && <div className="dx-legend" aria-label={`Series in ${card.title}`}>
            {numericY.map((key) => {
              const on = activeY.includes(key)
              return <button key={key} type="button" className={on ? 'on' : ''} aria-pressed={on} disabled={on && activeY.length === 1} onClick={() => toggleSeries(key)}>
                <i className={kind === 'line' ? 'line' : ''} style={{ background: color(key) }} />{label(key)}
              </button>
            })}
          </div>}
          <ResponsiveContainer width="100%" height={PLOT_HEIGHT}>
            {kind === 'bar' ? <BarChart data={rows} onClick={chartClick} margin={margin} barCategoryGap="30%" barGap={2}>
              {axes}
              {activeY.map((key) => <Bar key={key} dataKey={key} name={key} fill={color(key)} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false}
                onClick={(entry: { payload?: DataRow }) => selectRow(entry.payload)}>
                {rows.map((row, i) => <Cell key={i} fillOpacity={dimmed(row) ? 0.25 : 1} />)}
              </Bar>)}
            </BarChart> : kind === 'line' ? <LineChart data={rows} onClick={chartClick} margin={margin}>
              {axes}
              {activeY.map((key) => <Line key={key} type="monotone" dataKey={key} name={key} stroke={color(key)} strokeWidth={2}
                dot={rows.length <= 24 ? { r: 4, strokeWidth: 2, fill: color(key) } : false} activeDot={{ r: 5, strokeWidth: 2 }} isAnimationActive={false} />)}
              {selectedHere && <ReferenceLine x={selection.value} className="dx-ref" />}
            </LineChart> : <ScatterChart onClick={chartClick} margin={margin}>
              <CartesianGrid vertical={false} />
              <XAxis type="number" dataKey={card.x} name={label(card.x)} tickLine={false} axisLine={false} tickFormatter={(value: number) => axisTick(value, unit(card.x))} tickMargin={8} />
              <YAxis type="number" dataKey={activeY[0]} name={label(activeY[0])} tickLine={false} axisLine={false} tickFormatter={(value: number) => axisTick(value, unit(activeY[0]))} width={40} tickMargin={4} />
              <Tooltip content={tip} cursor={{ className: 'dx-cursor-line' }} isAnimationActive={false} />
              <Scatter data={rows} fill={color(activeY[0])} isAnimationActive={false} onClick={(entry: { payload?: DataRow }) => selectRow(entry.payload)}>
                {rows.map((row, i) => <Cell key={i} fillOpacity={dimmed(row) ? 0.2 : 0.9} />)}
              </Scatter>
            </ScatterChart>}
          </ResponsiveContainer>
          <div className="dx-axis">
            <span>{label(card.x)}</span>
            {activeY.length === 1 && <span>{label(activeY[0])}{unit(activeY[0]) && ` · ${unitLabel(unit(activeY[0]))}`}</span>}
          </div>
        </div>}

        {kind === 'table' && <div className="dx-table-wrap"><table className="dx-table">
          <thead><tr>{columns.map((column) => <th key={column.key} className={numericColumn(column.key) ? 'num' : ''} aria-sort={view.sortBy === column.key ? (view.sortDirection === 'desc' ? 'descending' : 'ascending') : undefined}>
            <button type="button" onClick={() => sort(column.key)}>{column.label}{column.unit && <small>{unitLabel(column.unit)}</small>}
              <span className="dx-sort" aria-hidden="true">{view.sortBy === column.key ? view.sortDirection === 'desc' ? '↓' : '↑' : ''}</span></button>
          </th>)}</tr></thead>
          <tbody>{shownRows.map((row, i) => <tr key={page * pageSize + i} className={selectedHere && row[card.x] === selection.value ? 'selected' : ''} tabIndex={0}
            onClick={() => selectRow(row)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectRow(row) } }}>
            {columns.map((column) => <td key={column.key} className={numericColumn(column.key) ? 'num' : ''}>{display(row[column.key], column.unit)}</td>)}
          </tr>)}</tbody>
        </table>
        {pages > 1 && <div className="dx-pages">
          <span>{page * pageSize + 1}–{Math.min(rows.length, (page + 1) * pageSize)} of {rows.length}</span>
          <button type="button" onClick={() => onView({ ...view, page: page - 1 })} disabled={page === 0}>Previous</button>
          <button type="button" onClick={() => onView({ ...view, page: page + 1 })} disabled={page === pages - 1}>Next</button>
        </div>}
        </div>}
      </>}

      {result && <footer className="dx-card-foot">
        <span className={`dx-src ${result.source.kind}`}>{SOURCE_LABEL[result.source.kind]}</span>
        <span>{result.source.as_of || 'date unknown'}</span>
        <span>{result.rows.length === result.total_rows ? `${result.total_rows} rows` : `${result.rows.length} of ${result.total_rows} rows`}</span>
        {result.source.notes.length > 0 && <details className="dx-notes">
          <summary aria-label="Data notes" title="Data notes"><InfoIcon size={13} /></summary>
          <ul>{result.source.notes.map((note, i) => <li key={i}>{note}</li>)}</ul>
        </details>}
      </footer>}
    </article>
  )
}
