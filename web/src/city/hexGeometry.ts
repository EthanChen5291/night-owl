import * as THREE from 'three'

/** One convex risk cell, one metre deep. The scene scales its z axis to the current height. */
export function buildHexPrism(ring: [number, number][]): THREE.BufferGeometry {
  if (ring.length < 3) throw new Error('A risk cell needs at least three corners')
  let signedArea = 0
  for (let i = 0; i < ring.length; i++) {
    const [x0, y0] = ring[i]
    const [x1, y1] = ring[(i + 1) % ring.length]
    signedArea += x0 * y1 - x1 * y0
  }
  const points = signedArea < 0 ? [...ring].reverse() : ring
  const n = points.length
  const wallStart = 2 * (n + 1)
  const pos = new Float32Array((wallStart + 4 * n) * 3)
  const normal = new Float32Array(pos.length)
  const IndexArray = wallStart + 4 * n > 65535 ? Uint32Array : Uint16Array
  const index = new IndexArray(n * 12)
  let cx = 0
  let cy = 0
  for (const [x, y] of points) { cx += x; cy += y }
  cx /= n
  cy /= n
  pos.set([cx, cy, 1], 0)
  normal.set([0, 0, 1], 0)
  const bottom = n + 1
  pos.set([cx, cy, 0], bottom * 3)
  normal.set([0, 0, -1], bottom * 3)
  let k = 0
  for (let i = 0; i < n; i++) {
    const [x0, y0] = points[i]
    const [x1, y1] = points[(i + 1) % n]
    pos.set([x0, y0, 1], (i + 1) * 3)
    normal.set([0, 0, 1], (i + 1) * 3)
    pos.set([x0, y0, 0], (bottom + i + 1) * 3)
    normal.set([0, 0, -1], (bottom + i + 1) * 3)
    index.set([0, i + 1, (i + 1) % n + 1], k)
    k += 3
    index.set([bottom, bottom + (i + 1) % n + 1, bottom + i + 1], k)
    k += 3
    const dx = x1 - x0
    const dy = y1 - y0
    const len = Math.hypot(dx, dy) || 1
    const nx = dy / len
    const ny = -dx / len
    const wall = wallStart + 4 * i
    pos.set([x0, y0, 0, x1, y1, 0, x1, y1, 1, x0, y0, 1], wall * 3)
    for (let j = 0; j < 4; j++) normal.set([nx, ny, 0], (wall + j) * 3)
    index.set([wall, wall + 1, wall + 2, wall, wall + 2, wall + 3], k)
    k += 6
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geometry.setAttribute('normal', new THREE.BufferAttribute(normal, 3))
  geometry.setIndex(new THREE.BufferAttribute(index, 1))
  geometry.computeBoundingBox()
  geometry.computeBoundingSphere()
  return geometry
}
