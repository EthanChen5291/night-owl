import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'
import { BuildingOcclusionIndex } from '../src/city/occlusion.ts'

const box = (id, x0, y0, x1, y1, height) => ({
  id, h3: 'test', height, // no address: these buildings still cast shadows and obstruct the pin
  footprint: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
})
const point = (east, north, height) => ({ east, north, height })

test('a roof blocks only when the sightline drops to its height inside the footprint', () => {
  const from = point(0, 0, 100)
  const to = point(100, 0, 10)
  assert.equal(new BuildingOcclusionIndex([box('tall', 40, -10, 60, 10, 80)]).blocks(from, to), true)
  assert.equal(new BuildingOcclusionIndex([box('short', 40, -10, 60, 10, 30)]).blocks(from, to), false)
  assert.equal(new BuildingOcclusionIndex([box('away', 40, 20, 60, 30, 100)]).blocks(from, to), false)
})

test('the last ten metres remain excluded as in the old camera raycast', () => {
  const index = new BuildingOcclusionIndex([box('near-pin', 96, -2, 99, 2, 100)])
  assert.equal(index.blocks(point(0, 0, 20), point(100, 0, 20)), false)
  assert.equal(index.blocks(point(0, 0, 20), point(100, 0, 20), 0), true)
})

test('negative grid coordinates and concave footprints resolve to the actual covered intervals', () => {
  const negative = new BuildingOcclusionIndex([box('west', -50, -10, -40, 10, 50)])
  assert.equal(negative.blocks(point(-100, 0, 20), point(0, 0, 20)), true)
  const concave = new BuildingOcclusionIndex([{
    id: 'u', h3: 'test', height: 50,
    footprint: [[0, 0], [10, 0], [10, 10], [8, 10], [8, 2], [2, 2], [2, 10], [0, 10]],
  }])
  assert.equal(concave.blocks(point(3, 5, 20), point(7, 5, 20), 0), false)
  assert.equal(concave.blocks(point(-2, 5, 20), point(12, 5, 20), 0), true)
})

test('a camera above a building can leave it before the sightline falls below the roof', () => {
  const index = new BuildingOcclusionIndex([box('start', -5, -5, 10, 5, 30)])
  assert.equal(index.blocks(point(0, 0, 100), point(100, 0, 10)), false)
})

test('rectangular sightlines agree with Three raycasting across heights and offsets', () => {
  const from = point(0, 0, 200)
  const to = point(100, 0, 12)
  const origin = new THREE.Vector3(from.east, from.height, -from.north)
  const aim = new THREE.Vector3(to.east, to.height, -to.north)
  const direction = aim.clone().sub(origin)
  const ray = new THREE.Raycaster(origin, direction.clone().normalize(), 0, direction.length() - 10)
  let seed = 42
  const random = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32)
  for (let i = 0; i < 100; i++) {
    const x0 = 10 + random() * 75
    const x1 = x0 + 2 + random() * 12
    const y0 = -12 + random() * 20
    const y1 = y0 + 2 + random() * 10
    const height = 10 + random() * 190
    const building = box(String(i), x0, y0, x1, y1, height)
    const mesh = new THREE.Mesh(
      new THREE.BoxGeometry(x1 - x0, height, y1 - y0),
      new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }),
    )
    mesh.position.set((x0 + x1) / 2, height / 2, -(y0 + y1) / 2)
    mesh.updateMatrixWorld(true)
    assert.equal(new BuildingOcclusionIndex([building]).blocks(from, to), ray.intersectObject(mesh).length > 0, `case ${i}`)
    mesh.geometry.dispose()
    mesh.material.dispose()
  }
})
