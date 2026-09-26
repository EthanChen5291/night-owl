import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { cellToLatLng } from 'h3-js'
import { fetchBacktest, fetchCells, fetchPlan, fetchPublic, fetchQueue } from './api'
import { centroid } from './city/projection'
import BacktestChart from './components/BacktestChart'
import CellPopup from './components/CellPopup'
import EventFeed, { eventKey } from './components/EventFeed'
import Header from './components/Header'
import Legend from './components/Legend'
import Scene from './components/Scene'
import Toggle from './components/Toggle'
import type { BacktestResponse, Building, Cell, CityMeta, Mode, PlanNode, Preset, RatEvent, Source } from './types'

const DEFAULT_MONTH = '2026-08'
const POLL_MS = 2000
const QUEUE_LIMIT = 20

function modeFromHash(): Mode {
  const m = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('mode')
  return m === 'a' || m === 'b' || m === 'silence' ? m : 'a'
}

export default function App() {
  const [mode, setModeState] = useState<Mode>(modeFromHash)
  const [preset, setPreset] = useState<Preset>('night')
  const [month, setMonth] = useState(DEFAULT_MONTH)
  const [cells, setCells] = useState<Cell[]>([])
  const [cellsSource, setCellsSource] = useState<Source | null>(null)
  const [plan, setPlan] = useState<PlanNode[]>([])
  const [showPlan, setShowPlan] = useState(true)
  const [events, setEvents] = useState<RatEvent[]>([])
  const [queueSource, setQueueSource] = useState<Source>('fixture')
  const [streaming, setStreaming] = useState(false)
  const [latestKey, setLatestKey] = useState<string | null>(null)
  const [flash, setFlash] = useState<{ h3: string; seq: number } | null>(null)
  const [focus, setFocus] = useState<{ h3: string; seq: number } | null>(null)
  const [backtest, setBacktest] = useState<BacktestResponse | null | undefined>(undefined)
  const [buildings, setBuildings] = useState<Building[] | null>(null)
  const [meta, setMeta] = useState<CityMeta | null | undefined>(undefined)
  const [hover, setHover] = useState<{ h3: string; x: number; y: number } | null>(null)

  const seenRef = useRef<Set<string>>(new Set())
  const primedRef = useRef(false) // first queue load does not flash
  const seqRef = useRef(0)

  // ---- mode in the URL hash so a reload keeps it
  const setMode = useCallback((m: Mode) => {
    setModeState(m)
    history.replaceState(null, '', `#mode=${m}`)
  }, [])
  useEffect(() => {
    const onHash = () => setModeState(modeFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // ---- cells and plan
  const loadCells = useCallback(async (m: string) => {
    const { data, source } = await fetchCells(m)
    setCells(data.cells)
    setCellsSource(source)
  }, [])
  useEffect(() => {
    void loadCells(month)
  }, [month, loadCells])
  useEffect(() => {
    void fetchPlan(8).then(({ data }) => setPlan(data.nodes))
    void fetchBacktest().then(setBacktest)
    void fetchPublic<CityMeta>('/city/meta.json').then((m) => setMeta(m))
    void fetchPublic<Building[]>('/city/buildings.json').then((b) => {
      if (Array.isArray(b)) setBuildings(b)
    })
  }, [])

  // ---- one event in: flash, bump the posterior locally, then refetch /cells
  const ingest = useCallback(
    (incoming: RatEvent[], source: Source) => {
      const fresh = incoming.filter((e) => !seenRef.current.has(eventKey(e)))
      for (const e of fresh) seenRef.current.add(eventKey(e))
      if (fresh.length === 0) return
      setEvents((prev) => {
        const merged = [...fresh, ...prev]
        merged.sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0))
        return merged.slice(0, 50)
      })
      if (!primedRef.current) {
        primedRef.current = true
        return
      }
      const newest = fresh.reduce((a, b) => (a.ts >= b.ts ? a : b))
      setLatestKey(eventKey(newest))
      setFlash({ h3: newest.h3, seq: ++seqRef.current })
      setCells((prev) =>
        prev.map((c) =>
          fresh.some((e) => e.h3 === c.h3)
            ? {
                ...c,
                posterior: {
                  ...c.posterior,
                  alpha: c.posterior.alpha + fresh.filter((e) => e.h3 === c.h3).length,
                  n_events: c.posterior.n_events + fresh.filter((e) => e.h3 === c.h3).length,
                },
                last_event_at: newest.ts,
              }
            : c,
        ),
      )
      if (source === 'live') setTimeout(() => void loadCells(month), 1000)
    },
    [loadCells, month],
  )
  const ingestRef = useRef(ingest)
  ingestRef.current = ingest

  // ---- /queue polling every 2 s (keeps trying the API so it goes live when the server appears)
  useEffect(() => {
    let alive = true
    const tick = async () => {
      const { data, source } = await fetchQueue(QUEUE_LIMIT)
      if (!alive) return
      setQueueSource(source)
      ingestRef.current(data.events, source)
    }
    void tick()
    const id = setInterval(() => void tick(), POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  // ---- optional SSE at /api/stream; silently ignored when the server has none
  useEffect(() => {
    if (typeof EventSource === 'undefined') return
    const es = new EventSource('/api/stream')
    es.onopen = () => setStreaming(true)
    es.onmessage = (msg) => {
      try {
        const body = JSON.parse(msg.data) as RatEvent | { events: RatEvent[] }
        ingestRef.current('events' in body ? body.events : [body], 'live')
      } catch {
        /* not an event */
      }
    }
    es.onerror = () => {
      setStreaming(false)
      es.close()
    }
    return () => es.close()
  }, [])

  // ---- derived
  const centre = useMemo(() => {
    if (meta?.centre) return meta.centre
    return centroid(cells.map((c) => ({ lat: cellToLatLng(c.h3)[0], lon: cellToLatLng(c.h3)[1] })))
  }, [meta, cells])
  const hoveredCell = hover ? cells.find((c) => c.h3 === hover.h3) : undefined
  const onHover = useCallback((h3: string | null, x: number, y: number) => {
    setHover(h3 ? { h3, x, y } : null)
  }, [])
  const ready = cells.length > 0 && meta !== undefined

  return (
    <div className="app">
      <Header month={month} cellCount={cells.length} source={cellsSource} onMonth={setMonth} />
      <main className="stage">
        {ready && (
          <Scene
            centre={centre}
            cells={cells}
            mode={mode}
            preset={preset}
            plan={plan}
            showPlan={showPlan}
            buildings={buildings}
            flash={flash}
            focus={focus}
            onHover={onHover}
          />
        )}
        {!ready && <div className="loading">loading cells...</div>}
        <Toggle mode={mode} onMode={setMode} preset={preset} onPreset={setPreset} />
        <Legend mode={mode} showPlan={showPlan} onShowPlan={setShowPlan} planCount={plan.length} />
        {hoveredCell && hover && <CellPopup cell={hoveredCell} mode={mode} x={hover.x} y={hover.y} />}
        <EventFeed
          events={events}
          source={queueSource}
          streaming={streaming}
          latestKey={latestKey}
          onSelect={(h3) => setFocus({ h3, seq: ++seqRef.current })}
        />
      </main>
      <BacktestChart data={backtest} />
    </div>
  )
}
