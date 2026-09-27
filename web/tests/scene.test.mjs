import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'
import { CityScene } from '../src/city/scene.ts'
import { installBuildingTheme } from '../src/city/themeMaterials.ts'

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
  scene.look = { sun: { shadows: true } }
  scene.raf = 0
  scene.urgentFrame = false
  scene.animationFrameDue = 0
  scene.lastFrame = performance.now()
  scene.keys = new Set()
  scene.flight = null
  scene.flightAreas = new Set()
  scene.renderedHexes = new WeakSet()
  scene.pendingHexReveal = []
  scene.areaLayerGroup = { visible: true }
  scene.hexGroup = { visible: true }
  scene.locator = null
  scene.visibleHexes = []
  scene.sites = []
  scene.nodes = new Map()
  scene.spots = []
  scene.areas = new Map()
  scene.cityLayerGroup = { visible: true }
  scene.areaLayerMeshes = new Map()
  scene.transitioningArea = false
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
  scene.pendingHexes = []
  scene.pendingAreaHexes = []
  scene.pendingPriorityHexes = 0
  scene.tileAreas = {}
  scene.tiles = new Map()
  scene.requestedTiles = new Map()
  scene.tileRequests = new Map()
  scene.tileInFlight = null
  scene.tileWorkerFailures = 0
  scene.tileGroup = new THREE.Group()
  scene.applyKeys = () => {}
  scene.reportView = () => {}
  scene.projector = { latLon: (x, z) => ({ lat: z, lon: x }) }
  scene.callbacks = { onView() {} }
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

test('a close borough flight keeps city ground visible until destination ground is ready', () => {
  const h = harness()
  try {
    const s = h.scene
    s.activeArea = 'source'
    s.transitioningArea = false
    s.cityLayerGroup = { visible: false }
    s.areaLayerGroup = { visible: true }
    s.areaLayerMeshes = new Map()
    s.hexGroup = { visible: true }
    s.areas.set('destination', {
      centre: new THREE.Vector3(10_000, 0, 0),
      fill: { visible: false }, rim: { visible: false }, label: { visible: true },
    })
    s.camera.position.set(0, 174, 244)
    s.pick = () => {}

    s.setActiveArea('destination')
    assert.equal(s.cityLayerGroup.visible, true)
    assert.ok(Math.abs(s.flight.radius0 - 300) < 1)
    assert.ok(Math.abs(s.flight.radius1 - 300) < 1, 'the crossing stays close without a zoom-out arc')

    s.flight.start = performance.now() - s.flight.duration
    h.flush()
    assert.equal(s.flight, null)
    assert.equal(s.cityLayerGroup.visible, true, 'city ground remains while borough ground loads')
    s.buildLayers = (_group, meshes) => meshes.set('land', {})
    s.setAreaLayers({ land: [], parks: [], water: [] })
    assert.equal(s.cityLayerGroup.visible, true)
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

test('switching areas cancels obsolete tile geometry before dispatching the new area', () => {
  const h = harness()
  const previousWorker = globalThis.Worker
  const sent = []
  let terminated = false
  globalThis.Worker = class {
    postMessage(message) { sent.push(message) }
    terminate() {}
  }
  try {
    h.scene.tileWorker = { terminate() { terminated = true } }
    h.scene.tileInFlight = 1
    h.scene.activeArea = 'brooklyn'
    h.scene.tileRequests.set('old', { id: 1, area: 'manhattan', buildings: [], roads: [], trees: [] })
    h.scene.setTiles(new Map([['new', { buildings: [], roads: [], trees: [] }]]))
    assert.equal(terminated, true)
    assert.equal(sent.length, 1)
    assert.equal(sent[0].tileId, 'new')
  } finally {
    globalThis.Worker = previousWorker
    h.restore()
  }
})

test('cells removed while hex construction is pending leave the map', () => {
  const h = harness()
  try {
    const s = h.scene
    s.cells = new Map()
    s.pendingHexes = []
    s.scheduleHexBuild = s.applyAreaVisibility = s.retintBuildings = () => {}
    s.setCells([{ h3: 'pending' }], 'a')
    assert.equal(s.cells.has('pending'), true)
    assert.equal(s.pendingHexes.length, 1)
    s.setCells([], 'a')
    assert.equal(s.cells.has('pending'), false)
    assert.equal(s.pendingHexes.length, 0)
  } finally { h.restore() }
})

test('borough entry defers uncached cell classification beyond the click task', () => {
  const h = harness()
  try {
    const s = h.scene
    s.activeArea = 'manhattan'
    s.areaLayerGroup = { visible: false }
    s.hexGroup = { visible: false }
    s.cellArea = new Map()
    s.scheduleHexBuild = () => {}
    s.areaOfCell = () => assert.fail('polygon classification ran synchronously')
    for (let i = 0; i < 100; i++) s.hexes.set(String(i), { mesh: { visible: true } })
    s.applyAreaVisibility()
    assert.equal(s.pendingAreaHexes.length, 100)
    assert.equal(s.visibleHexes.length, 0)
    assert.equal([...s.hexes.values()].every((entry) => !entry.mesh.visible), true)
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

test('lighting changes keep building shader configuration intact', () => {
  const h = harness()
  try {
    const s = h.scene
    s.sky = { material: { uniforms: { zenith: { value: new THREE.Color() }, horizon: { value: new THREE.Color() } } } }
    s.ambient = new THREE.AmbientLight()
    s.hemi = new THREE.HemisphereLight()
    s.key = new THREE.DirectionalLight()
    s.key.castShadow = true
    s.ground = { material: new THREE.MeshStandardMaterial() }
    s.roadMaterial = new THREE.MeshStandardMaterial()
    s.treeMaterial = new THREE.MeshStandardMaterial()
    s.wallMaterial = new THREE.MeshStandardMaterial({ vertexColors: true })
    s.roofMaterial = new THREE.MeshStandardMaterial({ vertexColors: true })
    s.buildingTheme = installBuildingTheme([s.wallMaterial, s.roofMaterial])
    s.cityLayerMeshes = new Map()
    s.areaLayerMeshes = new Map()
    s.retintBuildings = s.setPlan = s.setSpots = () => assert.fail('lighting rebuilt scene data')
    const materialVersion = s.wallMaterial.version
    s.setPreset('night')
    assert.equal(s.key.castShadow, true)
    assert.equal(s.key.shadow.intensity, 0)
    s.setPreset('day')
    assert.equal(s.key.shadow.intensity, 1)
    assert.equal(s.wallMaterial.version, materialVersion)
  } finally { h.restore() }
})

test('borough risk cells retain their coloured height and h3 pick identity', () => {
  const h = harness()
  try {
    const s = h.scene
    s.mode = 'a'
    s.look = { hexOpacity: 0.56 }
    s.projector = { xy: (lat, lon) => [lon * 1000, lat * 1000] }
    s.hexVisible = () => true
    const cell = { h3: '892a100d2c3ffff', pct_a: 80 }
    const entry = s.makeHex(cell)
    assert.equal(entry.mesh.geometry.type, 'BufferGeometry')
    assert.equal(entry.mesh.geometry.index.count > 0, true)
    assert.equal(entry.mesh.material.opacity, 0.56)
    assert.equal(entry.mesh.userData.h3, cell.h3)
    assert.equal(entry.targetHeight, 102)
    assert.equal(entry.mesh.scale.z, 102)
    entry.mesh.geometry.dispose()
    entry.mesh.material.dispose()
  } finally { h.restore() }
})

test('citywide borough entry telescopes from the actual pose without an outward detour', () => {
  const h = harness()
  try {
    h.scene.camera.position.setFromSphericalCoords(36000, 0.42, 0.35)
    const target = new THREE.Vector3(8000, 0, -5000)
    const destination = new THREE.Vector3().setFromSphericalCoords(3600, 0.95, 0.35).add(target)
    h.scene.pick = () => {}
    h.scene.areas.set('brooklyn', { centre: target, label: { visible: false } })
    h.scene.applyAreaVisibility = () => {}
    const initial = h.scene.camera.position.clone()
    h.scene.setActiveArea('brooklyn')
    assert.ok(h.scene.flight.duration >= 900 && h.scene.flight.duration <= 1400)
    assert.ok(h.scene.camera.position.equals(initial), 'entry must not snap the camera')
    assert.equal(h.scene.controls.target.length(), 0, 'entry must not snap the target')
    let radius = h.scene.camera.position.distanceTo(h.scene.controls.target)
    assert.ok(Math.abs(radius - 36000) < 1e-6)
    let height = h.scene.camera.position.y
    for (let i = 0; h.scene.flight && i < 100; i++) {
      h.flush()
      const nextRadius = h.scene.camera.position.distanceTo(h.scene.controls.target)
      assert.ok(nextRadius <= radius + 1e-6, 'camera zoomed outward')
      assert.ok(h.scene.camera.position.y <= height + 1e-6, 'camera climbed')
      radius = nextRadius
      height = h.scene.camera.position.y
    }
    assert.equal(h.scene.flight, null)
    assert.ok(h.scene.camera.position.distanceTo(destination) < 1e-6)
    assert.ok(h.scene.controls.target.distanceTo(target) < 1e-6)
  } finally { h.restore() }
})

test('back to city expands continuously from the current street view', () => {
  const h = harness()
  try {
    const s = h.scene
    const borough = new THREE.Vector3(8000, 0, -5000)
    s.activeArea = 'brooklyn'
    s.controls.target.copy(borough)
    s.camera.position.copy(new THREE.Vector3(0, 174, 244).add(borough))
    s.pick = () => {}
    s.applyAreaVisibility = () => {}

    const initial = s.camera.position.clone()
    s.setActiveArea(null)
    assert.ok(s.flight.duration >= 1000 && s.flight.duration <= 1400)
    assert.ok(s.camera.position.equals(initial), 'return must not snap the camera')
    assert.ok(s.controls.target.equals(borough), 'return must not snap the target')
    let radius = s.camera.position.distanceTo(s.controls.target)
    assert.ok(radius < 301, 'return starts at street scale')
    while (s.flight) {
      h.flush()
      const nextRadius = s.camera.position.distanceTo(s.controls.target)
      assert.ok(nextRadius >= radius - 1e-6)
      radius = nextRadius
    }
    assert.ok(Math.abs(radius - 36_000) < 1e-6)
    assert.ok(s.controls.target.length() < 1e-6)
  } finally { h.restore() }
})


test('flights request their destination immediately and skip intermediate tile requests', () => {
  const h = harness()
  try {
    const views = []
    h.scene.callbacks.onView = view => views.push(view)
    h.scene.reportView = CityScene.prototype.reportView
    h.scene.pick = () => {}
    const first = new THREE.Vector3(8000, 0, -5000)
    h.scene.fly(first, first.clone().add(new THREE.Vector3(0, 3000, 4000)), 1000)
    assert.deepEqual(views, [{ lat: 5000, lon: 8000, distance: 5000 }])
    for (let i = 0; i < 10; i++) h.flush()
    assert.equal(views.length, 1)
    const second = new THREE.Vector3(-2000, 0, -1000)
    h.scene.fly(second, second.clone().add(new THREE.Vector3(0, 3000, 4000)), 1000)
    assert.deepEqual(views[1], { lat: 1000, lon: -2000, distance: 5000 })
    while (h.scene.flight) h.flush()
    assert.equal(views.length, 2)
  } finally { h.restore() }
})


test('mid-flight retargeting preserves the current pose and re-selection keeps progress', () => {
  const h = harness()
  try {
    const s = h.scene
    s.camera.position.setFromSphericalCoords(36000, 0.42, 0.35)
    s.pick = () => {}
    s.applyAreaVisibility = () => {}
    s.areas.set('a', { centre: new THREE.Vector3(8000, 0, -5000), label: {} })
    s.areas.set('b', { centre: new THREE.Vector3(-4000, 0, 5000), label: {} })
    s.setActiveArea('a')
    for (let i = 0; i < 20; i++) h.flush()
    const ongoing = s.flight
    s.setActiveArea('a')
    assert.equal(s.flight, ongoing, 'same destination must not restart the easing')
    const position = s.camera.position.clone()
    const target = s.controls.target.clone()
    s.setActiveArea('b')
    assert.ok(s.camera.position.distanceTo(position) < 1e-8)
    assert.ok(s.controls.target.distanceTo(target) < 1e-8)
    let radius = position.distanceTo(target)
    while (s.flight) {
      h.flush()
      const next = s.camera.position.distanceTo(s.controls.target)
      assert.ok(next <= radius + 1e-6)
      radius = next
    }
    assert.ok(s.controls.target.distanceTo(s.areas.get('b').centre) < 1e-6)
    assert.equal(s.controls.enabled, true)
    assert.equal(h.pending.size, 0, 'settled flight must not keep rendering')
  } finally { h.restore() }
})

test('manual input cancels a flight at its current pose and resumes viewport requests', () => {
  const h = harness()
  try {
    const s = h.scene
    s.pick = () => {}
    s.applyAreaVisibility = () => {}
    s.fly(new THREE.Vector3(1000, 0, 0), new THREE.Vector3(1000, 100, 200))
    h.flush()
    const position = s.camera.position.clone()
    s.interruptFlight()
    assert.equal(s.flight, null)
    assert.equal(s.controls.enabled, true)
    assert.ok(s.camera.position.equals(position))
    assert.ok(Number.isNaN(s.lastView.x))
    h.flush()
    assert.equal(h.pending.size, 0)
  } finally { h.restore() }
})

test('outgoing coloured hexagons remain during travel and clear at landing', () => {
  const h = harness()
  try {
    const s = h.scene
    s.activeArea = 'source'
    s.cellArea = new Map([['old', 'source'], ['new', 'destination']])
    s.hexes = new Map([['old', { mesh: { visible: true } }], ['new', { mesh: { visible: false } }]])
    s.areas.set('destination', { centre: new THREE.Vector3(1000, 0, 0), fill: {}, rim: {}, label: {} })
    s.pick = () => {}
    s.setActiveArea('destination')
    assert.equal(s.hexes.get('old').mesh.visible, true)
    assert.equal(s.hexes.get('new').mesh.visible, true)
    // This test checks visibility, not the material animation exercised elsewhere.
    s.visibleHexes = []
    s.flight.start -= s.flight.duration
    s.hexes.get('new').targetHeight = 1
    s.hexes.get('new').mesh.scale = { z: 1 }
    s.hexes.get('new').targetColour = new THREE.Color()
    s.hexes.get('new').mesh.material = { color: new THREE.Color() }
    h.flush()
    assert.equal(s.hexes.get('old').mesh.visible, false)
    assert.equal(s.hexes.get('new').mesh.visible, true)
    assert.equal(s.cityLayerGroup.visible, true)
  } finally { h.restore() }
})

test('departing tile geometry survives the flight and is disposed after landing', () => {
  const h = harness()
  try {
    const s = h.scene
    let disposed = 0
    const group = new THREE.Group()
    s.tileGroup.add(group)
    s.tiles.set('old', { area: 'source', group, buildings: { geometry: { dispose() { disposed++ } } } })
    s.activeArea = 'destination'
    s.flightAreas.add('source')
    s.flight = {}
    s.setTiles(new Map())
    assert.equal(s.tiles.size, 1)
    assert.equal(disposed, 0)
    s.flight = null
    s.flightAreas.clear()
    s.setTiles(s.requestedTiles)
    assert.equal(s.tiles.size, 0)
    assert.equal(disposed, 1)
  } finally { h.restore() }
})

test('starting a flight drains control inertia without changing the starting pose', () => {
  const h = harness()
  try {
    const s = h.scene
    let residual = true
    s.controls.enableDamping = true
    s.controls.update = () => {
      if (residual) {
        s.controls.target.x += 50
        s.camera.position.x += 50
        residual = false
      }
      return false
    }
    const position = s.camera.position.clone()
    const target = s.controls.target.clone()
    s.fly(new THREE.Vector3(1000, 0, 0), new THREE.Vector3(1000, 300, 400))
    assert.ok(s.camera.position.equals(position))
    assert.ok(s.controls.target.equals(target))
    assert.equal(s.controls.enableDamping, true)
  } finally { h.restore() }
})

test('reduced motion lands on the next frame and does not retain outgoing detail', () => {
  const h = harness()
  try {
    const s = h.scene
    globalThis.window.matchMedia = () => ({ matches: true })
    s.pick = () => {}
    s.fly(new THREE.Vector3(1000, 0, 0), new THREE.Vector3(1000, 300, 400))
    h.flush()
    assert.equal(s.flight, null)
    assert.ok(s.controls.target.equals(new THREE.Vector3(1000, 0, 0)))
    assert.equal(h.pending.size, 0)
  } finally { h.restore() }
})

test('late borough metadata can resolve an already selected destination', () => {
  const h = harness()
  try {
    const s = h.scene
    s.applyAreaVisibility = () => {}
    s.setActiveArea('brooklyn', true)
    const centre = new THREE.Vector3(8000, 0, -5000)
    s.areas.set('brooklyn', { centre, label: {} })
    s.setActiveArea('brooklyn')
    assert.ok(s.flight.t1.equals(centre))
  } finally { h.restore() }
})


test('an inward flight anchors shadows at the prefetched destination', () => {
  const h = harness()
  try {
    const s = h.scene
    s.camera.position.setFromSphericalCoords(36000, 0.42, 0.35)
    const target = new THREE.Vector3(8000, 0, -5000)
    s.fly(target, new THREE.Vector3().setFromSphericalCoords(3600, .95, .35).add(target))
    h.flush()
    const shadow = s.key.target.position.clone()
    assert.ok(Math.abs(shadow.x - target.x) <= 256)
    assert.ok(Math.abs(shadow.z - target.z) <= 256)
    s.renderer.shadowMap.needsUpdate = false
    for (let i = 0; i < 20; i++) h.flush()
    assert.ok(s.key.target.position.equals(shadow))
    assert.equal(s.renderer.shadowMap.needsUpdate, false)
  } finally { h.restore() }
})


test('first wide-view hex display is batched nearest the destination, without rebuilding geometry', () => {
  const h = harness()
  try {
    const s = h.scene
    s.camera.position.setFromSphericalCoords(36000, .42, .35)
    const entries = Array.from({ length: 250 }, (_, i) => ({
      mesh: { position: new THREE.Vector3(i, 0, 0), visible: true },
    }))
    s.visibleHexes = entries
    s.fly(new THREE.Vector3(), new THREE.Vector3().setFromSphericalCoords(3600, .95, .35))
    assert.equal(entries.filter(e => e.mesh.visible).length, 0)
    // Isolate reveal scheduling from the unrelated colour/height animation loop.
    s.visibleHexes = []
    h.flush()
    assert.equal(entries.filter(e => e.mesh.visible).length, 48)
    assert.equal(entries[0].mesh.visible, true)
    assert.equal(entries[249].mesh.visible, false)
    for (let i = 0; i < 5; i++) h.flush()
    assert.equal(entries.filter(e => e.mesh.visible).length, 250)
    assert.equal(s.pendingHexReveal.length, 0)
  } finally { h.restore() }
})
