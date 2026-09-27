import { readSavedValue } from './storage'
import { latLngToCell } from 'h3-js'
import type { OwlNode, RatEvent } from './types'

// Owls are the placed sensor nodes. They live in localStorage for now: the contract has no
// endpoint for placements yet, and the stage demo only needs one.

const KEY = 'nightowl.owls'
export const STAGE_NODE_ID = 'demo-01' // what vision/pi/detect.py posts

export const eventKey = (e: RatEvent) => `${e.node_id}|${e.ts}`

export function loadOwls(): OwlNode[] {
  try {
    const raw = readSavedValue(KEY, 'barnowl.owls')
    const list = raw ? (JSON.parse(raw) as OwlNode[]) : []
    return Array.isArray(list) ? list.filter((n) => n && typeof n.id === 'string') : []
  } catch {
    return []
  }
}

export function saveOwls(owls: OwlNode[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(owls))
  } catch {
    /* private mode: placements just do not persist */
  }
}

/** Next owl: Owl n, and the first one takes the stage node id so the Pi's events land on it. */
export function newOwl(owls: OwlNode[], lat: number, lon: number, addr: string | null, nodeId?: string, treeId?: string): OwlNode {
  const n = owls.reduce((m, o) => Math.max(m, Number(o.id.replace('owl-', '')) || 0), 0) + 1
  const takenStage = owls.some((o) => o.nodeId === STAGE_NODE_ID)
  return {
    id: `owl-${n}`,
    nodeId: nodeId ?? (takenStage ? `owl-${n}` : STAGE_NODE_ID),
    name: `Owl ${n}`,
    lat,
    lon,
    h3: latLngToCell(lat, lon, 9),
    addr: addr ?? `block ${latLngToCell(lat, lon, 9).slice(-5)}`,
    placedAt: new Date().toISOString(),
    treeId,
  }
}

/** Sightings in the last `windowMin` minutes, scaled so `busyAt` per window reads as fully red. */
export function activityRate(sightings: RatEvent[], windowMin = 15, busyAt = 6): number {
  const since = Date.now() - windowMin * 60_000
  const n = sightings.filter((e) => new Date(e.ts).getTime() >= since).length
  return Math.min(1, n / busyAt)
}
