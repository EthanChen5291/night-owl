import { gridDisk, gridDistance, latLngToCell } from 'h3-js'
import type { Tile, TilesManifest } from '../types'

// Which r7 tiles to have resident for a camera target, within a building budget, and a small cache
// so flying back and forth does not refetch. The budget is what keeps a MacBook comfortable:
// ~90k buildings is about 3M vertices with shadows on.

export const CITYWIDE_DISTANCE = 12_000 // past this orbit distance nothing streams: the flat colour field carries the view
const BUDGET_BUILDINGS = 90_000
const MAX_RING = 2
const CACHE_TILES = 40

/** Only the active area's tiles ever load: the other boroughs stay flat so the frame budget goes to where you are. */
export function wantedTiles(manifest: TilesManifest, lat: number, lon: number, distance: number, areaId: string | null): string[] {
  if (!areaId || distance > CITYWIDE_DISTANCE) return []
  const centre = latLngToCell(lat, lon, manifest.res)
  const candidates = gridDisk(centre, MAX_RING)
    .filter((id) => manifest.tiles[id] && manifest.tiles[id].a === areaId)
    .sort((a, b) => gridDistance(centre, a) - gridDistance(centre, b))
  const out: string[] = []
  let used = 0
  for (const id of candidates) {
    const ring = gridDistance(centre, id)
    const n = manifest.tiles[id].b
    if (ring > 1 && used + n > BUDGET_BUILDINGS) continue // ring 0 and 1 always load; ring 2 only while it fits
    out.push(id)
    used += n
  }
  return out
}

export class TileCache {
  private tiles = new Map<string, Tile>()
  private inflight = new Map<string, Promise<Tile | null>>()

  get(id: string): Tile | undefined {
    const t = this.tiles.get(id)
    if (t) {
      // refresh recency
      this.tiles.delete(id)
      this.tiles.set(id, t)
    }
    return t
  }

  async load(id: string): Promise<Tile | null> {
    const have = this.get(id)
    if (have) return have
    let p = this.inflight.get(id)
    if (!p) {
      p = fetch(`/city/tiles/${id}.json`, { headers: { accept: 'application/json' } })
        .then(async (res) => {
          if (!res.ok || !(res.headers.get('content-type') ?? '').includes('json')) return null
          const body = (await res.json()) as Omit<Tile, 'id'>
          const tile: Tile = { id, buildings: body.buildings ?? [], roads: body.roads ?? [], trees: body.trees ?? [] }
          this.tiles.set(id, tile)
          while (this.tiles.size > CACHE_TILES) {
            const oldest = this.tiles.keys().next().value as string
            this.tiles.delete(oldest)
          }
          return tile
        })
        .catch(() => null)
        .finally(() => this.inflight.delete(id))
      this.inflight.set(id, p)
    }
    return p
  }
}

/** Keep cached tiles visible immediately and batch nearby responses into one map update. */
export function streamTiles(
  cache: Pick<TileCache, 'get' | 'load'>,
  wanted: string[],
  onChange: (tiles: Map<string, Tile>, pending: number) => void,
  delayMs = 40,
): () => void {
  let active = true
  let timer: ReturnType<typeof setTimeout> | null = null
  const resident = new Map<string, Tile>()
  const missing: string[] = []
  for (const id of wanted) {
    const tile = cache.get(id)
    if (tile) resident.set(id, tile)
    else missing.push(id)
  }
  let pending = missing.length
  const apply = () => {
    if (!active) return
    const tiles = new Map<string, Tile>()
    for (const id of wanted) {
      const tile = resident.get(id)
      if (tile) tiles.set(id, tile)
    }
    onChange(tiles, pending)
  }
  const schedule = () => {
    if (timer !== null) return
    timer = setTimeout(() => {
      timer = null
      apply()
    }, delayMs)
  }
  apply()
  for (const id of missing) {
    void cache.load(id).then((tile) => {
      if (!active) return
      if (tile) resident.set(id, tile)
      pending--
      schedule()
    })
  }
  return () => {
    active = false
    if (timer !== null) clearTimeout(timer)
  }
}
