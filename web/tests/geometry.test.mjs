import assert from 'node:assert/strict'
import test from 'node:test'
import { buildExtrusions, buildFlat, geometryTransfers, packGeometry, tintBuildingGeometry, unpackGeometry } from '../src/city/tileGeometry.ts'

const building = {
  id: 'lot-1', h3: '892a100d467ffff', height: 12,
  footprint: [[0, 0], [8, 0], [8, 5], [0, 5]],
}
const road = { id: 'road-1', ring: [[-2, -2], [10, -2], [10, -1], [-2, -1]] }

function snapshot(geometry) {
  return {
    attributes: Object.fromEntries(Object.entries(geometry.attributes).map(([name, attr]) => [name, Array.from(attr.array)])),
    index: geometry.index ? Array.from(geometry.index.array) : null,
    groups: geometry.groups.map((group) => ({ ...group })),
    sphere: geometry.boundingSphere ? {
      center: geometry.boundingSphere.center.toArray(), radius: geometry.boundingSphere.radius,
    } : null,
  }
}

test('building and road geometry survive typed-array transfer with groups and bounds', () => {
  const ranges = []
  const buildings = buildExtrusions([building], ranges, [12.8, 13.6])
  const roads = buildFlat([road])
  assert.ok(roads)
  assert.equal(ranges.length, 1)
  assert.deepEqual(buildings.groups.map((group) => group.materialIndex), [0, 1])

  for (const original of [buildings, roads]) {
    const before = snapshot(original)
    const packed = packGeometry(original)
    const transferred = structuredClone(packed, { transfer: geometryTransfers(packed) })
    assert.equal(packed.position.byteLength, 0)
    assert.deepEqual(snapshot(unpackGeometry(transferred)), before)
  }
})

test('short rings are skipped and a collinear roof does not keep unused indices', () => {
  assert.equal(buildFlat([{ id: 'short', ring: [[0, 0], [1, 0]] }]), null)
  const ranges = []
  const geometry = buildExtrusions([
    { ...building, id: 'short', footprint: [[0, 0], [1, 0]] },
    { ...building, id: 'line', footprint: [[0, 0], [1, 0], [2, 0], [3, 0]] },
  ], ranges, [12.8, 13.6])
  assert.equal(ranges.length, 1)
  const [walls, roof] = geometry.groups
  assert.equal(walls.count, 24)
  assert.equal(roof.count, geometry.index.count - walls.count)
  assert.deepEqual(snapshot(unpackGeometry(packGeometry(geometry))), snapshot(geometry))
})

test('worker-painted day and night colours survive transfer as normalized 16-bit attributes', () => {
  const ranges = []
  const geometry = buildExtrusions([building], ranges, [12.8, 13.6])
  tintBuildingGeometry(geometry, ranges, {
    colours: { [building.h3]: '#ff0000' },
    day: { facades: [0, 0, 0], buildingTint: 1, tintLift: 0 },
    night: { facades: [0x0000ff, 0x0000ff, 0x0000ff], buildingTint: 0, tintLift: 0 },
  })
  const packed = packGeometry(geometry)
  const copy = unpackGeometry(structuredClone(packed, { transfer: geometryTransfers(packed) }))
  assert.equal(copy.getAttribute('color').normalized, true)
  assert.equal(copy.getAttribute('colorNight').normalized, true)
  assert.deepEqual(Array.from(copy.getAttribute('color').array.slice(0, 3)), [65535, 0, 0])
  assert.equal(copy.getAttribute('colorNight').array[2] > 0, true)
})
