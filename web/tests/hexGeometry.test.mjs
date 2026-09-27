import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'
import { buildHexPrism } from '../src/city/hexGeometry.ts'

const ring = [[-2, 0], [-1, -2], [1, -2], [2, 0], [1, 2], [-1, 2]]

test('convex prism keeps the exact footprint and raycasts on both caps and walls', () => {
  for (const points of [ring, [...ring].reverse()]) {
    const geometry = buildHexPrism(points)
    assert.deepEqual(geometry.boundingBox.min.toArray(), [-2, -2, 0])
    assert.deepEqual(geometry.boundingBox.max.toArray(), [2, 2, 1])
    assert.equal(geometry.index.count, points.length * 12)
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial())
    const rays = [
      [new THREE.Vector3(0, 0, 3), new THREE.Vector3(0, 0, -1)],
      [new THREE.Vector3(0, 0, -2), new THREE.Vector3(0, 0, 1)],
      [new THREE.Vector3(4, 0, 0.5), new THREE.Vector3(-1, 0, 0)],
    ]
    for (const [origin, direction] of rays) {
      const hit = new THREE.Raycaster(origin, direction).intersectObject(mesh)[0]
      assert.ok(hit)
      assert.ok(Math.abs(hit.distance - 2) < 1e-6)
    }
    geometry.dispose()
    mesh.material.dispose()
  }
})
