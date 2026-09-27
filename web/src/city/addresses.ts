import type { Building, Tile, Tree } from '../types'

// Answers "what is at x, y?" in local metres without touching three.js: a coarse grid over the
// district's buildings (point-in-footprint) and street trees (nearest pit, which carries the
// address it fronts). Built once per district; hover queries run every frame.

const CELL = 80 // metres per grid cell

export interface Hit {
  addr: string
  kind: 'building' | 'street'
  tree?: Tree
  building?: Building
  x: number
  y: number
}

export class AddressIndex {
  private static tileIndexes = new WeakMap<Tile, AddressIndex>()
  private buildings = new Map<string, Building[]>()
  private trees = new Map<string, Tree[]>()
  private parts: AddressIndex[] | null = null

  static fromTiles(tiles: Iterable<Tile>): AddressIndex {
    const index = new AddressIndex(null, null)
    index.parts = []
    for (const tile of tiles) {
      let part = AddressIndex.tileIndexes.get(tile)
      if (!part) {
        part = new AddressIndex(tile.buildings, tile.trees)
        AddressIndex.tileIndexes.set(tile, part)
      }
      index.parts.push(part)
    }
    return index
  }

  constructor(buildings: Building[] | null, trees: Tree[] | null) {
    for (const b of buildings ?? []) {
      if (!b.addr || b.footprint.length < 3) continue
      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      let maxY = -Infinity
      for (const [x, y] of b.footprint) {
        if (x < minX) minX = x
        if (x > maxX) maxX = x
        if (y < minY) minY = y
        if (y > maxY) maxY = y
      }
      for (let gx = Math.floor(minX / CELL); gx <= Math.floor(maxX / CELL); gx++) {
        for (let gy = Math.floor(minY / CELL); gy <= Math.floor(maxY / CELL); gy++) {
          const key = `${gx},${gy}`
          const list = this.buildings.get(key)
          if (list) list.push(b)
          else this.buildings.set(key, [b])
        }
      }
    }
    for (const t of trees ?? []) {
      if (!t.addr) continue
      const key = `${Math.floor(t.x / CELL)},${Math.floor(t.y / CELL)}`
      const list = this.trees.get(key)
      if (list) list.push(t)
      else this.trees.set(key, [t])
    }
  }

  get empty(): boolean {
    if (this.parts) return this.parts.every((part) => part.empty)
    return this.buildings.size === 0 && this.trees.size === 0
  }

  buildingAt(x: number, y: number): Building | null {
    if (this.parts) {
      for (const part of this.parts) {
        const building = part.buildingAt(x, y)
        if (building) return building
      }
      return null
    }
    const list = this.buildings.get(`${Math.floor(x / CELL)},${Math.floor(y / CELL)}`)
    if (!list) return null
    for (const b of list) if (pointInRing(x, y, b.footprint)) return b
    return null
  }

  nearestTree(x: number, y: number, maxM = 60): { tree: Tree; dist: number } | null {
    if (this.parts) {
      let best: { tree: Tree; dist: number } | null = null
      for (const part of this.parts) {
        const hit = part.nearestTree(x, y, maxM)
        if (hit && (!best || hit.dist < best.dist)) best = hit
      }
      return best
    }
    const gx = Math.floor(x / CELL)
    const gy = Math.floor(y / CELL)
    const reach = Math.ceil(maxM / CELL)
    let best: { tree: Tree; dist: number } | null = null
    for (let i = gx - reach; i <= gx + reach; i++) {
      for (let j = gy - reach; j <= gy + reach; j++) {
        const list = this.trees.get(`${i},${j}`)
        if (!list) continue
        for (const t of list) {
          const d = Math.hypot(t.x - x, t.y - y)
          if (d <= maxM && (!best || d < best.dist)) best = { tree: t, dist: d }
        }
      }
    }
    return best
  }

  /** The address to show for a point: the building it is in, else the nearest tree pit's street address. */
  at(x: number, y: number): Hit | null {
    const b = this.buildingAt(x, y)
    if (b?.addr) return { addr: b.addr, kind: 'building', building: b, x, y }
    const t = this.nearestTree(x, y)
    if (t?.tree.addr) return { addr: t.tree.addr, kind: 'street', tree: t.tree, x: t.tree.x, y: t.tree.y }
    return null
  }
}

/**
 * Somewhere an owl can actually hang: never inside a building. A point in a footprint moves to the nearest tree pit within
 * `maxTreeM`, else to the nearest point on the footprint's edge pushed 2.5 m out onto the sidewalk.
 */
export function offBuilding(index: AddressIndex, x: number, y: number, maxTreeM = 150): { x: number; y: number; tree?: Tree } {
  const b = index.buildingAt(x, y)
  if (!b) return { x, y }
  const t = index.nearestTree(x, y, maxTreeM)
  if (t) return { x: t.tree.x, y: t.tree.y, tree: t.tree }
  // nearest point on the ring, then step outward along the edge normal (away from the footprint's centroid)
  let best = { x, y, d: Infinity, nx: 0, ny: 0 }
  const ring = b.footprint
  let cx = 0
  let cy = 0
  for (const [px, py] of ring) {
    cx += px / ring.length
    cy += py / ring.length
  }
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [ax, ay] = ring[j]
    const [bx, by] = ring[i]
    const ex = bx - ax
    const ey = by - ay
    const len2 = ex * ex + ey * ey || 1
    const t = Math.max(0, Math.min(1, ((x - ax) * ex + (y - ay) * ey) / len2))
    const qx = ax + ex * t
    const qy = ay + ey * t
    const d = Math.hypot(qx - x, qy - y)
    if (d < best.d) {
      let nx = ey
      let ny = -ex
      if ((qx - cx) * nx + (qy - cy) * ny < 0) {
        nx = -nx
        ny = -ny
      }
      const n = Math.hypot(nx, ny) || 1
      best = { x: qx, y: qy, d, nx: nx / n, ny: ny / n }
    }
  }
  return { x: best.x + best.nx * 2.5, y: best.y + best.ny * 2.5 }
}

export function pointInRing(x: number, y: number, ring: [number, number][]): boolean {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}
