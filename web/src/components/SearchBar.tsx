import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { cellToLatLng } from 'h3-js'
import type { Cell } from '../types'
import { SearchIcon } from './Icons'

// Address search (top right): NYC GeoSearch for street addresses and places, plus the model's own neighbourhood
// names and raw hexagon ids, matched locally. Picking one flies the camera to that point and pins its hexagon.

export interface Place {
  label: string
  sub: string
  lat: number
  lon: number
  borough: string | null
  h3?: string // set when the pick is a hexagon itself (an id typed in)
  kind: 'address' | 'neighborhood' | 'hexagon'
}

interface Props {
  cells: Cell[]
  onPick: (p: Place) => void
}

const GEOSEARCH = 'https://geosearch.planninglabs.nyc/v2/autocomplete'
const DEBOUNCE_MS = 180
const MAX_REMOTE = 7
const MAX_LOCAL = 3
const H3_ID = /^8[0-9a-f]{14}$/i

const titleCase = (s: string) => s.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase())

interface GeoFeature {
  geometry: { coordinates: [number, number] }
  properties: { name?: string; label?: string; borough?: string; neighbourhood?: string; layer?: string }
}

async function geosearch(text: string, signal: AbortSignal): Promise<Place[]> {
  const res = await fetch(`${GEOSEARCH}?text=${encodeURIComponent(text)}`, { signal, headers: { accept: 'application/json' } })
  if (!res.ok) return []
  const body = (await res.json()) as { features?: GeoFeature[] }
  const out: Place[] = []
  const seen = new Set<string>()
  for (const f of body.features ?? []) {
    const name = f.properties.name ?? f.properties.label ?? ''
    const [lon, lat] = f.geometry.coordinates
    const label = titleCase(name)
    if (!label || seen.has(label)) continue
    seen.add(label)
    const borough = f.properties.borough ?? null
    const hood = f.properties.neighbourhood
    out.push({ label, sub: [hood, borough].filter(Boolean).join(' · '), lat, lon, borough, kind: 'address' })
    if (out.length >= MAX_REMOTE) break
  }
  return out
}

export default function SearchBar({ cells, onPick }: Props) {
  const [query, setQuery] = useState('')
  const [remote, setRemote] = useState<{ text: string; places: Place[] }>({ text: '', places: [] })
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [busyText, setBusyText] = useState<string | null>(null) // the query a request is out for
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  // neighbourhoods the cells carry (live data only): name -> centroid of its hexagons
  const hoods = useMemo(() => {
    const acc = new Map<string, { borough: string | null; lat: number; lon: number; n: number }>()
    for (const c of cells) {
      if (!c.neighborhood) continue
      const [lat, lon] = cellToLatLng(c.h3)
      const cur = acc.get(c.neighborhood)
      if (cur) {
        cur.lat += lat
        cur.lon += lon
        cur.n += 1
      } else acc.set(c.neighborhood, { borough: c.borough ?? null, lat, lon, n: 1 })
    }
    return [...acc.entries()].map(([name, v]) => ({ name, borough: v.borough, lat: v.lat / v.n, lon: v.lon / v.n, n: v.n }))
  }, [cells])
  const cellIds = useMemo(() => new Set(cells.map((c) => c.h3)), [cells])

  const local = useMemo<Place[]>(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 2) return []
    if (H3_ID.test(q)) {
      const id = q.toLowerCase()
      if (!cellIds.has(id)) return []
      const [lat, lon] = cellToLatLng(id)
      return [{ label: `Hexagon ${id}`, sub: 'model cell', lat, lon, borough: null, h3: id, kind: 'hexagon' }]
    }
    const starts = hoods.filter((h) => h.name.toLowerCase().startsWith(q))
    const within = hoods.filter((h) => !h.name.toLowerCase().startsWith(q) && h.name.toLowerCase().includes(q))
    return [...starts, ...within].slice(0, MAX_LOCAL).map((h) => ({
      label: h.name,
      sub: `neighbourhood · ${h.n} hexagons${h.borough ? ` · ${h.borough}` : ''}`,
      lat: h.lat,
      lon: h.lon,
      borough: h.borough,
      kind: 'neighborhood' as const,
    }))
  }, [query, hoods, cellIds])

  // remote suggestions, debounced; a newer keystroke aborts the older request
  const text = query.trim()
  const wantRemote = text.length >= 3 && !H3_ID.test(text)
  useEffect(() => {
    if (!wantRemote) return
    const ctl = new AbortController()
    const timer = setTimeout(() => {
      setBusyText(text)
      geosearch(text, ctl.signal)
        .then((places) => {
          if (!ctl.signal.aborted) setRemote({ text, places })
        })
        .catch(() => {
          if (!ctl.signal.aborted) setRemote({ text, places: [] })
        })
        .finally(() => {
          if (!ctl.signal.aborted) setBusyText(null)
        })
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ctl.abort()
    }
  }, [text, wantRemote])
  const busy = busyText === text
  // only suggestions for the current text count; older ones would flash under the cursor
  const results = useMemo(() => [...local, ...(wantRemote && remote.text === text ? remote.places : [])], [local, remote, wantRemote, text])
  const cursor = Math.min(active, Math.max(0, results.length - 1)) // the list shrinks under the cursor as results arrive

  // click outside closes the list
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [open])

  const pick = useCallback(
    (p: Place) => {
      onPick(p)
      setQuery(p.label)
      setOpen(false)
      inputRef.current?.blur()
    },
    [onPick],
  )

  const onKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActive(Math.min(results.length - 1, cursor + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive(Math.max(0, cursor - 1))
    } else if (e.key === 'Enter') {
      const p = results[cursor]
      if (p) pick(p)
    } else if (e.key === 'Escape') {
      setOpen(false)
      inputRef.current?.blur()
    }
  }

  const showList = open && text.length >= 2
  return (
    <div ref={boxRef} className="search">
      <label className="search-field panel" title="Find the hexagon for an address, place or neighbourhood">
        <SearchIcon size={16} />
        <input
          ref={inputRef}
          type="search"
          value={query}
          placeholder="Address or neighbourhood"
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          aria-label="Search an address"
          aria-expanded={showList}
          role="combobox"
          aria-controls="search-results"
          aria-autocomplete="list"
        />
        {busy && <span className="search-busy" aria-hidden />}
      </label>
      {showList && (
        <ul id="search-results" className="search-list panel" role="listbox">
          {results.length === 0 && <li className="search-empty muted small">{busy ? 'searching…' : 'no matches'}</li>}
          {results.map((p, i) => (
            <li
              key={`${p.kind}:${p.label}:${p.sub}`}
              role="option"
              aria-selected={i === cursor}
              className={`search-item ${i === cursor ? 'active' : ''}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()} // keep the input focused so the list does not close before the click
              onClick={() => pick(p)}
            >
              <span className="search-label">{p.label}</span>
              {p.sub && <span className="search-sub muted small">{p.sub}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
