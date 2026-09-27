import type { Building } from '../types'
import { pointInRing } from './addresses'

// Sightlines for the close camera are a few hundred metres long. Indexing footprints
// keeps each candidate view from raycasting through every triangle in a merged tile.
const CELL_M = 80
const EPS = 1e-9

export interface SightPoint {
  east: number
  north: number
  height: number
}

interface Footprint {
  ring: [number, number][]
  roof: number
  minEast: number
  minNorth: number
  maxEast: number
  maxNorth: number
}

const cross = (ax: number, ay: number, bx: number, by: number) => ax * by - ay * bx
const key = (x: number, y: number) => `${x},${y}`

export class BuildingOcclusionIndex {
  private cells = new Map<string, Footprint[]>()

  constructor(buildings: Building[]) {
    for (const building of buildings) {
      const ring = building.footprint
      if (ring.length < 3) continue
      let minEast = Infinity
      let minNorth = Infinity
      let maxEast = -Infinity
      let maxNorth = -Infinity
      for (const [east, north] of ring) {
        minEast = Math.min(minEast, east)
        minNorth = Math.min(minNorth, north)
        maxEast = Math.max(maxEast, east)
        maxNorth = Math.max(maxNorth, north)
      }
      const entry: Footprint = {
        ring, roof: Math.max(1, building.height || 3), minEast, minNorth, maxEast, maxNorth,
      }
      for (let x = Math.floor(minEast / CELL_M); x <= Math.floor(maxEast / CELL_M); x++) {
        for (let y = Math.floor(minNorth / CELL_M); y <= Math.floor(maxNorth / CELL_M); y++) {
          const cell = key(x, y)
          const list = this.cells.get(cell)
          if (list) list.push(entry)
          else this.cells.set(cell, [entry])
        }
      }
    }
  }

  /** Whether a loaded building blocks the camera-to-pin segment before its final `stopShortM` metres. */
  blocks(from: SightPoint, to: SightPoint, stopShortM = 10): boolean {
    const dx = to.east - from.east
    const dy = to.north - from.north
    const dz = to.height - from.height
    const length = Math.hypot(dx, dy, dz)
    if (length <= stopShortM) return false
    const limit = 1 - stopShortM / length
    const endEast = from.east + dx * limit
    const endNorth = from.north + dy * limit
    const minEast = Math.min(from.east, endEast)
    const minNorth = Math.min(from.north, endNorth)
    const maxEast = Math.max(from.east, endEast)
    const maxNorth = Math.max(from.north, endNorth)
    const seen = new Set<Footprint>()
    for (let x = Math.floor(minEast / CELL_M); x <= Math.floor(maxEast / CELL_M); x++) {
      for (let y = Math.floor(minNorth / CELL_M); y <= Math.floor(maxNorth / CELL_M); y++) {
        for (const building of this.cells.get(key(x, y)) ?? []) {
          if (seen.has(building)) continue
          seen.add(building)
          if (building.maxEast < minEast || building.minEast > maxEast ||
              building.maxNorth < minNorth || building.minNorth > maxNorth) continue
          if (blocksFootprint(building, from, dx, dy, dz, limit)) return true
        }
      }
    }
    return false
  }
}

function blocksFootprint(building: Footprint, from: SightPoint, dx: number, dy: number, dz: number, limit: number): boolean {
  // Split the projected ray at each footprint edge. Within an interval the ray
  // is either inside or outside; its height changes linearly, so the lower end
  // determines whether it meets the roof or a wall.
  const crossings = [0, limit]
  const ring = building.ring
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [ax, ay] = ring[j]
    const [bx, by] = ring[i]
    const ex = bx - ax
    const ey = by - ay
    const denominator = cross(dx, dy, ex, ey)
    if (Math.abs(denominator) < EPS) continue
    const px = ax - from.east
    const py = ay - from.north
    const t = cross(px, py, ex, ey) / denominator
    const u = cross(px, py, dx, dy) / denominator
    if (t > 0 && t < limit && u >= -EPS && u <= 1 + EPS) crossings.push(t)
  }
  crossings.sort((a, b) => a - b)
  for (let i = 1; i < crossings.length; i++) {
    const start = crossings[i - 1]
    const end = crossings[i]
    if (end - start < EPS) continue
    const t = (start + end) / 2
    if (!pointInRing(from.east + dx * t, from.north + dy * t, ring)) continue
    if (Math.min(from.height + dz * start, from.height + dz * end) <= building.roof + EPS) return true
  }
  return false
}
