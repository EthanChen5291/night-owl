import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'
import { CityScene, PerfOverlay } from '../src/city/scene.ts'

function harness() {
  const pending = new Map()
  let nextId = 1
  let renders = 0
  let idleCalls = 0
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
  scene.perf = { resume: () => {}, idle: () => { idleCalls++ }, dispose() {} }
  scene.renderer.info = { render: { calls: 0, triangles: 0 }, memory: { geometries: 0, textures: 0 } }
  scene.perf.sample = () => {}
  scene.hexes = new Map()
  scene.tiles = new Map()
  scene.applyKeys = () => {}
  scene.reportView = () => {}
  scene.canvas = { removeEventListener() {} }
  scene.facade = { map: { dispose() {} }, emissive: { dispose() {} } }
  scene.viewReportTimer = null

  return {
    scene, doc, pending,
    get renders() { return renders },
    get idleCalls() { return idleCalls },
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
    assert.equal(h.idleCalls, 1)
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

test('idle meter uses the latest render counts after an early stop', () => {
  const previousDocument = globalThis.document
  const element = { style: {}, setAttribute() {}, remove() {}, textContent: '' }
  globalThis.document = { createElement: () => element, body: { appendChild() {} } }
  try {
    const meter = new PerfOverlay()
    meter.sample(performance.now() + 1001, 4, 2, 4, 100, 200, 6, 12, 3)
    meter.sample(performance.now() + 1002, 5, 3, 9, 300, 200, 9, 14, 4)
    meter.idle()
    assert.match(element.textContent, /scene idle  frames 2  fps 0/)
    assert.match(element.textContent, /draw calls 9  triangles 300/)
    assert.match(element.textContent, /hexes 200  tiles 9/)
    assert.match(element.textContent, /CPU frame mean\/p95/)
    meter.dispose()
  } finally { globalThis.document = previousDocument }
})
