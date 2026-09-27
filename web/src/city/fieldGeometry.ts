import * as THREE from 'three'
import { cellToBoundary, cellToLatLng, gridDisk, latLngToCell, polygonToCells } from 'h3-js'
import type { Poly } from '../types'
import { pointInRing } from './addresses'
import { makeProjector, type LatLon, type Projector } from './projection'

export interface FieldArea {
  outline: [number, number][]
  bounds: { minX: number; maxX: number; minY: number; maxY: number }
}
export interface FieldGeometry {
  pos: Float32Array
  col: Float32Array
  idx: Uint32Array
}

const FIELD_FEATHER = [0, 0.18, 0.38, 0.6, 0.8, 0.92] // the colour field's alpha ring by ring in from a land border (Westchester, Nassau): it fades out over ~1 km instead of stopping on the city line. At the coast it runs at full strength to the shore and the land stencil cuts it there
const FIELD_ISLAND_MAX = 400 // land outside the borough outlines in pieces up to this many hexes (the Rockaways, Rikers, Randalls, the Jamaica Bay marshes) is still the city; bigger pieces are the neighbours
const FIELD_REACH = 30 // rings searched for the nearest coloured hex when an island has no coloured neighbour to inherit from (~5 km)

/** CPU-only city field builder. Owned by a worker, never the animation thread. */
export class FieldGeometryBuilder {
  private projector: Projector
  private landHexes: string[] = []
  private areas: FieldArea[] = []
  private fieldNeighbours: Map<string, string[]> | null = null
  private cellInBorough = new Map<string, boolean>()
  private cellKeys: string[] = []

  constructor(centre: LatLon) { this.projector = makeProjector(centre) }

  setLand(land: Poly[]) {
    this.landHexes = this.hexesOverLand(land)
    this.fieldNeighbours = null
  }

  setAreas(areas: FieldArea[]) {
    this.areas = areas
    this.cellInBorough.clear()
    this.fieldNeighbours = null
  }

  build(coloursByHex: Map<string, string>, smooth: number): FieldGeometry {
    const keys = [...coloursByHex.keys()]
    if (keys.length !== this.cellKeys.length || keys.some((h, i) => h !== this.cellKeys[i])) this.fieldNeighbours = null
    this.cellKeys = keys
    // 1. the hexes the field covers: land inside a borough plus every cell (the core), then one ring past that edge; with
    //    ring-1 neighbours within the set (cached until the set changes)
    const land = new Set(this.landHexes)
    const core = new Set<string>()
    for (const h of land) if (this.insideBorough(h)) core.add(h)
    for (const h3 of coloursByHex.keys()) core.add(h3)
    // land outside the outlines comes in pieces: small ones are the city's own islands and airports, so they join the core;
    // the large ones (Nassau past Far Rockaway) stay outside and get the feather
    const outside = new Set([...land].filter((h) => !core.has(h)))
    const seen = new Set<string>()
    for (const start of outside) {
      if (seen.has(start)) continue
      const piece = [start]
      seen.add(start)
      for (let i = 0; i < piece.length; i++) for (const nb of gridDisk(piece[i], 1)) if (outside.has(nb) && !seen.has(nb)) {
        seen.add(nb)
        piece.push(nb)
      }
      if (piece.length <= FIELD_ISLAND_MAX) for (const h of piece) core.add(h)
    }
    const hexes = new Set(core)
    for (const h of core) for (const n of gridDisk(h, 1)) hexes.add(n)
    let neighbours = this.fieldNeighbours
    if (!neighbours || neighbours.size !== hexes.size) {
      neighbours = new Map()
      for (const h of hexes) neighbours.set(h, gridDisk(h, 1).filter((n) => n !== h && hexes.has(n)))
      this.fieldNeighbours = neighbours
    }
    const colours = new Map<string, THREE.Color>()
    for (const [h3, colour] of coloursByHex) colours.set(h3, new THREE.Color(colour))
    // 2. hexes with no cell take the mean of their coloured neighbours, ring by ring outwards, so nothing on land is left grey
    let pending = [...hexes].filter((h) => !colours.has(h))
    while (pending.length) {
      const next: string[] = []
      const found = new Map<string, THREE.Color>()
      for (const h of pending) {
        const c = new THREE.Color(0, 0, 0)
        let n = 0
        for (const nb of neighbours.get(h) ?? []) {
          const cc = colours.get(nb)
          if (cc) {
            c.add(cc)
            n++
          }
        }
        if (n) found.set(h, c.multiplyScalar(1 / n))
        else next.push(h)
      }
      if (found.size === 0) {
        // islands: nothing coloured touches them, so each takes the mean of the nearest coloured hexes across the water
        for (const h of pending) {
          for (let k = 2; k <= FIELD_REACH; k++) {
            const near = gridDisk(h, k).filter((n) => colours.has(n))
            if (near.length === 0) continue
            const c = new THREE.Color(0, 0, 0)
            for (const n of near) c.add(colours.get(n)!)
            colours.set(h, c.multiplyScalar(1 / near.length))
            break
          }
        }
        break
      }
      for (const [h, c] of found) colours.set(h, c)
      pending = next
    }
    // 3. blur: each hex takes the mean of itself and its ring, `smooth` times
    let current = colours
    for (let pass = 0; pass < smooth; pass++) {
      const blurred = new Map<string, THREE.Color>()
      for (const [h, own] of current) {
        const c = own.clone()
        let n = 1
        for (const nb of neighbours.get(h) ?? []) {
          const cc = current.get(nb)
          if (cc) {
            c.add(cc)
            n++
          }
        }
        blurred.set(h, c.multiplyScalar(1 / n))
      }
      current = blurred
    }
    // 4. edges: the overshoot ring is transparent. Off land it only exists for the stencil to cut, so the shore hexes inside
    //    it keep full strength; on land (past the city line) it seeds a feather that climbs over the next rings in
    const alpha = new Map<string, number>()
    let frontier: string[] = []
    for (const h of current.keys()) {
      if (core.has(h)) continue
      alpha.set(h, FIELD_FEATHER[0])
      if (land.has(h)) frontier.push(h)
    }
    for (let ring = 1; ring < FIELD_FEATHER.length; ring++) {
      const next: string[] = []
      for (const h of frontier) for (const nb of neighbours.get(h) ?? []) if (current.has(nb) && !alpha.has(nb)) {
        alpha.set(nb, FIELD_FEATHER[ring])
        next.push(nb)
      }
      frontier = next
    }
    // 5. one fan per hex, corner colours and alpha averaged across the hexes that share the corner
    const cornerKey = (lat: number, lon: number) => `${lat.toFixed(6)},${lon.toFixed(6)}`
    const corners = new Map<string, { r: number; g: number; b: number; a: number; n: number }>()
    const rings: { h3: string; ring: [number, number][]; colour: THREE.Color; a: number }[] = []
    let nVerts = 0
    let nIdx = 0
    for (const [h3, colour] of current) {
      const ring = cellToBoundary(h3)
      const a = alpha.get(h3) ?? 1
      rings.push({ h3, ring, colour, a })
      for (const [lat, lon] of ring) {
        const k = cornerKey(lat, lon)
        const c = corners.get(k) ?? { r: 0, g: 0, b: 0, a: 0, n: 0 }
        c.r += colour.r
        c.g += colour.g
        c.b += colour.b
        c.a += a
        c.n++
        corners.set(k, c)
      }
      nVerts += ring.length + 1
      nIdx += ring.length * 3
    }
    const pos = new Float32Array(nVerts * 3)
    const col = new Float32Array(nVerts * 4) // rgba: three.js reads vertex alpha from a 4-wide colour attribute
    const idx = new Uint32Array(nIdx)
    let v = 0
    let k = 0
    for (const { h3, ring, colour, a } of rings) {
      const [cx, cy] = this.projector.xy(...cellToLatLng(h3))
      const centre = v
      pos.set([cx, 0, -cy], v * 3)
      col.set([colour.r, colour.g, colour.b, a], v * 4)
      v++
      ring.forEach(([lat, lon], i) => {
        const [x, y] = this.projector.xy(lat, lon)
        const c = corners.get(cornerKey(lat, lon))!
        pos.set([x, 0, -y], v * 3)
        col.set([c.r / c.n, c.g / c.n, c.b / c.n, c.a / c.n], v * 4)
        idx[k++] = centre
        idx[k++] = centre + 1 + i
        idx[k++] = centre + 1 + ((i + 1) % ring.length)
        v++
      })
    }
    return { pos, col, idx }
  }

  /** Every r9 hex whose centre is on land in the citywide bake. */
  private hexesOverLand(land: Poly[]): string[] {
    const set = new Set<string>()
    for (const poly of land) {
      if (poly.ring.length < 3) continue
      const loop = poly.ring.map(([x, y]) => {
        const { lat, lon } = this.projector.latLon(x, y)
        return [lat, lon] as [number, number]
      })
      const cells = polygonToCells([loop], 9)
      for (const h of cells) set.add(h)
      if (cells.length === 0) {
        // an islet smaller than a hex has no hex centre inside it: give it the hex under its centroid so it is still coloured
        const lat = loop.reduce((sum, [la]) => sum + la, 0) / loop.length
        const lon = loop.reduce((sum, [, lo]) => sum + lo, 0) / loop.length
        set.add(latLngToCell(lat, lon, 9))
      }
    }
    return [...set]
  }

  /** Whether an r9 cell's centre lies inside a borough outline. Unlike areaOfCell there is no tile fallback: this is the city line. */
  private insideBorough(h3: string): boolean {
    const cached = this.cellInBorough.get(h3)
    if (cached !== undefined) return cached
    const [cx, cy] = this.projector.xy(...cellToLatLng(h3))
    let inside = false
    for (const a of this.areas.values()) {
      if (cx >= a.bounds.minX && cx <= a.bounds.maxX && cy >= a.bounds.minY && cy <= a.bounds.maxY && pointInRing(cx, cy, a.outline)) {
        inside = true
        break
      }
    }
    this.cellInBorough.set(h3, inside)
    return inside
  }
}
