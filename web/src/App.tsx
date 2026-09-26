import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { cellToLatLng, cellToParent, latLngToCell } from 'h3-js'
import { fetchBacktest, fetchCells, fetchPlacements, fetchPlan, fetchPublic, fetchQueue } from './api'
import { AddressIndex, offBuilding, pointInRing } from './city/addresses'
import { centroid, makeProjector } from './city/projection'
import { TileCache, wantedTiles } from './city/tiles'
import AreaPicker from './components/AreaPicker'
import BacktestChart from './components/BacktestChart'
import CellPopup from './components/CellPopup'
import Header from './components/Header'
import HoverTip from './components/HoverTip'
import Legend from './components/Legend'
import LogsDrawer from './components/LogsDrawer'
import ModeBar from './components/ModeBar'
import NodesPanel from './components/NodesPanel'
import Scene from './components/Scene'
import Toolbar from './components/Toolbar'
import { activityRate, eventKey, loadOwls, newOwl, saveOwls } from './owls'
import type {
  AreasManifest,
  BacktestResponse,
  Cell,
  CityLayers,
  CityMeta,
  HoverInfo,
  Mode,
  OwlNode,
  PlanNode,
  Poly,
  Preset,
  RatEvent,
  Source,
  Spot,
  Tile,
  TilesManifest,
  ViewInfo,
} from './types'

const DEFAULT_MONTH = '2026-09'
const POLL_MS = 2000
const QUEUE_LIMIT = 50
const DEFAULT_PLAN_BUDGET = 20
const DEMO_H3 = '892a100d2c3ffff'

function hashParams(): URLSearchParams {
  return new URLSearchParams(window.location.hash.replace(/^#/, ''))
}
function modeFromHash(): Mode {
  const m = hashParams().get('mode')
  return m === 'a' || m === 'b' || m === 'silence' ? m : 'a'
}
function areaFromHash(): string | null {
  try {
    return hashParams().get('a') || localStorage.getItem('barnowl.area') || null
  } catch {
    return hashParams().get('a') || null
  }
}
function writeHash(mode: Mode, area: string | null) {
  const p = new URLSearchParams()
  p.set('mode', mode)
  if (area) p.set('a', area)
  history.replaceState(null, '', `#${p.toString()}`)
}

export default function App() {
  const [mode, setModeState] = useState<Mode>(modeFromHash)
  const [preset, setPreset] = useState<Preset>('day')
  const [month, setMonth] = useState(DEFAULT_MONTH)
  const [cells, setCells] = useState<Cell[]>([])
  const [cellsSource, setCellsSource] = useState<Source | null>(null)
  const [servedMonth, setServedMonth] = useState<string | null>(null)
  const [plan, setPlan] = useState<PlanNode[]>([])
  const [planMonth, setPlanMonth] = useState<string | null>(null)
  const [planBudget, setPlanBudget] = useState(DEFAULT_PLAN_BUDGET)
  const [showPlan, setShowPlan] = useState(true)
  const [events, setEvents] = useState<RatEvent[]>([])
  const [queueSource, setQueueSource] = useState<Source>('fixture')
  const [streaming, setStreaming] = useState(false)
  const [flash, setFlash] = useState<{ h3: string; seq: number } | null>(null)
  const [focus, setFocus] = useState<{ lat: number; lon: number; distance?: number; seq: number } | null>(null)
  const [openRank, setOpenRank] = useState<number | null>(null) // the suggested hexagon whose spot options are open
  const [spotsByCell, setSpotsByCell] = useState<Map<string, Spot[]>>(() => new Map())
  const [backtest, setBacktest] = useState<BacktestResponse | null | undefined>(undefined)
  const [meta, setMeta] = useState<CityMeta | null | undefined>(undefined)
  const [cityLayers, setCityLayers] = useState<CityLayers | null>(null)
  const [areaLayers, setAreaLayers] = useState<CityLayers | null>(null)
  const [areasManifest, setAreasManifest] = useState<AreasManifest | null | undefined>(undefined)
  const [tilesManifest, setTilesManifest] = useState<TilesManifest | null | undefined>(undefined)
  const [area, setAreaState] = useState<string | null>(areaFromHash)
  const [view, setView] = useState<ViewInfo | null>(null)
  const [tiles, setTiles] = useState<Map<string, Tile>>(() => new Map())
  const [pendingTiles, setPendingTiles] = useState(0)
  const [hover, setHover] = useState<HoverInfo | null>(null)
  const [pinned, setPinned] = useState<{ h3: string; addr: string | null } | null>(null)
  const [owls, setOwls] = useState<OwlNode[]>(loadOwls)
  const [selected, setSelected] = useState<string | null>(null)
  const [placing, setPlacing] = useState(false)
  const [logsOpen, setLogsOpen] = useState(false)
  const [owlsOpen, setOwlsOpen] = useState(true)
  const [chartOpen, setChartOpen] = useState(true)

  const seenRef = useRef<Set<string>>(new Set())
  const primedRef = useRef(false) // first queue load does not flash
  const seqRef = useRef(0)
  const liveRef = useRef({ cells: false, queue: false })
  const monthRef = useRef(month)
  const planBudgetRef = useRef(planBudget)
  const cellsRequestRef = useRef(0)
  const planRequestRef = useRef(0)
  const owlsRef = useRef(owls)
  const cacheRef = useRef(new TileCache())

  // ---- mode and area in the URL hash so a reload keeps them
  const setMode = useCallback((m: Mode) => setModeState(m), [])
  const setArea = useCallback((id: string | null) => {
    setAreaState(id)
    setPlacing(false)
    setPinned(null)
    setSelected(null)
    setOpenRank(null)
    try {
      if (id) localStorage.setItem('barnowl.area', id)
      else localStorage.removeItem('barnowl.area')
    } catch {
      /* ignore */
    }
  }, [])
  useEffect(() => writeHash(mode, area), [mode, area])
  useEffect(() => {
    const onHash = () => {
      setModeState(modeFromHash())
      setAreaState(hashParams().get('a') || null)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  // ---- the UI theme follows the lighting preset (index.css tokens)
  useEffect(() => {
    document.documentElement.dataset.theme = preset
  }, [preset])

  // ---- owls persist
  useEffect(() => {
    owlsRef.current = owls
    saveOwls(owls)
  }, [owls])

  // ---- keyboard: Esc cancels placing / selection / pinned card, Delete removes the selected owl
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPlacing(false)
        setPinned(null)
        setSelected(null)
        setLogsOpen(false)
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && selected && !(e.target instanceof HTMLInputElement)) {
        setOwls((prev) => prev.filter((o) => o.id !== selected))
        setSelected(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected])

  // ---- cells, plan, backtest, citywide layers, manifests
  const loadCells = useCallback(async (m: string) => {
    const request = ++cellsRequestRef.current
    const { data, source } = await fetchCells(m)
    if (request !== cellsRequestRef.current || monthRef.current !== m) return
    if (source === 'fixture' && liveRef.current.cells) {
      setCellsSource('stale')
      return
    }
    liveRef.current.cells = source === 'live'
    setCells(data.cells)
    setCellsSource(data.synthetic || data.source === 'fixture' ? 'fixture' : source)
    setServedMonth(data.month)
  }, [])
  useEffect(() => {
    void loadCells(month)
  }, [month, loadCells])
  const selectMonth = useCallback((m: string) => {
    monthRef.current = m
    liveRef.current.cells = false
    setCells([])
    setCellsSource(null)
    setServedMonth(null)
    setPlan([])
    setPlanMonth(null)
    setMonth(m)
  }, [])
  const loadPlan = useCallback(async (m: string, k: number) => {
    const request = ++planRequestRef.current
    const { data } = await fetchPlan(m, k)
    if (request !== planRequestRef.current || monthRef.current !== m) return
    setPlan(data.nodes.slice(0, k))
    setPlanMonth(data.month)
    setOpenRank(null)
    setSpotsByCell(new Map())
  }, [])
  useEffect(() => {
    void loadPlan(month, planBudget)
  }, [month, planBudget, loadPlan])
  useEffect(() => {
    void fetchBacktest().then(setBacktest)
    void fetchPublic<CityMeta>('/city/meta.json').then((m) => setMeta(m))
    void fetchPublic<AreasManifest>('/city/areas.json').then((m) => setAreasManifest(m))
    void fetchPublic<TilesManifest>('/city/tiles.json').then((m) => setTilesManifest(m))
    void Promise.all([fetchPublic<Poly[]>('/city/land.json'), fetchPublic<Poly[]>('/city/parks.json'), fetchPublic<Poly[]>('/city/water.json')]).then(
      ([land, parks, water]) => {
        if (land || parks || water) setCityLayers({ land, parks, water })
      },
    )
  }, [])

  // ---- inside an area only that borough's ground is drawn (the citywide layers hide), so it is fetched on entry
  useEffect(() => {
    if (!area) {
      setAreaLayers(null)
      return
    }
    let alive = true
    const base = `/city/areas/${area}`
    void Promise.all([fetchPublic<Poly[]>(`${base}/land.json`), fetchPublic<Poly[]>(`${base}/parks.json`), fetchPublic<Poly[]>(`${base}/water.json`)]).then(
      ([land, parks, water]) => {
        if (alive) setAreaLayers({ land, parks, water })
      },
    )
    return () => {
      alive = false
    }
  }, [area])

  // ---- tiles stream around the camera target, only the active area's: the wanted set changes as the view moves, the cache fills it
  useEffect(() => {
    if (!tilesManifest || !view) return
    const wanted = wantedTiles(tilesManifest, view.lat, view.lon, view.distance, area)
    let alive = true
    const cache = cacheRef.current
    const apply = () => {
      if (!alive) return
      const next = new Map<string, Tile>()
      for (const id of wanted) {
        const t = cache.get(id)
        if (t) next.set(id, t)
      }
      setTiles((prev) => {
        if (prev.size === next.size && [...next.keys()].every((k) => prev.has(k))) return prev
        return next
      })
    }
    apply()
    const missing = wanted.filter((id) => !cache.get(id))
    setPendingTiles(missing.length)
    for (const id of missing) {
      void cache.load(id).then(() => {
        apply()
        setPendingTiles((n) => Math.max(0, n - 1))
      })
    }
    return () => {
      alive = false
    }
  }, [tilesManifest, view, area])

  // ---- the opened suggested hexagon's spot options (A, B, C), fetched once per cell
  useEffect(() => {
    const node = openRank !== null ? plan.find((p) => p.rank === openRank) : undefined
    if (!node || spotsByCell.has(node.h3)) return
    let alive = true
    void fetchPlacements(node.h3).then((spots) => {
      if (alive) setSpotsByCell((prev) => new Map(prev).set(node.h3, spots))
    })
    return () => {
      alive = false
    }
  }, [openRank, plan, spotsByCell])

  // ---- events are evidence; the server owns posterior and ranking updates
  const ingest = useCallback(
    (incoming: RatEvent[], source: Source, flashNew = true) => {
      const fresh = incoming.filter((e) => !seenRef.current.has(eventKey(e)))
      for (const e of fresh) seenRef.current.add(eventKey(e))
      if (fresh.length === 0) return
      setEvents((prev) => {
        const merged = [...fresh, ...prev]
        merged.sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0))
        return merged.slice(0, 500)
      })
      // Only real node events can create persistent owls. Fixture rows are feed examples.
      const unknown = source === 'live'
        ? fresh.filter((e) => !owlsRef.current.some((o) => o.nodeId === e.node_id))
        : []
      if (unknown.length) {
        setOwls((prev) => {
          let next = prev
          for (const e of unknown) {
            if (next.some((o) => o.nodeId === e.node_id)) continue
            const [lat, lon] = cellToLatLng(e.h3)
            next = [...next, newOwl(next, lat, lon, null, e.node_id)]
          }
          return next
        })
      }
      // The queue includes rejected detections. Flash only events that pass the frozen update gate.
      const accepted = fresh.filter((e) => e.accepted ?? (e.class === 'rat' && e.conf >= 0.5 && e.n_hits >= 3))
      if (flashNew && accepted.length) {
        const newest = accepted.reduce((a, b) => (a.ts >= b.ts ? a : b))
        setFlash({ h3: newest.h3, seq: ++seqRef.current })
      }
      if (source === 'live') {
        void loadCells(month)
        void loadPlan(month, planBudget)
      }
    },
    [loadCells, loadPlan, month, planBudget],
  )
  const ingestRef = useRef(ingest)
  useEffect(() => { ingestRef.current = ingest }, [ingest])

  const activateLiveQueue = useCallback(() => {
    if (liveRef.current.queue) return false
    liveRef.current.queue = true
    seenRef.current.clear()
    primedRef.current = false
    setEvents([])
    setFlash(null)
    setQueueSource('live')
    void loadCells(monthRef.current)
    void loadPlan(monthRef.current, planBudgetRef.current)
    void fetchBacktest().then(setBacktest)
    return true
  }, [loadCells, loadPlan])

  // ---- /queue polling every 2 s (keeps trying the API so it goes live when the server appears)
  useEffect(() => {
    let alive = true
    const tick = async () => {
      const { data, source } = await fetchQueue(QUEUE_LIMIT)
      if (!alive) return
      if (source === 'fixture' && liveRef.current.queue) {
        setQueueSource('stale')
        return
      }
      const becameLive = source === 'live' && activateLiveQueue()
      setQueueSource(source)
      if (source === 'live' && data.events.length === 0 && seenRef.current.size > 0) {
        seenRef.current.clear()
        setEvents([])
        setFlash(null)
        void loadCells(monthRef.current)
        void loadPlan(monthRef.current, planBudgetRef.current)
      }
      ingestRef.current(data.events, source, primedRef.current && !becameLive)
      primedRef.current = true
    }
    void tick()
    const id = setInterval(() => void tick(), POLL_MS)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [activateLiveQueue, loadCells, loadPlan])

  // ---- SSE at /api/stream: the server names its messages, so listen for `event`, not the default channel
  useEffect(() => {
    if (typeof EventSource === 'undefined') return
    let disposed = false
    let source: EventSource | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    const onEvent = (msg: MessageEvent) => {
      try {
        const body = JSON.parse(msg.data as string) as RatEvent | { events: RatEvent[] }
        activateLiveQueue()
        ingestRef.current('events' in body ? body.events : [body], 'live')
      } catch {
        /* not an event */
      }
    }
    const onReset = () => {
      activateLiveQueue()
      seenRef.current.clear()
      setEvents([])
      setFlash(null)
      void loadCells(monthRef.current)
      void loadPlan(monthRef.current, planBudgetRef.current)
    }
    const connect = () => {
      if (disposed) return
      const es = new EventSource('/api/stream')
      source = es
      es.onopen = () => {
        setStreaming(true)
        activateLiveQueue()
      }
      es.addEventListener('event', onEvent)
      es.onmessage = onEvent
      es.addEventListener('reset', onReset)
      es.onerror = () => {
        setStreaming(false)
        // The browser retries CONNECTING streams. A terminal HTTP error closes the
        // stream, so open a new one while queue polling continues.
        if (disposed || source !== es || es.readyState !== EventSource.CLOSED) return
        es.close()
        source = null
        if (retryTimer === null) {
          retryTimer = setTimeout(() => {
            retryTimer = null
            connect()
          }, 3000)
        }
      }
    }
    connect()
    return () => {
      disposed = true
      if (retryTimer !== null) clearTimeout(retryTimer)
      source?.close()
    }
  }, [activateLiveQueue, loadCells, loadPlan])

  // ---- derived
  const centre = useMemo(() => {
    if (areasManifest?.centre) return areasManifest.centre
    if (meta?.centre) return meta.centre
    return centroid(cells.map((c) => ({ lat: cellToLatLng(c.h3)[0], lon: cellToLatLng(c.h3)[1] })))
  }, [areasManifest, meta, cells])
  const projector = useMemo(() => makeProjector(centre), [centre])
  const areas = useMemo(() => areasManifest?.areas ?? [], [areasManifest])
  const tileAreas = useMemo(() => {
    const out: Record<string, string | null | undefined> = {}
    for (const [id, t] of Object.entries(tilesManifest?.tiles ?? {})) out[id] = t.a
    return out
  }, [tilesManifest])
  const activeArea = areas.find((a) => a.id === area) ?? null
  const index = useMemo(() => {
    if (tiles.size === 0) return null
    const buildings = [...tiles.values()].flatMap((t) => t.buildings)
    const trees = [...tiles.values()].flatMap((t) => t.trees)
    return new AddressIndex(buildings, trees)
  }, [tiles])
  const cellByH3 = useMemo(() => new Map(cells.map((c) => [c.h3, c])), [cells])
  // suggested sites of the borough you are in (by their r7 tile's area); nothing citywide
  const visiblePlan = useMemo(() => (planMonth && planMonth === servedMonth ? plan : []), [planMonth, servedMonth, plan])
  const noBake = areas.length === 0
  const planHere = useMemo(() => (noBake ? visiblePlan : area ? visiblePlan.filter((p) => tileAreas[cellToParent(p.h3, 7)] === area) : []), [visiblePlan, area, noBake, tileAreas])
  const openNode = openRank !== null ? planHere.find((p) => p.rank === openRank) : undefined
  // which borough an owl is in: its point against the borough outlines, else its r7 tile's area
  const areaOfOwl = useCallback(
    (o: OwlNode) => {
      const [x, y] = projector.xy(o.lat, o.lon)
      return areas.find((a) => pointInRing(x, y, a.outline))?.id ?? tileAreas[cellToParent(o.h3, 7)] ?? null
    },
    [areas, projector, tileAreas],
  )
  // inside a borough only its owls exist, on the map and in the list; citywide, all of them
  const owlsHere = useMemo(() => (noBake ? owls : area ? owls.filter((o) => areaOfOwl(o) === area) : owls), [owls, area, noBake, areaOfOwl])
  const openSpots = useMemo(() => (openNode ? spotsByCell.get(openNode.h3) : undefined), [openNode, spotsByCell])

  // ---- an owl spawned by an event before any tile was loaded has a placeholder address: fill it in once we can
  useEffect(() => {
    if (!index) return
    setOwls((prev) => {
      let changed = false
      const next = prev.map((o) => {
        const [x0, y0] = projector.xy(o.lat, o.lon)
        // an owl inside a building footprint (placed before the rule, or spawned at a cell centre) moves to the sidewalk
        const off = !o.treeId && index.buildingAt(x0, y0) ? offBuilding(index, x0, y0) : null
        if (!off && !o.addr.startsWith('block ')) return o
        const [x, y] = off ? [off.x, off.y] : [x0, y0]
        const hit = off?.tree?.addr ? { addr: `near ${off.tree.addr}` } : index.at(x, y)
        const near = hit ? hit.addr : (() => { const t = index.nearestTree(x, y, 120); return t?.tree.addr ? `near ${t.tree.addr}` : null })()
        if (!off && !near) return o
        changed = true
        const ll = off ? projector.latLon(x, y) : { lat: o.lat, lon: o.lon }
        return { ...o, addr: near ?? o.addr, lat: ll.lat, lon: ll.lon, h3: latLngToCell(ll.lat, ll.lon, 9), treeId: off?.tree?.id ?? o.treeId }
      })
      return changed ? next : prev
    })
  }, [index, projector])
  const sightings = useMemo(() => {
    const m = new Map<string, RatEvent[]>()
    for (const o of owls) m.set(o.id, events.filter((e) => e.node_id === o.nodeId))
    return m
  }, [owls, events])
  const rates = useMemo(() => new Map(owls.map((o) => [o.id, activityRate(sightings.get(o.id) ?? [])])), [owls, sightings])
  const hoveredCell = hover?.h3 ? cellByH3.get(hover.h3) : undefined
  const pinnedCell = pinned ? cellByH3.get(pinned.h3) : undefined
  const ready = cells.length > 0 && meta !== undefined && areasManifest !== undefined

  // ---- placing and clicking
  const addressAt = useCallback(
    (lat: number, lon: number) => {
      if (!index) return { addr: null as string | null, lat, lon, treeId: undefined as string | undefined }
      const [x0, y0] = projector.xy(lat, lon)
      const tree = index.nearestTree(x0, y0, 40)
      if (tree?.tree.addr) {
        const ll = projector.latLon(tree.tree.x, tree.tree.y)
        return { addr: tree.tree.addr, lat: ll.lat, lon: ll.lon, treeId: tree.tree.id } // snap to the tree pit: owls hang on tree guards
      }
      // never inside a building: the nearest pit further out, else the sidewalk at the footprint's edge
      const off = offBuilding(index, x0, y0)
      const [x, y] = [off.x, off.y]
      const ll = projector.latLon(x, y)
      const hit = off.tree?.addr ? { addr: `near ${off.tree.addr}` } : index.at(x, y)
      return { addr: hit?.addr ?? null, lat: ll.lat, lon: ll.lon, treeId: off.tree?.id }
    },
    [index, projector],
  )
  /** Select an owl; the camera glides there, or all the way in (`close`) until the 3D pin shows. */
  const selectOwl = useCallback((id: string | null, close = false) => {
    setSelected(id)
    const o = id ? owlsRef.current.find((x) => x.id === id) : null
    if (o) setFocus({ lat: o.lat, lon: o.lon, distance: close ? 300 : undefined, seq: ++seqRef.current })
  }, [])
  /** Place an owl on a spot option: on its street tree, with the model's mount address. */
  const placeSpot = useCallback((spot: Spot) => {
    const addr = spot.mount_address.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase()) // the model shouts; the bake's addresses are title case
    const owl = newOwl(owlsRef.current, spot.lat, spot.lon, addr, undefined, spot.tree_id)
    owlsRef.current = [...owlsRef.current, owl]
    setOwls((prev) => [...prev, owl])
    setSelected(owl.id)
    setOwlsOpen(true)
    setOpenRank(null)
    setFocus({ lat: spot.lat, lon: spot.lon, distance: 300, seq: ++seqRef.current })
  }, [])
  const placePlan = useCallback((site: PlanNode) => {
    const owl = newOwl(owlsRef.current, site.lat, site.lon, null, undefined, site.tree_id)
    owlsRef.current = [...owlsRef.current, owl]
    setOwls((prev) => [...prev, owl])
    setSelected(owl.id)
    setOwlsOpen(true)
    setFocus({ lat: site.lat, lon: site.lon, distance: 300, seq: ++seqRef.current })
  }, [])
  const placeOwl = useCallback(
    (lat: number, lon: number) => {
      const spot = addressAt(lat, lon)
      const owl = newOwl(owlsRef.current, spot.lat, spot.lon, spot.addr, undefined, spot.treeId)
      owlsRef.current = [...owlsRef.current, owl] // a second placement before the re-render must not reuse the id
      setOwls((prev) => [...prev, owl])
      setSelected(owl.id)
      setOwlsOpen(true)
    },
    [addressAt],
  )
  const onClick = useCallback(
    (info: HoverInfo) => {
      if (info.kind === 'area' && info.areaId) {
        if (info.areaId !== area) setArea(info.areaId) // a name tag: from the city, or straight from another area
        return
      }
      if (placing) {
        placeOwl(info.lat, info.lon)
        setPlacing(false)
        return
      }
      if (info.kind === 'node' && info.nodeId) {
        selectOwl(info.nodeId, true) // select and fly all the way in
        return
      }
      if (info.kind === 'plan' && info.planRank !== undefined) {
        // a suggested hexagon's pin opens its spot options and glides there
        const rank = info.planRank
        setOpenRank((r) => (r === rank ? null : rank))
        setFocus({ lat: info.lat, lon: info.lon, seq: ++seqRef.current })
        return
      }
      if (info.kind === 'spot' && openSpots) {
        const spot = openSpots.find((s) => s.rank === info.spotRank)
        if (spot) placeSpot(spot)
        return
      }
      if (info.cellHit && info.h3 && cellByH3.has(info.h3) && (area || noBake)) {
        const h3 = info.h3
        setPinned((p) => (p?.h3 === h3 ? null : { h3, addr: info.addr }))
        setSelected(null)
        return
      }
      setPinned(null)
      setSelected(null)
    },
    [area, noBake, placing, placeOwl, cellByH3, setArea, selectOwl, openSpots, placeSpot],
  )
  const onHover = useCallback((info: HoverInfo | null) => setHover(info), [])
  const onView = useCallback((v: ViewInfo) => setView(v), [])

  const selectedOwl = selected ? owls.find((o) => o.id === selected) : undefined
  const hoveredOwl = hover?.nodeId ? owls.find((o) => o.id === hover.nodeId) : undefined
  const hoveredArea = hover?.areaId ? areas.find((a) => a.id === hover.areaId) : undefined

  return (
    <div className={`app ${placing ? 'placing' : ''} ${hover && (hover.kind === 'node' || hover.kind === 'plan' || hover.kind === 'spot' || hover.kind === 'area') ? 'hot' : ''}`}>
      <main className="stage">
        {ready && (
          <Scene
            centre={centre}
            cells={cells}
            mode={mode}
            preset={preset}
            plan={planHere}
            showPlan={showPlan}
            spots={showPlan && openSpots ? openSpots : []}
            cityLayers={cityLayers}
            areaLayers={areaLayers}
            tiles={tiles}
            areas={areas}
            tileAreas={tileAreas}
            activeArea={noBake ? null : area}
            nodes={owlsHere}
            selectedNode={selected}
            index={index}
            flash={flash}
            focus={focus}
            onHover={onHover}
            onClick={onClick}
            onView={onView}
          />
        )}
        {!ready && <div className="loading">loading the city…</div>}
        {pendingTiles > 0 && <div className="loading-chip panel">streaming {pendingTiles} tile{pendingTiles === 1 ? '' : 's'}…</div>}

        <Toolbar
          area={activeArea}
          placing={placing}
          showPlan={showPlan}
          logsOpen={logsOpen}
          onBack={() => setArea(null)}
          onPlace={() => setPlacing((p) => !p)}
          onShowPlan={() => setShowPlan((s) => !s)}
          onLogs={() => setLogsOpen((o) => !o)}
          noBake={noBake}
        />
        <ModeBar mode={mode} onMode={setMode} preset={preset} onPreset={setPreset} />
        <Header month={month} servedMonth={servedMonth} cellCount={cells.length} source={cellsSource} planBudget={planBudget} onMonth={selectMonth} onPlanBudget={(k) => { planBudgetRef.current = k; setPlan([]); setPlanMonth(null); setPlanBudget(k) }} onDemo={() => {
          if (!cellByH3.has(DEMO_H3)) return
          const [lat, lon] = cellToLatLng(DEMO_H3)
          setFocus({ lat, lon, distance: 800, seq: ++seqRef.current })
          setPinned({ h3: DEMO_H3, addr: null })
        }} />
        <Legend mode={mode} lifted={chartOpen} />

        {!activeArea && areas.length > 0 && <AreaPicker areas={areas} hovered={hover?.areaId ?? null} onPick={setArea} />}

        {hover && hover.kind !== 'ground' && <HoverTip info={hover} mode={mode} cell={hoveredCell} node={hoveredOwl} area={hoveredArea} placing={placing} />}
        {pinnedCell && <CellPopup cell={pinnedCell} mode={mode} addr={pinned?.addr ?? null} onClose={() => setPinned(null)} />}

        <NodesPanel
          nodes={owlsHere}
          sightings={sightings}
          rates={rates}
          selected={selected}
          plan={planHere}
          openRank={openRank}
          openSpots={openSpots}
          onOpenRank={(rank) => {
            setOpenRank(rank)
            const p = rank !== null ? planHere.find((x) => x.rank === rank) : undefined
            if (p) setFocus({ lat: p.lat, lon: p.lon, seq: ++seqRef.current })
          }}
          onFlySpot={(s) => setFocus({ lat: s.lat, lon: s.lon, distance: 320, seq: ++seqRef.current })}
          onPlaceSpot={placeSpot}
          onPlacePlan={placePlan}
          inArea={!!area || noBake}
          source={queueSource}
          streaming={streaming}
          open={owlsOpen}
          onToggle={() => setOwlsOpen((o) => !o)}
          onSelect={selectOwl}
          onRemove={(id) => {
            setOwls((prev) => prev.filter((o) => o.id !== id))
            if (selected === id) setSelected(null)
          }}
          onStartPlacing={() => setPlacing(true)}
        />
        {logsOpen && <LogsDrawer events={events} nodes={owlsHere} selected={selectedOwl?.id ?? null} onClose={() => setLogsOpen(false)} onSelect={selectOwl} />}
        <BacktestChart data={backtest} open={chartOpen} onToggle={() => setChartOpen((o) => !o)} wide={!owlsOpen} />
      </main>
    </div>
  )
}
