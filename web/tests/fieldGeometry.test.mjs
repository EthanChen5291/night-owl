import assert from 'node:assert/strict'
import test from 'node:test'
import { cellToBoundary, gridDisk, latLngToCell } from 'h3-js'
import { FieldGeometryBuilder } from '../src/city/fieldGeometry.ts'
import { makeProjector } from '../src/city/projection.ts'
import { CityScene } from '../src/city/scene.ts'
import * as THREE from 'three'

const centre = { lat: 40.724, lon: -73.985 }
const projector = makeProjector(centre)
const hex = latLngToCell(centre.lat, centre.lon, 9)
const ring = cellToBoundary(hex).map(([lat, lon]) => projector.xy(lat, lon))
const areas = [{ outline: ring, bounds: { minX: -500, maxX: 500, minY: -500, maxY: 500 } }]
const land = [{ id: 'land', ring }]
const colours = new Map([[hex, '#21918c']])
function builder() {
  const b = new FieldGeometryBuilder(centre)
  b.setLand(land)
  b.setAreas(areas)
  return b
}

test('field buffers preserve linear colour and valid fan geometry', () => {
  const { pos, col, idx } = builder().build(colours, 6)
  assert.equal(pos.length / 3, 7 * 7)
  assert.equal(col.length / 4, pos.length / 3)
  assert.equal(idx.length, 7 * 18)
  assert.ok([...pos, ...col].every(Number.isFinite))
  assert.ok(idx.every((i) => i < pos.length / 3))
  const expected = new THREE.Color('#21918c')
  for (let i = 0; i < col.length; i += 4) {
    assert.ok(Math.abs(col[i] - expected.r) < 1e-7)
    assert.ok(Math.abs(col[i + 1] - expected.g) < 1e-7)
    assert.ok(Math.abs(col[i + 2] - expected.b) < 1e-7)
    assert.ok(col[i + 3] >= 0 && col[i + 3] <= 1)
  }
})

test('same-count cell replacement and area updates invalidate topology caches', () => {
  const b = builder()
  b.build(colours, 6)
  const replacement = new Map([[gridDisk(hex, 3).at(-1), '#fde725']])
  assert.deepEqual(b.build(replacement, 6), builder().build(replacement, 6))
  b.setAreas([])
  const fresh = builder()
  fresh.setAreas([])
  assert.deepEqual(b.build(replacement, 6), fresh.build(replacement, 6))
})

function sceneHarness() {
  const s = Object.create(CityScene.prototype)
  const messages = []
  let terminated = false
  const worker = { postMessage: (m) => messages.push(m), terminate: () => { terminated = true } }
  Object.assign(s, {
    disposed: false, fieldWorker: null, fieldWorkerFailed: false, fieldRevision: 0,
    fieldInFlight: null, fieldPending: false, fieldLand: land, fieldLandDirty: true,
    fieldAreasDirty: true, look: { field: { smooth: 6, neutral: 0xe6e4de, mix: .12, opacity: 1 } },
    cells: new Map([[hex, { pct_a: 10, pct_b: 80, silence: -30 }]]),
    mode: 'b', projector, areas: new Map([['manhattan', areas[0]]]),
    field: null, fieldNeutral: { value: new THREE.Color() }, fieldMix: { value: 0 },
    activeArea: null, flightAreas: new Set(), scene: new THREE.Scene(), cityLayerMeshes: new Map(),
    invalidate() {},
  })
  const old = globalThis.Worker
  globalThis.Worker = function () { return worker }
  return { s, worker, messages, get terminated() { return terminated }, restore: () => { globalThis.Worker = old } }
}

test('worker requests coalesce mode changes, reject stale replies, and retain the completed field', () => {
  const h = sceneHarness()
  try {
    h.s.rebuildField()
    assert.equal(h.messages.length, 1)
    assert.equal(h.messages[0].land, land)
    const geometry = builder().build(colours, 6)
    h.worker.onmessage({ data: { id: 1, geometry } })
    const oldField = h.s.field
    let disposed = 0
    oldField.geometry.addEventListener('dispose', () => disposed++)
    h.s.mode = 'a'; h.s.rebuildField()
    h.s.mode = 'silence'; h.s.rebuildField()
    h.s.mode = 'b'; h.s.rebuildField()
    assert.equal(h.messages.length, 2)
    assert.equal(h.s.field, oldField)
    assert.equal(h.messages[1].land, undefined)
    assert.equal(h.messages[1].areas, undefined)
    h.worker.onmessage({ data: { id: 2, geometry } })
    assert.equal(h.s.field, oldField)
    assert.equal(disposed, 0)
    assert.equal(h.messages.length, 3)
    assert.equal(h.messages[2].id, 4)
    h.s.flightAreas.add('manhattan')
    h.worker.onmessage({ data: { id: 4, geometry } })
    assert.notEqual(h.s.field, oldField)
    assert.equal(disposed, 1)
    assert.equal(h.s.field.visible, false, 'outgoing borough remains visible during return flight')
  } finally { h.restore() }
})

test('worker failure has no blocking UI fallback, and disposed scenes ignore late replies', () => {
  const h = sceneHarness()
  try {
    h.s.rebuildField()
    h.worker.onerror()
    assert.equal(h.terminated, true)
    h.s.rebuildField()
    assert.equal(h.messages.length, 1)
    h.s.disposed = true
    h.worker.onmessage({ data: { id: 1, geometry: builder().build(colours, 6) } })
    assert.equal(h.s.field, null)
  } finally { h.restore() }
})

test('cleared data removes the field and invalidates an in-flight reply', () => {
  const h = sceneHarness()
  try {
    h.s.rebuildField()
    const geometry = builder().build(colours, 6)
    h.worker.onmessage({ data: { id: 1, geometry } })
    assert.ok(h.s.field)
    h.s.rebuildField()
    h.s.cells.clear()
    h.s.rebuildField()
    assert.equal(h.s.field, null)
    h.worker.onmessage({ data: { id: 2, geometry } })
    assert.equal(h.s.field, null)
    assert.equal(h.messages.length, 2)
  } finally { h.restore() }
})
