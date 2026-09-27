import * as THREE from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import type { Building, Poly } from '../types'

export interface BuildingRange {
  h3: string
  start: number
  count: number
  band: 0 | 1 | 2
  shade: number
}

export interface PackedGeometry {
  position: Float32Array
  normal: Float32Array | null
  color: Float32Array | null
  uv: Float32Array | null
  index: Uint16Array | Uint32Array | null
  groups: { start: number; count: number; materialIndex: number }[]
  sphere: { center: [number, number, number]; radius: number } | null
}

export interface TileGeometryRequest {
  id: number
  tileId: string
  buildings: Building[]
  roads: Poly[]
  facadeTileM: [number, number]
}

export type TileGeometryReply =
  | { id: number; tileId: string; ok: true; buildings: PackedGeometry | null; roads: PackedGeometry | null; ranges: BuildingRange[] }
  | { id: number; tileId: string; ok: false; error: string }

export function packGeometry(geometry: THREE.BufferGeometry): PackedGeometry {
  const attribute = (name: string) => geometry.getAttribute(name)?.array as Float32Array | undefined
  const sphere = geometry.boundingSphere
  return {
    position: attribute('position')!,
    normal: attribute('normal') ?? null,
    color: attribute('color') ?? null,
    uv: attribute('uv') ?? null,
    index: (geometry.getIndex()?.array as Uint16Array | Uint32Array | undefined) ?? null,
    groups: geometry.groups.map(({ start, count, materialIndex }) => ({ start, count, materialIndex: materialIndex ?? 0 })),
    sphere: sphere ? { center: [sphere.center.x, sphere.center.y, sphere.center.z], radius: sphere.radius } : null,
  }
}

export function unpackGeometry(packed: PackedGeometry): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(packed.position, 3))
  if (packed.normal) geometry.setAttribute('normal', new THREE.BufferAttribute(packed.normal, 3))
  if (packed.color) geometry.setAttribute('color', new THREE.BufferAttribute(packed.color, 3))
  if (packed.uv) geometry.setAttribute('uv', new THREE.BufferAttribute(packed.uv, 2))
  if (packed.index) geometry.setIndex(new THREE.BufferAttribute(packed.index, 1))
  for (const { start, count, materialIndex } of packed.groups) geometry.addGroup(start, count, materialIndex)
  if (packed.sphere) {
    const { center, radius } = packed.sphere
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(...center), radius)
  }
  return geometry
}

export function geometryTransfers(packed: PackedGeometry | null): Transferable[] {
  if (!packed) return []
  return [packed.position, packed.normal, packed.color, packed.uv, packed.index]
    .filter((array): array is Float32Array | Uint16Array | Uint32Array => array !== null)
    .map((array) => array.buffer)
}

function hashId(id: string): number {
  let h = 2166136261
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000
}

/** Every ring as a triangulated flat shape in shape space (x east, y north), merged into one geometry. */
export function buildFlat(polys: Poly[]): THREE.BufferGeometry | null {
  const parts: THREE.BufferGeometry[] = []
  for (const p of polys) {
    if (p.ring.length < 3) continue
    const shape = new THREE.Shape()
    p.ring.forEach(([x, y], i) => (i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y)))
    shape.closePath()
    const g = new THREE.ShapeGeometry(shape)
    g.deleteAttribute('uv')
    parts.push(g)
  }
  if (parts.length === 0) return null
  const merged = mergeGeometries(parts, false)
  for (const g of parts) g.dispose()
  if (!merged) return null
  merged.computeBoundingSphere()
  return merged
}

/**
 * Extrude every footprint into one indexed BufferGeometry: roof cap + walls, no bottom cap.
 * Built in shape space (x east, y north, z up); the mesh is rotated -90deg about x afterwards.
 * Walls get UVs in facade tiles (u along the wall, v up) and go in material group 0; roofs in group 1.
 * `ranges` receives the vertex range of each building so its colour can be updated per mode.
 */
export function buildExtrusions(buildings: Building[], ranges: BuildingRange[], facadeTileM: [number, number]): THREE.BufferGeometry {
  let nVerts = 0
  let nRoof = 0
  let nWall = 0
  for (const b of buildings) {
    const n = b.footprint.length
    if (n < 3) continue
    nVerts += n + 4 * n
    nRoof += (n - 2) * 3
    nWall += 6 * n
  }
  const pos = new Float32Array(nVerts * 3)
  const nor = new Float32Array(nVerts * 3)
  const col = new Float32Array(nVerts * 3)
  const uv = new Float32Array(nVerts * 2)
  const IndexArray = nVerts > 65_535 ? Uint32Array : Uint16Array
  const roofIdx = new IndexArray(nRoof)
  const wallIdx = new IndexArray(nWall)
  const [tileU, tileV] = facadeTileM
  let v = 0
  let kr = 0
  let kw = 0
  for (const b of buildings) {
    const pts = b.footprint
    const n = pts.length
    if (n < 3) continue
    const h = Math.max(1, b.height || 3)
    const start = v
    // enforce counter-clockwise so the walls face outward
    const ccw = THREE.ShapeUtils.isClockWise(pts.map(([x, y]) => new THREE.Vector2(x, y))) ? [...pts].reverse() : pts
    // roof cap
    const tri = THREE.ShapeUtils.triangulateShape(
      ccw.map(([x, y]) => new THREE.Vector2(x, y)),
      [],
    )
    for (let i = 0; i < n; i++) {
      pos.set([ccw[i][0], ccw[i][1], h], (v + i) * 3)
      nor.set([0, 0, 1], (v + i) * 3)
    }
    for (const [a, b2, c] of tri) {
      roofIdx[kr++] = v + a
      roofIdx[kr++] = v + b2
      roofIdx[kr++] = v + c
    }
    v += n
    // walls, 4 verts per edge for flat normals and a continuous facade u along the perimeter
    let along = 0
    for (let i = 0; i < n; i++) {
      const [x0, y0] = ccw[i]
      const [x1, y1] = ccw[(i + 1) % n]
      const dx = x1 - x0
      const dy = y1 - y0
      const len = Math.hypot(dx, dy) || 1
      const nx = dy / len
      const ny = -dx / len
      const base = v
      const u0 = along / tileU
      const u1 = (along + len) / tileU
      const v1 = h / tileV
      pos.set([x0, y0, 0, x1, y1, 0, x1, y1, h, x0, y0, h], base * 3)
      uv.set([u0, 0, u1, 0, u1, v1, u0, v1], base * 2)
      for (let j = 0; j < 4; j++) nor.set([nx, ny, 0], (base + j) * 3)
      wallIdx[kw++] = base
      wallIdx[kw++] = base + 1
      wallIdx[kw++] = base + 2
      wallIdx[kw++] = base
      wallIdx[kw++] = base + 2
      wallIdx[kw++] = base + 3
      v += 4
      along += len
    }
    ranges.push({
      h3: b.h3,
      start,
      count: v - start,
      band: h < 15 ? 0 : h < 45 ? 1 : 2,
      shade: 0.88 + 0.24 * hashId(b.id),
    })
  }
  // a degenerate roof (collinear points) triangulates to fewer triangles than n-2: trim the unused slots
  const index = new IndexArray(nWall + kr)
  index.set(wallIdx, 0)
  index.set(roofIdx.subarray(0, kr), nWall)
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('normal', new THREE.BufferAttribute(nor, 3))
  g.setAttribute('color', new THREE.BufferAttribute(col, 3))
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
  g.setIndex(new THREE.BufferAttribute(index, 1))
  g.addGroup(0, nWall, 0) // walls: facade material
  g.addGroup(nWall, kr, 1) // roofs: plain
  g.computeBoundingSphere()
  return g
}
