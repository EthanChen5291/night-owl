import { useMemo } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { ChartSelection, DashboardCard, DataRow, QueryResult } from './types'
import { resolvedKind, sortedRows, visibleSeries, type CardView } from './view'

interface Props {
  card: DashboardCard
  result?: QueryResult
  view: CardView
  selection: ChartSelection | null
  onView: (view: CardView) => void
  onSelect: (selection: ChartSelection) => void
}

const colors = ['#bc672d', '#397c9e', '#619b70', '#876cb4', '#c09042']
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const compact = (value: number) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)
const compactTick = (value: number) => new Intl.NumberFormat(undefined, {
  notation: Math.abs(value) >= 1000 ? 'compact' : 'standard', maximumFractionDigits: Math.abs(value) >= 1000 ? 1 : 2,
}).format(value)
const unitLabel = (unit: string) => unit === 'probability' || unit === 'fraction' ? '%' : unit === 'percentile 0–100' ? 'percentile' : unit

function axisTick(value: string | number | null, unit = ''): string {
  if (value === null) return ''
  if (typeof value === 'number') return `${compactTick((unit === 'probability' || unit === 'fraction') ? value * 100 : value)}${unit === 'probability' || unit === 'fraction' || unit === '%' ? '%' : ''}`
  return value.length > 16 ? `${value.slice(0, 15)}…` : value
}

function display(value: string | number | null | undefined, unit = ''): string {
  if (value === null || value === undefined) return '—'
  if (typeof value !== 'number') return value
  if (unit === 'probability' || unit === 'fraction') return `${compact(value * 100)}%`
  return `${compact(value)}${unit === '%' ? '%' : unit ? ` ${unitLabel(unit)}` : ''}`
}


export default function ChartCard({ card, result, view, selection, onView, onSelect }: Props) {
  const columns = result?.columns ?? []
  const label = (key: string) => columns.find((column) => column.key === key)?.label ?? key
  const unit = (key: string) => columns.find((column) => column.key === key)?.unit ?? ''
  const columnFor = (name: string) => columns.find((column) => column.key === name || column.label === name)
  const rows = useMemo(() => sortedRows(result?.rows ?? [], view), [result?.rows, view])
  const numericY = card.y.filter((key) => rows.some((row) => number(row[key])))
  const activeY = visibleSeries(card, view).filter((key) => numericY.includes(key))
  const kind = resolvedKind(card, result, view)
  const xNumeric = rows.some((row) => number(row[card.x]))
  const choices: DashboardCard['kind'][] = ['table']
  if (rows.length === 1 && activeY.length) choices.unshift('metric')
  if (activeY.length && rows.some((row) => row[card.x] != null)) choices.unshift('bar', 'line')
  if (xNumeric && activeY.length === 1) choices.unshift('scatter')
  const selectedHere = selection?.card_id === card.id && selection.field === card.x
  const isSelected = (row: DataRow) => selectedHere && row[card.x] === selection.value
  const selectRow = (row?: DataRow) => {
    const value = row?.[card.x]
    if (typeof value === 'string' || number(value)) onSelect({ card_id: card.id, field: card.x, value })
  }
  const chartClick = (event: unknown) => {
    const payload = event as { activePayload?: { payload?: DataRow }[] }
    selectRow(payload.activePayload?.[0]?.payload)
  }
  const changeKind = (next: DashboardCard['kind']) => onView({ ...view, kind: next })
  const toggleSeries = (key: string) => {
    const hidden = new Set(view.hidden ?? [])
    if (hidden.has(key)) hidden.delete(key)
    else if (activeY.length > 1) hidden.add(key)
    const next = { ...view, hidden: [...hidden] }
    if (kind === 'scatter' && visibleSeries(card, next).length !== 1) next.kind = 'bar'
    onView(next)
  }
  const sort = (key: string) => onView({ ...view, page: 0, sortBy: key, sortDirection: view.sortBy === key && view.sortDirection === 'asc' ? 'desc' : 'asc' })
  const tooltip = <Tooltip formatter={(value: unknown, name: unknown) => { const column = columnFor(String(name)); return [display(value as number | string | null, column?.unit), column?.label ?? String(name)] }} labelFormatter={(value: unknown) => `${label(card.x)}: ${display(value as string | number, unit(card.x))}`} />
  const yCaption = activeY.map((key) => `${label(key)}${unit(key) && ` (${unitLabel(unit(key))})`}`).join(' · ')
  const axisUnit = activeY.length && activeY.every((key) => unit(key) === unit(activeY[0])) ? unit(activeY[0]) : ''
  const pageSize = 50
  const pages = Math.max(1, Math.ceil(rows.length / pageSize))
  const page = Math.min(Math.max(0, view.page ?? 0), pages - 1)
  const shownRows = rows.slice(page * pageSize, (page + 1) * pageSize)

  return (
    <article className={`dash-card ${selectedHere ? 'selected' : ''}`}>
      <div className="dash-card-head">
        <div>
          <h3>{card.title}</h3>
          {card.description && <p>{card.description}</p>}
        </div>
        {result && <label className="dash-kind-label">View
          <select aria-label={`Chart type for ${card.title}`} value={kind} onChange={(event) => changeKind(event.target.value as DashboardCard['kind'])}>
            {choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
          </select>
        </label>}
      </div>

      {!result && <div className="dash-empty">No result was returned for this card.</div>}
      {result && rows.length === 0 && <div className="dash-empty">No rows match this query.</div>}
      {result && rows.length > 0 && <>
        {card.y.length > 1 && numericY.length > 0 && <div className="dash-series" aria-label={`Series in ${card.title}`}>
          {numericY.map((key, index) => <label key={key} className="dash-series-item">
            <input type="checkbox" checked={activeY.includes(key)} onChange={() => toggleSeries(key)} disabled={activeY.length === 1 && activeY.includes(key)} />
            <i style={{ background: colors[index % colors.length] }} />{label(key)}{unit(key) && ` (${unit(key)})`}
          </label>)}
        </div>}

        {kind === 'metric' && <div className="dash-metrics">{activeY.map((key) => <div key={key} className="dash-metric"><strong>{display(rows[0][key], unit(key))}</strong><span>{label(key)}</span></div>)}</div>}

        {(kind === 'bar' || kind === 'line' || kind === 'scatter') && <div className="dash-plot" role="group" aria-label={`${card.title} ${kind} chart`}>
          <ResponsiveContainer width="100%" height={260}>
            {kind === 'bar' ? <BarChart data={rows} onClick={chartClick} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
              <CartesianGrid stroke="#e7e9e7" vertical={false} />
              <XAxis dataKey={card.x} tick={{ fontSize: 11 }} tickFormatter={(value: string | number) => axisTick(value, unit(card.x))} interval="preserveStartEnd" minTickGap={12} tickMargin={8} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => axisTick(value, axisUnit)} width={48} />
              {tooltip}
              {activeY.map((key, index) => <Bar key={key} dataKey={key} name={key} fill={colors[index % colors.length]} maxBarSize={48} onClick={(entry: { payload?: DataRow }) => selectRow(entry.payload)}>
                {rows.map((row, i) => <Cell key={i} fill={isSelected(row) ? '#172e3c' : colors[index % colors.length]} />)}
              </Bar>)}
            </BarChart> : kind === 'line' ? <LineChart data={rows} onClick={chartClick} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
              <CartesianGrid stroke="#e7e9e7" vertical={false} />
              <XAxis dataKey={card.x} tick={{ fontSize: 11 }} tickFormatter={(value: string | number) => axisTick(value, unit(card.x))} interval="preserveStartEnd" minTickGap={12} tickMargin={8} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(value: number) => axisTick(value, axisUnit)} width={48} />
              {tooltip}
              {activeY.map((key, index) => <Line key={key} type="monotone" dataKey={key} name={key} stroke={colors[index % colors.length]} strokeWidth={2.3} dot={rows.length <= 24} isAnimationActive={false} />)}
              {selectedHere && <ReferenceLine x={selection.value} stroke="#172e3c" strokeDasharray="4 3" />}
            </LineChart> : <ScatterChart onClick={chartClick} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
              <CartesianGrid stroke="#e7e9e7" />
              <XAxis type="number" dataKey={card.x} name={label(card.x)} tick={{ fontSize: 11 }} tickFormatter={(value: number) => axisTick(value, unit(card.x))} tickMargin={8} />
              <YAxis type="number" dataKey={activeY[0]} name={label(activeY[0])} tick={{ fontSize: 11 }} tickFormatter={(value: number) => axisTick(value, unit(activeY[0]))} width={48} />
              {tooltip}
              <Scatter data={rows} fill={colors[0]} onClick={(entry: { payload?: DataRow }) => selectRow(entry.payload)}>
                {rows.map((row, i) => <Cell key={i} fill={isSelected(row) ? '#172e3c' : colors[0]} />)}
              </Scatter>
            </ScatterChart>}
          </ResponsiveContainer>
          <div className="dash-axis-caption">{label(card.x)}{unit(card.x) && ` (${unit(card.x)})`}</div>
          <div className="dash-axis-caption">{yCaption}</div>
        </div>}

        {kind === 'table' && <div className="dash-table-wrap"><table className="dash-table">
          <thead><tr>{columns.map((column) => <th key={column.key}><button type="button" onClick={() => sort(column.key)} aria-label={`Sort by ${column.label}`}>{column.label}{column.unit && ` (${column.unit})`}{view.sortBy === column.key ? view.sortDirection === 'desc' ? ' ↓' : ' ↑' : ''}</button></th>)}</tr></thead>
          <tbody>{shownRows.map((row, index) => <tr key={page * pageSize + index} className={isSelected(row) ? 'selected' : ''} tabIndex={0} onClick={() => selectRow(row)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectRow(row) } }}>
            {columns.map((column) => <td key={column.key}>{display(row[column.key], column.unit)}</td>)}
          </tr>)}</tbody>
        </table><div className="dash-table-limit"><span>Showing {page * pageSize + 1}–{Math.min(rows.length, (page + 1) * pageSize)} of {rows.length} returned rows{result.total_rows > rows.length ? ` (${result.total_rows} groups before the query limit)` : ''}.</span>{pages > 1 && <span className="dash-table-pages"><button type="button" onClick={() => onView({ ...view, page: page - 1 })} disabled={page === 0}>Previous</button><span>{page + 1} / {pages}</span><button type="button" onClick={() => onView({ ...view, page: page + 1 })} disabled={page === pages - 1}>Next</button></span>}</div></div>}
      </>}

      {result && <div className="dash-source">
        <span className={`dash-source-kind ${result.source.kind}`}>{result.source.kind === 'fixture' ? 'Sample data' : result.source.kind === 'events' ? 'Event data' : 'Model data'}</span>
        <span>As of {result.source.as_of || 'unknown'}</span>
        <span>{result.rows.length} of {result.total_rows} result rows</span>
        {result.source.notes.map((note, index) => <span key={index} className="dash-source-note">{note}</span>)}
      </div>}
    </article>
  )
}
