import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'
import { CityScene } from '../src/city/scene.ts'

function harness() {
  const pending = new Map()
  let nextId = 1
  let renders = 0
  const previousDocument = globalThis.document
  const previousWindow = globalThis.window
  const previousRaf = globalThis.requestAnimationFrame
  const previousCancel = globalThis.cancelAnimationFrame
  const previousNow = performance.now
  let now = previousNow.call(performance)
  performance.now = () => now
  const doc = { hidden: false, removeEventListener() {} }
  globalThis.document = doc
  globalThis.window = { removeEventListener() {} }
  globalThis.requestAnimationFrame = (callback) => {
    const id = nextId++
    pending.set(id, callback)
    return id
  }
  globalThis.cancelAnimationFrame = (id) => pending.delete(id)

  // Exercise the real lifecycle methods without constructing a WebGL context.
  const scene = Object.create(CityScene.prototype)
  scene.loop = scene.loop.bind(scene)
  scene.invalidate = scene.invalidate.bind(scene)
  scene.handleVisibility = scene.handleVisibility.bind(scene)
  scene.disposed = false
  scene.raf = 0
  scene.urgentFrame = false
  scene.animationFrameDue = 0
  scene.lastFrame = performance.now()
  scene.keys = new Set()
  scene.flight = null
  scene.locator = null
  scene.visibleHexes = []
  scene.sites = []
  scene.nodes = new Map()
  scene.spots = []
  scene.areas = new Map()
  scene.pointerDirty = false
  scene.activeArea = null
  scene.hoveredArea = null
  scene.camera = { position: new THREE.Vector3(0, 100, 200) }
  scene.controls = { target: new THREE.Vector3(), update: () => false, removeEventListener() {}, dispose() {} }
  scene.key = { target: { position: new THREE.Vector3() }, position: new THREE.Vector3() }
  scene.renderer = { shadowMap: { needsUpdate: false }, render: () => { renders++ }, dispose() {} }
  scene.scene = { fog: null, traverse() {} }
  scene.renderer.info = { render: { calls: 0, triangles: 0 }, memory: { geometries: 0, textures: 0 } }
  scene.hexes = new Map()
  scene.tiles = new Map()
  scene.tileRequests = new Map()
  scene.tileInFlight = null
  scene.tileWorkerFailures = 0
  scene.tileGroup = new THREE.Group()
  scene.applyKeys = () => {}
  scene.reportView = () => {}
  scene.canvas = { removeEventListener() {} }
  scene.facade = { map: { dispose() {} }, emissive: { dispose() {} } }
  scene.viewReportTimer = null

  return {
    scene, doc, pending,
    get renders() { return renders },
    flush() {
      const [id, callback] = pending.entries().next().value ?? []
      assert.ok(callback, 'expected a scheduled frame')
      pending.delete(id)
      now += 17
      callback()
    },
    restore() {
      globalThis.document = previousDocument
      globalThis.window = previousWindow
      globalThis.requestAnimationFrame = previousRaf
      globalThis.cancelAnimationFrame = previousCancel
      performance.now = previousNow
    },
  }
}

test('invalidation coalesces and a settled scene stops scheduling frames', () => {
  const h = harness()
  try {
    h.scene.invalidate()
    h.scene.invalidate()
    assert.equal(h.pending.size, 1)
    h.flush()
    assert.equal(h.renders, 1)
    assert.equal(h.pending.size, 0)
  } finally { h.restore() }
})

test('hidden scenes do not queue work; visibility resumes; disposed scenes stay stopped', () => {
  const h = harness()
  try {
    h.scene.invalidate()
    h.scene.keys.add('w')
    assert.equal(h.pending.size, 1)
    h.doc.hidden = true
    h.scene.handleVisibility()
    assert.equal(h.pending.size, 0)
    assert.equal(h.scene.keys.size, 0)
    h.scene.invalidate()
    assert.equal(h.pending.size, 0)
    h.doc.hidden = false
    h.scene.handleVisibility()
    assert.equal(h.pending.size, 1)
    h.flush()
    assert.equal(h.renders, 1)
    h.scene.invalidate()
    assert.equal(h.pending.size, 1)
    h.scene.dispose()
    assert.equal(h.pending.size, 0)
    h.scene.invalidate()
    h.scene.handleVisibility()
    assert.equal(h.pending.size, 0)
  } finally { h.restore() }
})

test('controls continue until settled; animated frames are capped but urgent changes wake immediately', () => {
  const h = harness()
  try {
    let moving = true
    h.scene.controls.update = () => { const result = moving; moving = false; return result }
    h.scene.invalidate()
    h.flush()
    assert.equal(h.pending.size, 1)
    h.flush()
    assert.equal(h.renders, 2)
    assert.equal(h.pending.size, 0)

    h.scene.spots = [{}] // visible spot pulse keeps the render loop active
    h.scene.invalidate()
    h.flush()
    h.scene.animationFrameDue = performance.now() + 10_000
    const before = h.renders
    h.flush()
    assert.equal(h.renders, before)
    assert.equal(h.pending.size, 1)
    h.scene.invalidate()
    assert.equal(h.pending.size, 1)
    h.flush()
    assert.equal(h.renders, before + 1)
  } finally { h.restore() }
})


test('a stale tile reply starts the current request without restoring old geometry', () => {
  const h = harness()
  try {
    const sent = []
    h.scene.tileWorker = { postMessage: (message) => sent.push(message) }
    h.scene.tileInFlight = 1
    h.scene.tileRequests.set('current', { id: 2, area: null, buildings: [], roads: [], trees: [] })
    const reply = (id, tileId) => ({ id, tileId, ok: true, buildings: null, roads: null, ranges: [] })
    h.scene.receiveTile(reply(1, 'old'))
    assert.equal(h.scene.tiles.size, 0)
    assert.equal(sent.length, 1)
    assert.equal(sent[0].tileId, 'current')
    h.scene.receiveTile(reply(1, 'old'))
    assert.equal(sent.length, 1)
    h.scene.receiveTile(reply(2, 'current'))
    assert.deepEqual([...h.scene.tiles.keys()], ['current'])
    assert.equal(h.scene.tileRequests.size, 0)
    assert.equal(h.scene.tileInFlight, null)
  } finally { h.restore() }
})

test('an old-area reply is dropped and disposal terminates tile work', () => {
  const h = harness()
  try {
    let terminated = false
    h.scene.tileWorker = { postMessage: () => assert.fail('obsolete work restarted'), terminate: () => { terminated = true } }
    h.scene.tileInFlight = 1
    h.scene.activeArea = 'new'
    h.scene.tileRequests.set('old', { id: 1, area: 'old', buildings: [], roads: [], trees: [] })
    h.scene.receiveTile({ id: 1, tileId: 'old', ok: true, buildings: null, roads: null, ranges: [] })
    assert.equal(h.scene.tiles.size, 0)
    assert.equal(h.scene.tileRequests.size, 0)
    h.scene.dispose()
    assert.equal(terminated, true)
    h.scene.receiveTile({ id: 1, tileId: 'old', ok: true, buildings: null, roads: null, ranges: [] })
    assert.equal(h.scene.tiles.size, 0)
  } finally { h.restore() }
})

test('camera motion reuses shadows until it crosses a shadow-box boundary', () => {
  const h = harness()
  try {
    h.scene.controls.target.x = 255
    h.scene.invalidate()
    h.flush()
    assert.equal(h.scene.renderer.shadowMap.needsUpdate, false)
    h.scene.controls.target.x = 257
    h.scene.invalidate()
    h.flush()
    assert.equal(h.scene.key.target.position.x, 512)
    assert.equal(h.scene.key.position.x, 512 - 3200)
    assert.equal(h.scene.renderer.shadowMap.needsUpdate, true)
    h.scene.renderer.shadowMap.needsUpdate = false
    h.scene.controls.target.x = 300
    h.scene.invalidate()
    h.flush()
    assert.equal(h.scene.renderer.shadowMap.needsUpdate, false)
  } finally { h.restore() }
})
