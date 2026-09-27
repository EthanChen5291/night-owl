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

test('citywide borough entry starts nearby and settles without a long zoom', () => {
  const h = harness()
  try {
    h.scene.camera.position.setFromSphericalCoords(36000, 0.42, 0.35)
    const target = new THREE.Vector3(8000, 0, -5000)
    const destination = new THREE.Vector3().setFromSphericalCoords(3600, 0.95, 0.35).add(target)
    h.scene.pick = () => {}
    h.scene.areas.set('brooklyn', { centre: target, label: { visible: false } })
    h.scene.applyAreaVisibility = () => {}
    h.scene.setActiveArea('brooklyn')
    assert.equal(h.scene.flight.duration, 360)
    assert.ok(h.scene.controls.target.distanceTo(target) < 1e-6, 'entry begins at the borough')
    let radius = h.scene.camera.position.distanceTo(h.scene.controls.target)
    assert.ok(radius < 4500, 'entry skips the 36 km overview zoom')
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

test('back to city starts near the overview and settles without a street-level sweep', () => {
  const h = harness()
  try {
    const s = h.scene
    const borough = new THREE.Vector3(8000, 0, -5000)
    s.activeArea = 'brooklyn'
    s.controls.target.copy(borough)
    s.camera.position.copy(new THREE.Vector3(0, 174, 244).add(borough))
    s.pick = () => {}
    s.applyAreaVisibility = () => {}

    s.setActiveArea(null)
    assert.equal(s.flight.duration, 240)
    assert.ok(s.controls.target.length() < 1e-6, 'return begins at the city centre')
    let radius = s.camera.position.distanceTo(s.controls.target)
    assert.ok(radius > 30_000, 'return skips the street-to-overview sweep')
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
