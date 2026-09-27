import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { cellToBoundary, cellToLatLng, cellToParent, latLngToCell } from 'h3-js'
import { colourFor, heightFor } from '../colours'
import type { Area, Building, Cell, CityLayers, HoverInfo, Mode, OwlNode, PlanNode, Poly, Preset, Spot, Tile, Tree, ViewInfo } from '../types'
import { makeProjector, type LatLon, type Projector } from './projection'
import { FACADE_TILE_M, facadeTextures } from './facade'
import { pointInRing, type AddressIndex } from './addresses'

// No React in here. App owns the data; Scene.tsx owns the lifecycle; this class owns three.js.
// Coordinates: local metres, x east, y north (from the projector); mapped to three.js x / -z.

export interface SceneCallbacks {
  onHover: (info: HoverInfo | null) => void
  onClick: (info: HoverInfo) => void
  onView: (view: ViewInfo) => void
}

interface HexEntry {
  mesh: THREE.Mesh<THREE.ExtrudeGeometry, THREE.MeshStandardMaterial>
  targetHeight: number
  targetColour: THREE.Color
  flashUntil: number
}

interface BuildingRange {
  h3: string
  start: number // first vertex index
  count: number
  band: 0 | 1 | 2 // low / mid / tall, picks the facade colour
  shade: number // per-building variation, ~0.9..1.1
}

interface TileMeshes {
  group: THREE.Group
  buildings: THREE.Mesh | null
  ranges: BuildingRange[]
  roads: THREE.Mesh | null
  trees: THREE.InstancedMesh | null
}

interface NodeMarker {
  group: THREE.Group
  badge: THREE.Mesh<THREE.CylinderGeometry, THREE.MeshBasicMaterial> // the flat red disc for the far view: unlit, unfogged, pure red
  ring: THREE.Mesh<THREE.RingGeometry, THREE.ShaderMaterial> // pink rim; sweeps yellow clockwise from 12 o'clock on hover
  pin: THREE.Group // the 3D pin for the close view: base, post, head
  pinMats: THREE.Material[]
  hit: THREE.Mesh // invisible, generous click target
  cover: THREE.Mesh<THREE.CircleGeometry, THREE.MeshBasicMaterial>
  rings: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>[]
  halo: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>
  h3: string
  phase: number
  hoverT: number // 0..1, eased: the marker swells a little under the pointer
  sweepT: number // 0..1: how far round the ring the yellow has swept
  bounceAt: number // when it was last clicked (it hops)
}

/** A site on the ground (a suggested hexagon, or a spot option inside one): a flat glass disc, a rim, a pulse, a letter chip. */
interface SiteMarker {
  group: THREE.Group
  disc: THREE.Mesh<THREE.CylinderGeometry, THREE.MeshBasicMaterial>
  rim: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>
  pulse: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial> | null
  chip: THREE.Sprite
  phase: number
}

interface AreaMarker {
  fill: THREE.Mesh<THREE.ShapeGeometry, THREE.MeshBasicMaterial>
  rim: THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>
  label: THREE.Sprite
  centre: THREE.Vector3
  outline: [number, number][] // local metres, for which cells belong to it
}

/** The band drawn around a searched hexagon once the camera has landed on it. */
interface Locator {
  group: THREE.Group
  band: THREE.Mesh<THREE.ShapeGeometry, THREE.MeshBasicMaterial>
  edge: THREE.Mesh<THREE.ShapeGeometry, THREE.MeshBasicMaterial>
  h3: string
  start: number | null // null until the flight has landed
  flashesLeft: number
  nextFlashAt: number
}

interface Flight {
  p0: THREE.Vector3
  t0: THREE.Vector3
  p1: THREE.Vector3
  t1: THREE.Vector3
  start: number
  duration: number
  bump: number
}

const FLASH_MS = 1500
const MAX_PIXEL_RATIO = 1.5
// the search locator: a bright band lands on the hexagon after the flight, starts wide, shrinks onto it, holds, fades
const LOCATE_GROW_MS = 1300
const LOCATE_HOLD_MS = 1000
const LOCATE_FADE_MS = 1500
const LOCATE_START_SCALE = 2.8
const LOCATE_FLASHES = 3 // the cell pulses this many times, back to back, once the camera has landed
const WIDE_DISTANCE = 9000 // orbit distance (m) past which the view counts as citywide (tiles stop streaming)
const NODE_RANGE = 110 // metres: the coverage disc, roughly the tree-guard rail's block face
const NODE_RED = 0xc0271d // a deep red, like a map pin, not a warning light
const NODE_PULSE_MS = 5200 // one ring leaves every ~2.6 s: a slow breath, not a siren
const NODE_RIPPLE_MS = 2400 // the selected owl's red edge ripples outward on this beat
const BADGE_NEAR = 450 // camera-to-owl distance (m) inside which the 3D pin has fully taken over from the badge
const BADGE_FAR = 1100 // ...and beyond which the badge has fully taken over from the pin; in between they crossfade
const SITE_RADIUS = 7 // metres: the site discs are smaller than an owl's badge
const BADGE_RADIUS = 12 // metres, at close range; it grows sublinearly with distance so it stays findable without looking pasted on
const NODE_PINK = 0xf3b4c4
const NODE_YELLOW = 0xffd54a
const BOUNCE_MS = 650
// markers draw after the prisms so the glass never tints them (the red stays red); the far badge skips the depth test,
// the close pin keeps it (buildings in front of it hide it) and the prisms do not write depth, so they never hide the pin
const MARKER_ORDER = 1
const HEX_PICK_DISTANCE = 1000 // closer than this the prisms are scenery: not hoverable, not clickable, the street underneath is
const CITY_DISTANCE = 36_000
const CITY_POLAR = 0.42 // near top-down: the citywide view is a map, not a skyline
const AREA_DISTANCE = 3600
const LABEL_SCALE = { city: 0.055, area: 0.04 } // name-tag height (x4 for width) as a fraction of its distance to the camera: constant on screen, bigger citywide
const VIEW_REPORT_MS = 250
// keyboard flight (inside an area): W/S forward/back, A/D left/right, J/K up/down
const KEY_MOVE = { KeyW: [0, 1], KeyS: [0, -1], KeyA: [-1, 0], KeyD: [1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] } as const
const KEY_LIFT = { KeyJ: 1, KeyK: -1 } as const

const FLAT_LAYERS = ['land', 'parks', 'water'] as const
type FlatLayer = (typeof FLAT_LAYERS)[number]

/** Everything that changes between the two lighting presets. */
interface Look {
  background: number
  fog: [number, number]
  zenith: number
  horizon: number
  ambient: { colour: number; intensity: number }
  hemi: { sky: number; ground: number; intensity: number }
  sun: { colour: number; intensity: number; shadows: boolean }
  exposure: number
  layers: Record<FlatLayer | 'ground' | 'roads' | 'trees', number>
  facades: [number, number, number]
  buildingTint: number
  tintLift: number
  windows: number
  windowColour: number
  hexOpacity: number
  /** the citywide 2D colour field: every cell colour is pulled `mix` of the way to `neutral` so the map stays calm */
  field: { neutral: number; mix: number; opacity: number }
  /** the search locator band and the halo either side of it: ink on paper by day, the flash's warm white on dark by night */
  locator: { band: number; edge: number }
  area: { fill: number; rim: number; ink: string }
}

const LOOKS: Record<Preset, Look> = {
  day: {
    background: 0xd3dde4,
    fog: [2200, 15000],
    zenith: 0x7ea3cc,
    horizon: 0xe3e9ec,
    ambient: { colour: 0xffffff, intensity: 0.3 },
    hemi: { sky: 0xa9bdd6, ground: 0x8c8274, intensity: 0.85 },
    sun: { colour: 0xfff0d8, intensity: 2.4, shadows: true },
    exposure: 1.05,
    layers: { ground: 0x6d9dbb, water: 0x6d9dbb, land: 0xd2cec5, roads: 0xbbb8b0, parks: 0x9ab97c, trees: 0x4e8a48 },
    facades: [0xb59782, 0xcdc4b3, 0x9fb4c6],
    buildingTint: 0.5,
    tintLift: 0.3,
    windows: 0,
    windowColour: 0xffffff,
    hexOpacity: 0.56,
    field: { neutral: 0xe6e4de, mix: 0.12, opacity: 0.9 },
    locator: { band: 0x16202b, edge: 0xffffff },
    area: { fill: 0xffffff, rim: 0xffffff, ink: '#16202b' },
  },
  night: {
    background: 0x05060a,
    fog: [3500, 14000],
    zenith: 0x04050a,
    horizon: 0x0d1220,
    ambient: { colour: 0x8090c0, intensity: 0.12 },
    hemi: { sky: 0x3a4a7a, ground: 0x0a0a10, intensity: 0.45 },
    sun: { colour: 0xb9c6ea, intensity: 1.2, shadows: false }, // moonlight, not sodium: the orange came from a warm sun on warm windows
    exposure: 1.0,
    layers: { ground: 0x04060c, water: 0x06091a, land: 0x10131b, roads: 0x1a1e2a, parks: 0x0e1d18, trees: 0x2c5a3a },
    facades: [0x262a35, 0x2a2d38, 0x2c3140],
    buildingTint: 0.22,
    tintLift: 0,
    windows: 0.3,
    windowColour: 0xdfe7f7, // lit windows read as a pale cool white, so the skyline stays blue-grey, not amber
    hexOpacity: 0.8,
    field: { neutral: 0x171b26, mix: 0.25, opacity: 0.84 },
    locator: { band: 0xfff0b0, edge: 0x1b202a },
    area: { fill: 0x9fc4ff, rim: 0xbfd8ff, ink: '#e6e8ef' },
  },
}

const smoothstep = (t: number) => t * t * (3 - 2 * t)

/** Development-only CPU and renderer counters, enabled with ?perf=1. */
class PerfOverlay {
  private element = document.createElement('pre')
  private frameMs = new Float32Array(120)
  private renderMs = new Float32Array(120)
  private frames = 0
  private lastUpdate = performance.now()
  private lastFrameCount = 0
  private lastStats = ''
  private active = false
  private latest = { calls: 0, triangles: 0, hexes: 0, tiles: 0, geometries: 0, textures: 0 }

  constructor() {
    this.element.id = 'city-perf'
    this.element.setAttribute('aria-label', 'City scene performance')
    this.element.style.cssText = 'position:fixed;top:140px;left:8px;z-index:10000;margin:0;padding:8px 10px;background:rgba(0,0,0,.82);color:#fff;font:12px/1.45 monospace;pointer-events:none;white-space:pre'
    document.body.appendChild(this.element)
  }

  sample(now: number, frameMs: number, renderMs: number, calls: number, triangles: number, hexes: number, tiles: number, geometries: number, textures: number) {
    const index = this.frames % this.frameMs.length
    this.frameMs[index] = frameMs
    this.renderMs[index] = renderMs
    this.frames++
    this.latest = { calls, triangles, hexes, tiles, geometries, textures }
    const elapsed = now - this.lastUpdate
    if (elapsed < 1000) return
    this.lastStats = this.formatStats()
    const fps = (this.frames - this.lastFrameCount) * 1000 / elapsed
    this.element.textContent = `scene frames ${this.frames}  fps ${fps.toFixed(1)}\n` + this.lastStats
    this.lastUpdate = now
    this.lastFrameCount = this.frames
  }

  private formatStats() {
    const count = Math.min(this.frames, this.frameMs.length)
    const summary = (samples: Float32Array) => {
      const sorted = Array.from(samples.subarray(0, count)).sort((a, b) => a - b)
      const mean = sorted.reduce((sum, value) => sum + value, 0) / count
      return `${mean.toFixed(1)} / ${sorted[Math.ceil(count * 0.95) - 1].toFixed(1)} ms`
    }
    return `CPU frame mean/p95 ${summary(this.frameMs)}\n` +
      `CPU render mean/p95 ${summary(this.renderMs)}\n` +
      `draw calls ${this.latest.calls}  triangles ${this.latest.triangles}\n` +
      `hexes ${this.latest.hexes}  tiles ${this.latest.tiles}\n` +
      `GPU geometries ${this.latest.geometries}  textures ${this.latest.textures}`
  }

  resume() {
    if (this.active) return
    this.active = true
    this.lastUpdate = performance.now()
    this.lastFrameCount = this.frames
    this.element.textContent = `scene rendering  frames ${this.frames}\n${this.lastStats}`
  }

  idle(state = 'idle') {
    this.active = false
    if (this.frames > 0) this.lastStats = this.formatStats()
    this.element.textContent = `scene ${state}  frames ${this.frames}  fps 0\n${this.lastStats}`
  }

  dispose() {
    this.element.remove()
  }
}

export class CityScene {
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private raycaster = new THREE.Raycaster()
  private pointer = new THREE.Vector2(2, 2)
  private pointerClient = { x: 0, y: 0 }
  private pointerDirty = false
  private pointerDown: { x: number; y: number; t: number } | null = null
  private keys = new Set<string>()
  private keysEnabled = false
  private lastFrame = performance.now()
  private lastView = { x: NaN, z: NaN, wide: false, t: 0 }
  private groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)
  private hexes = new Map<string, HexEntry>()
  private visibleHexes: HexEntry[] = []
  private visibleHexMeshes: THREE.Object3D[] = []
  private hexGroup = new THREE.Group()
  private field: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | null = null // the citywide 2D colour map
  private fieldCellByFace: string[] = []
  private planGroup = new THREE.Group()
  private cityLayerGroup = new THREE.Group() // citywide land / parks / water: the map under the colour field
  private areaLayerGroup = new THREE.Group() // the active area's own ground: the only land drawn inside an area
  private cityLayerMeshes = new Map<FlatLayer, THREE.Mesh>()
  private areaLayerMeshes = new Map<FlatLayer, THREE.Mesh>()
  private tileGroup = new THREE.Group()
  private tiles = new Map<string, TileMeshes>()
  private nodeGroup = new THREE.Group()
  private nodes = new Map<string, NodeMarker>()
  private selectedNode: string | null = null
  private areaGroup = new THREE.Group()
  private areas = new Map<string, AreaMarker>()
  private activeArea: string | null = null
  private hoveredArea: string | null = null
  private tileAreas: Record<string, string | null | undefined> = {} // r7 tile -> area id, from tiles.json
  private cellArea = new Map<string, string | null>() // r9 cell -> area id (by the borough outline, else the tile's area), memoised
  private ground: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial>
  private sky: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>
  private look: Look = LOOKS.day
  private wallMaterial: THREE.MeshStandardMaterial
  private roofMaterial: THREE.MeshStandardMaterial
  private roadMaterial: THREE.MeshStandardMaterial
  private treeMaterial: THREE.MeshStandardMaterial
  private facade = facadeTextures()
  private hemi: THREE.HemisphereLight
  private key: THREE.DirectionalLight
  private ambient: THREE.AmbientLight
  private projector: Projector
  private mode: Mode = 'a'
  private cells = new Map<string, Cell>()
  private hovered: string | null = null
  private hoveredNode: string | null = null
  private spotGroup = new THREE.Group()
  private sites: SiteMarker[] = []
  private planNodes: PlanNode[] = []
  private spots: Spot[] = []
  private lastHover: HoverInfo | null = null
  private callbacks: SceneCallbacks
  private index: AddressIndex | null = null
  private flight: Flight | null = null
  private locator: Locator | null = null
  private raf = 0
  private urgentFrame = false
  private animationFrameDue = 0
  private viewReportTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false
  private canvas: HTMLCanvasElement
  private perf: PerfOverlay | null = null

  constructor(canvas: HTMLCanvasElement, centre: LatLon, callbacks: SceneCallbacks) {
    this.canvas = canvas
    this.callbacks = callbacks
    this.projector = makeProjector(centre)
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.renderer.shadowMap.autoUpdate = false
    this.renderer.shadowMap.needsUpdate = true
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping

    // near = 20 (minDistance is 150) keeps enough depth precision for the flat layers to stack cleanly
    this.camera = new THREE.PerspectiveCamera(50, 1, 20, 150_000)
    this.controls = new OrbitControls(this.camera, canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.maxPolarAngle = Math.PI * 0.47
    this.controls.minDistance = 150
    this.controls.maxDistance = 40_000
    this.controls.addEventListener('change', this.invalidate)
    this.controls.target.set(0, 0, 0)
    this.camera.position.copy(orbitPosition(this.controls.target, CITY_DISTANCE, CITY_POLAR, 0.35))

    this.ground = new THREE.Mesh(
      new THREE.PlaneGeometry(160_000, 160_000),
      new THREE.MeshStandardMaterial({ color: LOOKS.day.layers.ground, roughness: 0.9, metalness: 0 }),
    )
    this.ground.rotation.x = -Math.PI / 2
    this.ground.position.y = -0.5
    this.ground.receiveShadow = true
    this.scene.add(this.ground)

    this.sky = makeSky()
    this.scene.add(this.sky)

    this.ambient = new THREE.AmbientLight(0xffffff, 0.15)
    this.hemi = new THREE.HemisphereLight(0x3a4a7a, 0x0a0a10, 0.5)
    // sun from the south-west so the faces the opening camera sees are lit; it follows the camera target
    this.key = new THREE.DirectionalLight(0xffb070, 1.6)
    this.key.shadow.mapSize.set(4096, 4096)
    const sc = this.key.shadow.camera
    sc.left = sc.bottom = -4200
    sc.right = sc.top = 4200
    sc.near = 500
    sc.far = 16_000
    this.key.shadow.bias = -0.0004
    this.key.shadow.normalBias = 2
    this.scene.add(this.ambient, this.hemi, this.key, this.key.target)

    this.wallMaterial = new THREE.MeshStandardMaterial({
      vertexColors: true,
      map: this.facade.map,
      emissiveMap: this.facade.emissive,
      emissive: new THREE.Color(0xffffff),
      emissiveIntensity: 0,
      roughness: 0.7,
      metalness: 0.08,
    })
    this.roofMaterial = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, metalness: 0 })
    this.roadMaterial = new THREE.MeshStandardMaterial({ color: LOOKS.day.layers.roads, roughness: 1, metalness: 0, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 })
    this.treeMaterial = new THREE.MeshStandardMaterial({ color: LOOKS.day.layers.trees, roughness: 0.95 })

    this.scene.add(this.cityLayerGroup, this.areaLayerGroup, this.tileGroup, this.areaGroup, this.hexGroup, this.planGroup, this.spotGroup, this.nodeGroup)
    this.setPreset('day')

    canvas.addEventListener('pointermove', this.handlePointerMove)
    canvas.addEventListener('pointerleave', this.handlePointerLeave)
    canvas.addEventListener('pointerdown', this.handlePointerDown)
    canvas.addEventListener('click', this.handleClick)
    window.addEventListener('keydown', this.handleKeyDown)
    window.addEventListener('keyup', this.handleKeyUp)
    window.addEventListener('blur', this.handleBlur)
    window.addEventListener('resize', this.resize)
    document.addEventListener('visibilitychange', this.handleVisibility)
    this.resize()
    if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('perf') === '1') this.perf = new PerfOverlay()
    this.invalidate()
  }

  // ---------------------------------------------------------------- public API

  private scheduleFrame = () => {
    if (this.disposed || document.hidden || this.raf) return
    this.perf?.resume()
    this.raf = requestAnimationFrame(this.loop)
  }

  private invalidate = () => {
    this.urgentFrame = true
    this.scheduleFrame()
  }

  get centre(): LatLon {
    return this.projector.centre
  }

  setAddressIndex(index: AddressIndex | null) {
    this.index = index
    this.pointerDirty = true
    this.invalidate()
  }

  /** Rebuild (or update) the hex prisms from the contract cells. Geometry is reused across updates. */
  setCells(cells: Cell[], mode: Mode) {
    this.mode = mode
    const seen = new Set<string>()
    for (const cell of cells) {
      this.cells.set(cell.h3, cell)
      seen.add(cell.h3)
      let entry = this.hexes.get(cell.h3)
      if (!entry) {
        entry = this.makeHex(cell)
        this.hexes.set(cell.h3, entry)
        this.hexGroup.add(entry.mesh)
      }
      entry.targetHeight = heightFor(mode, cell)
      entry.targetColour.set(colourFor(mode, cell))
    }
    for (const [h3, entry] of this.hexes) {
      if (!seen.has(h3)) {
        this.hexGroup.remove(entry.mesh)
        entry.mesh.geometry.dispose()
        entry.mesh.material.dispose()
        this.hexes.delete(h3)
        this.cells.delete(h3)
      }
    }
    this.applyAreaVisibility()
    this.rebuildField()
    this.retintBuildings()
    this.invalidate()
  }

  setMode(mode: Mode) {
    if (mode === this.mode) return
    this.mode = mode
    for (const [h3, entry] of this.hexes) {
      const cell = this.cells.get(h3)
      if (!cell) continue
      entry.targetHeight = heightFor(mode, cell)
      entry.targetColour.set(colourFor(mode, cell))
    }
    this.rebuildField()
    this.retintBuildings()
    this.invalidate()
  }

  setPreset(preset: Preset) {
    const L = LOOKS[preset]
    this.look = L
    if (this.locator) {
      this.locator.band.material.color.set(L.locator.band)
      this.locator.edge.material.color.set(L.locator.edge)
    }
    this.scene.background = new THREE.Color(L.background)
    this.scene.fog = new THREE.Fog(L.background, L.fog[0], L.fog[1])
    ;(this.sky.material.uniforms.zenith.value as THREE.Color).set(L.zenith)
    ;(this.sky.material.uniforms.horizon.value as THREE.Color).set(L.horizon)
    this.ambient.color.set(L.ambient.colour)
    this.ambient.intensity = L.ambient.intensity
    this.hemi.color.set(L.hemi.sky)
    this.hemi.groundColor.set(L.hemi.ground)
    this.hemi.intensity = L.hemi.intensity
    this.key.color.set(L.sun.colour)
    this.key.intensity = L.sun.intensity
    this.key.castShadow = L.sun.shadows
    this.renderer.shadowMap.needsUpdate = true
    this.renderer.toneMappingExposure = L.exposure
    this.ground.material.color.set(L.layers.ground)
    for (const [name, mesh] of this.cityLayerMeshes) (mesh.material as THREE.MeshStandardMaterial).color.set(L.layers[name])
    for (const [name, mesh] of this.areaLayerMeshes) (mesh.material as THREE.MeshStandardMaterial).color.set(L.layers[name])
    this.roadMaterial.color.set(L.layers.roads)
    this.treeMaterial.color.set(L.layers.trees)
    this.wallMaterial.emissiveIntensity = L.windows
    this.wallMaterial.emissive.set(L.windowColour)
    for (const [h3, entry] of this.hexes) entry.mesh.material.opacity = h3 === this.hovered ? Math.min(1, L.hexOpacity + 0.15) : L.hexOpacity
    this.rebuildField()
    this.setPlan(this.planNodes) // the chips carry the theme's ink
    this.setSpots(this.spots)
    for (const [id, a] of this.areas) {
      a.fill.material.color.set(L.area.fill)
      a.rim.material.color.set(L.area.rim)
      a.label.material.map?.dispose()
      const tex = textTexture((a.label.userData.name as string) ?? id, L.area.ink)
      a.label.material.map = tex
      a.label.userData.aspect = tex.image.width / tex.image.height
      a.label.material.needsUpdate = true
    }
    this.retintBuildings()
    this.invalidate()
  }

  setPlan(nodes: PlanNode[]) {
    this.planNodes = nodes
    this.disposeSites(this.planGroup)
    for (const node of nodes) {
      const m = this.makeSite(node.lat, node.lon, String(node.rank), { disc: 0xd9a441, rim: 0xffe3a3, pulse: false })
      m.group.userData = { plan: node }
      this.planGroup.add(m.group)
      this.sites.push(m)
    }
    this.invalidate()
  }

  setPlanVisible(visible: boolean) {
    this.planGroup.visible = visible
    this.invalidate()
  }

  /** The spot options (A, B, C) inside the opened suggested hexagon: red pulsing discs on their street trees. */
  setSpots(spots: Spot[]) {
    this.spots = spots
    this.disposeSites(this.spotGroup)
    spots.forEach((spot, i) => {
      const m = this.makeSite(spot.lat, spot.lon, String.fromCharCode(65 + i), { disc: NODE_RED, rim: NODE_PINK, pulse: true })
      m.group.userData = { spot }
      this.spotGroup.add(m.group)
      this.sites.push(m)
    })
    this.invalidate()
  }

  private disposeSites(group: THREE.Group) {
    this.sites = this.sites.filter((m) => {
      if (m.group.parent !== group) return true
      m.disc.geometry.dispose()
      m.disc.material.dispose()
      m.rim.geometry.dispose()
      m.rim.material.dispose()
      m.pulse?.geometry.dispose()
      m.pulse?.material.dispose()
      m.chip.material.map?.dispose()
      m.chip.material.dispose()
      return false
    })
    group.clear()
  }

  /** Same family as the owl badge: a squat translucent disc with a rim, drawn over the buildings but under the prism glass. */
  private makeSite(lat: number, lon: number, text: string, style: { disc: number; rim: number; pulse: boolean }): SiteMarker {
    const [x, y] = this.projector.xy(lat, lon)
    const over = { transparent: true, depthTest: false, depthWrite: false } as const
    const group = new THREE.Group()
    group.position.set(x, 0.5, -y)
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 0.18, 40), new THREE.MeshBasicMaterial({ color: style.disc, fog: false, toneMapped: false, ...over, opacity: 0.94 }))
    disc.position.y = 0.09
    disc.renderOrder = MARKER_ORDER + 0.5
    const rim = new THREE.Mesh(new THREE.RingGeometry(1.06, 1.24, 48), new THREE.MeshBasicMaterial({ color: style.rim, fog: false, toneMapped: false, ...over, opacity: 1, side: THREE.DoubleSide }))
    rim.rotation.x = -Math.PI / 2
    rim.position.y = 0.3
    rim.renderOrder = MARKER_ORDER + 0.4
    let pulse: SiteMarker['pulse'] = null
    if (style.pulse) {
      pulse = new THREE.Mesh(new THREE.RingGeometry(0.94, 1, 48), new THREE.MeshBasicMaterial({ color: style.rim, fog: false, toneMapped: false, ...over, opacity: 0.5, side: THREE.DoubleSide }))
      pulse.rotation.x = -Math.PI / 2
      pulse.position.y = 0.25
      pulse.renderOrder = MARKER_ORDER + 0.3
      group.add(pulse)
    }
    const chip = new THREE.Sprite(new THREE.SpriteMaterial({ map: textTexture(text, this.look.area.ink), depthTest: false, transparent: true }))
    chip.renderOrder = MARKER_ORDER + 0.6
    chip.userData = { aspect: (chip.material.map as THREE.CanvasTexture).image.width / (chip.material.map as THREE.CanvasTexture).image.height }
    group.add(disc, rim, chip)
    return { group, disc, rim, pulse, chip, phase: hashId(text) }
  }

  /** Emissive pulse on one cell for ~1.5 s. */
  flash(h3: string) {
    const entry = this.hexes.get(h3)
    if (!entry) return
    entry.flashUntil = performance.now() + FLASH_MS
    this.invalidate()
  }

  /**
   * Point out a hexagon after a search: a wide bright band waits for the camera flight to land, then shrinks onto the
   * cell's outline, holds, and fades; the cell itself flashes three times from the moment of landing, so the glow is
   * not spent mid-flight the way a single flash at pick time was.
   */
  locate(h3: string) {
    this.clearLocator()
    const ring = cellToBoundary(h3).map(([lat, lon]) => this.projector.xy(lat, lon))
    const [cx, cy] = this.projector.xy(...cellToLatLng(h3))
    // a hexagonal band between two scalings of the cell outline, centred on the cell
    const hexBand = (outerK: number, innerK: number, colour: number) => {
      const outer = new THREE.Shape()
      const hole = new THREE.Path()
      ring.forEach(([x, y], i) => {
        const px = x - cx
        const py = y - cy
        if (i === 0) {
          outer.moveTo(px * outerK, py * outerK)
          hole.moveTo(px * innerK, py * innerK)
        } else {
          outer.lineTo(px * outerK, py * outerK)
          hole.lineTo(px * innerK, py * innerK)
        }
      })
      outer.closePath()
      hole.closePath()
      outer.holes.push(hole)
      const material = new THREE.MeshBasicMaterial({ color: colour, transparent: true, opacity: 0, depthTest: false, depthWrite: false, fog: false, toneMapped: false, side: THREE.DoubleSide })
      return new THREE.Mesh(new THREE.ShapeGeometry(outer), material)
    }
    const edge = hexBand(1.05, 0.79, this.look.locator.edge)
    const band = hexBand(1, 0.84, this.look.locator.band)
    edge.renderOrder = MARKER_ORDER + 2 // over the prisms and the markers, never hidden by a building
    band.renderOrder = MARKER_ORDER + 3
    const group = new THREE.Group()
    group.add(edge, band)
    group.rotation.x = -Math.PI / 2
    group.position.set(cx, 3, -cy)
    group.visible = false
    this.scene.add(group)
    this.locator = { group, band, edge, h3, start: null, flashesLeft: LOCATE_FLASHES, nextFlashAt: 0 }
    this.invalidate()
  }

  private clearLocator() {
    if (!this.locator) return
    this.scene.remove(this.locator.group)
    for (const m of [this.locator.band, this.locator.edge]) {
      m.geometry.dispose()
      m.material.dispose()
    }
    this.locator = null
  }

  /** Glide the orbit target to a point, keeping the current distance and angle (or dolly to `distance`). */
  /** A JPEG of the current view for the assistant. Renders once more first: the drawing buffer is only
   *  guaranteed until the frame is composited, and copying it in the same task catches it. */
  screenshot(maxWidth = 1280): string {
    this.renderer.render(this.scene, this.camera)
    const src = this.renderer.domElement
    const scale = Math.min(1, maxWidth / src.width)
    const out = document.createElement('canvas')
    out.width = Math.round(src.width * scale)
    out.height = Math.round(src.height * scale)
    out.getContext('2d')?.drawImage(src, 0, 0, out.width, out.height)
    return out.toDataURL('image/jpeg', 0.82)
  }

  focusLatLon(lat: number, lon: number, distance?: number) {
    const [x, y] = this.projector.xy(lat, lon)
    const target = new THREE.Vector3(x, 0, -y)
    const current = this.camera.position.clone().sub(this.controls.target)
    // a close approach looks down more steeply (52 deg) and turns to an angle from which no building hides the spot
    const azimuth = Math.atan2(current.x, current.z)
    const view = distance && distance <= 400 ? this.clearApproach(target, distance, 0.66, azimuth) : { polar: 0.95, azimuth }
    const p1 = distance ? orbitPosition(target, distance, view.polar, view.azimuth) : target.clone().add(current)
    this.fly(target, p1, distance ? 1700 : 1200)
  }

  /**
   * An orbit angle from which a pin standing at `target` is not behind a building: try the current azimuth first, then
   * swing left and right in 30 deg steps, then look down more steeply; a ray from each candidate camera to the pin's post
   * must clear every loaded building mesh. Falls back to nearly straight down.
   */
  private clearApproach(target: THREE.Vector3, distance: number, polar: number, azimuth: number): { polar: number; azimuth: number } {
    const meshes = [...this.tiles.values()].map((t) => t.buildings).filter((m): m is THREE.Mesh => m !== null)
    const aim = target.clone().setY(12)
    const clear = (p: number, az: number) => {
      const pos = orbitPosition(target, distance, p, az)
      const dir = aim.clone().sub(pos)
      const len = dir.length()
      this.raycaster.set(pos, dir.normalize())
      this.raycaster.far = len - 10
      const blocked = this.raycaster.intersectObjects(meshes, false).length > 0
      this.raycaster.far = Infinity
      return !blocked
    }
    for (const p of [polar, 0.5, 0.35]) {
      for (let k = 0; k < 12; k++) {
        const az = azimuth + (k % 2 ? 1 : -1) * Math.ceil(k / 2) * (Math.PI / 6)
        if (clear(p, az)) return { polar: p, azimuth: az }
      }
    }
    return { polar: 0.25, azimuth }
  }

  /** Citywide flat layers (land, parks, water): the map under the colour field, hidden inside an area. */
  setCityLayers(layers: CityLayers) {
    this.buildLayers(this.cityLayerGroup, this.cityLayerMeshes, layers)
    this.invalidate()
  }

  /** The active area's own ground, the only land drawn while you are in it (null clears it). */
  setAreaLayers(layers: CityLayers | null) {
    this.buildLayers(this.areaLayerGroup, this.areaLayerMeshes, layers ?? { land: null, parks: null, water: null })
    this.invalidate()
  }

  private buildLayers(group: THREE.Group, meshes: Map<FlatLayer, THREE.Mesh>, layers: CityLayers) {
    for (const mesh of meshes.values()) {
      group.remove(mesh)
      mesh.geometry.dispose()
      ;(mesh.material as THREE.Material).dispose()
    }
    meshes.clear()
    const L = this.look
    FLAT_LAYERS.forEach((name, i) => {
      const polys = layers[name]
      if (!polys || polys.length === 0) return
      const geometry = buildFlat(polys)
      if (!geometry) return
      const material = new THREE.MeshStandardMaterial({
        color: L.layers[name],
        roughness: name === 'water' ? 0.35 : 1,
        metalness: 0,
        polygonOffset: true, // stack the coplanar layers without z-fighting
        polygonOffsetFactor: -(i + 1) * 2,
        polygonOffsetUnits: -(i + 1) * 2,
      })
      const mesh = new THREE.Mesh(geometry, material)
      mesh.rotation.x = -Math.PI / 2
      mesh.position.y = -0.4
      mesh.renderOrder = -20 + i
      mesh.receiveShadow = true
      meshes.set(name, mesh)
      group.add(mesh)
    })
  }

  /** The streamed tiles: add what is new, drop what left. Each tile is one building mesh, one road mesh, one canopy. */
  setTiles(tiles: Map<string, Tile>) {
    let changed = false
    for (const [id, t] of this.tiles) {
      if (tiles.has(id)) continue
      changed = true
      this.tileGroup.remove(t.group)
      t.buildings?.geometry.dispose()
      t.roads?.geometry.dispose()
      t.trees?.geometry.dispose()
      this.tiles.delete(id)
    }
    for (const [id, tile] of tiles) {
      if (this.tiles.has(id)) continue
      changed = true
      // a tile on a river holds both banks: only the active area's side is built (tiles are rebuilt on every area switch)
      const mine = (h3: string) => !this.activeArea || this.areaOfCell(h3) === this.activeArea
      const buildingList = tile.buildings.filter((b) => mine(b.h3))
      const roadList = tile.roads.filter((r) => {
        const { lat, lon } = this.projector.latLon(...ringCentre(r.ring))
        return mine(latLngToCell(lat, lon, 9))
      })
      const treeList = tile.trees.filter((t) => mine(t.h3))
      const group = new THREE.Group()
      let buildings: THREE.Mesh | null = null
      const ranges: BuildingRange[] = []
      if (buildingList.length) {
        buildings = new THREE.Mesh(buildExtrusions(buildingList, ranges), [this.wallMaterial, this.roofMaterial])
        buildings.rotation.x = -Math.PI / 2 // shape (x, y=north, z=up) -> three (x, y=up, -z)
        buildings.castShadow = true
        buildings.receiveShadow = true
        group.add(buildings)
      }
      let roads: THREE.Mesh | null = null
      const roadGeometry = roadList.length ? buildFlat(roadList) : null
      if (roadGeometry) {
        roads = new THREE.Mesh(roadGeometry, this.roadMaterial)
        roads.rotation.x = -Math.PI / 2
        roads.position.y = -0.4
        roads.renderOrder = -18
        roads.receiveShadow = true
        group.add(roads)
      }
      let trees: THREE.InstancedMesh | null = null
      if (treeList.length) {
        trees = buildTrees(treeList, this.treeMaterial)
        group.add(trees)
      }
      this.tileGroup.add(group)
      const entry = { group, buildings, ranges, roads, trees }
      this.tiles.set(id, entry)
      this.retintTile(entry)
    }
    if (changed) {
      this.renderer.shadowMap.needsUpdate = true
      this.invalidate()
    }
  }

  /** Area (borough) fills, coastlines and labels for the citywide view. */
  setAreas(areas: Area[]) {
    for (const a of this.areas.values()) {
      this.areaGroup.remove(a.fill, a.rim, a.label)
      a.fill.geometry.dispose()
      a.fill.material.dispose()
      a.rim.geometry.dispose()
      a.rim.material.dispose()
      a.label.material.map?.dispose()
      a.label.material.dispose()
    }
    this.areas.clear()
    const L = this.look
    for (const a of areas) {
      if (a.outline.length < 3) continue
      const shape = new THREE.Shape()
      a.outline.forEach(([x, y], i) => (i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y)))
      shape.closePath()
      const fill = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ color: L.area.fill, transparent: true, opacity: 0.08, depthWrite: false }))
      fill.rotation.x = -Math.PI / 2
      fill.position.y = 1
      fill.renderOrder = -5
      fill.userData = { areaId: a.id }
      const pts = [...a.outline, a.outline[0]].map(([x, y]) => new THREE.Vector3(x, 2, -y))
      const rim = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: L.area.rim, transparent: true, opacity: 0.55 }))
      const [cx, cy] = this.projector.xy(a.lat, a.lon)
      const tex = textTexture(a.name, L.area.ink)
      const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }))
      label.scale.set(3400, 850, 1)
      label.position.set(cx, 260, -cy)
      label.renderOrder = 20
      label.userData = { name: a.name, areaId: a.id, aspect: tex.image.width / tex.image.height }
      this.areaGroup.add(fill, rim, label)
      this.areas.set(a.id, { fill, rim, label, centre: new THREE.Vector3(cx, 0, -cy), outline: a.outline })
    }
    this.cellArea.clear()
    this.applyAreaVisibility()
    this.invalidate()
  }

  /** Which area each r7 tile belongs to (tiles.json): inside an area only that area's prisms stand. */
  setTileAreas(tileAreas: Record<string, string | null | undefined>) {
    this.tileAreas = tileAreas
    this.cellArea.clear()
    this.applyAreaVisibility()
    this.invalidate()
  }

  /** Fly into an area (or out to the city with null). `immediate` snaps, for the first frame. */
  setActiveArea(id: string | null, immediate = false) {
    this.activeArea = id
    this.keysEnabled = id !== null
    this.keys.clear()
    this.applyAreaVisibility()
    const a = id ? this.areas.get(id) : null
    const target = a ? a.centre.clone() : new THREE.Vector3(0, 0, 0)
    const current = this.camera.position.clone().sub(this.controls.target)
    const azimuth = Math.atan2(current.x, current.z)
    const p1 = a ? orbitPosition(target, AREA_DISTANCE, 0.95, azimuth) : orbitPosition(target, CITY_DISTANCE, CITY_POLAR, azimuth)
    if (immediate) {
      this.flight = null
      this.controls.target.copy(target)
      this.camera.position.copy(p1)
      this.controls.update()
      this.renderer.shadowMap.needsUpdate = true
      this.invalidate()
      return
    }
    this.fly(target, p1, a ? 2200 : 1900)
  }

  /** Owl markers: red dot, white rim, three pulse rings, a steady halo when selected. */
  setNodes(nodes: OwlNode[], selectedId: string | null) {
    this.selectedNode = selectedId
    const seen = new Set<string>()
    nodes.forEach((n, i) => {
      seen.add(n.id)
      let m = this.nodes.get(n.id)
      if (!m) {
        m = this.makeNodeMarker(n, i)
        this.nodes.set(n.id, m)
        this.nodeGroup.add(m.group)
      }
      const [x, y] = this.projector.xy(n.lat, n.lon)
      m.group.position.set(x, 0, -y)
      m.h3 = n.h3
      m.group.userData = { nodeId: n.id }
    })
    for (const [id, m] of this.nodes) {
      if (!seen.has(id)) {
        this.nodeGroup.remove(m.group)
        m.group.traverse((o) => {
          if (o instanceof THREE.Mesh) {
            o.geometry.dispose()
            ;(o.material as THREE.Material).dispose()
          }
        })
        this.nodes.delete(id)
      }
    }
    for (const [id, m] of this.nodes) m.halo.visible = id === selectedId
    this.renderer.shadowMap.needsUpdate = true
    this.invalidate()
  }

  /** Client-pixel position of an area's name tag (dev screenshot scripts click these). */
  tagAt(id: string): { x: number; y: number } | null {
    const a = this.areas.get(id)
    if (!a || !a.label.visible) return null
    const v = a.label.position.clone().project(this.camera)
    const rect = this.canvas.getBoundingClientRect()
    return { x: rect.left + ((v.x + 1) / 2) * rect.width, y: rect.top + ((1 - v.y) / 2) * rect.height }
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    if (this.viewReportTimer !== null) clearTimeout(this.viewReportTimer)
    this.canvas.removeEventListener('pointermove', this.handlePointerMove)
    this.canvas.removeEventListener('pointerleave', this.handlePointerLeave)
    this.canvas.removeEventListener('pointerdown', this.handlePointerDown)
    this.canvas.removeEventListener('click', this.handleClick)
    window.removeEventListener('keydown', this.handleKeyDown)
    window.removeEventListener('keyup', this.handleKeyUp)
    window.removeEventListener('blur', this.handleBlur)
    window.removeEventListener('resize', this.resize)
    document.removeEventListener('visibilitychange', this.handleVisibility)
    this.perf?.dispose()
    this.perf = null
    this.controls.removeEventListener('change', this.invalidate)
    this.controls.dispose()
    for (const a of this.areas.values()) a.label.material.map?.dispose()
    for (const site of this.sites) site.chip.material.map?.dispose()
    this.scene.traverse((o) => {
      if (o instanceof THREE.Mesh || o instanceof THREE.Line || o instanceof THREE.Sprite) {
        o.geometry.dispose()
        const m = o.material as THREE.Material | THREE.Material[]
        if (Array.isArray(m)) m.forEach((x) => x.dispose())
        else m.dispose()
      }
    })
    this.facade.map.dispose()
    this.facade.emissive.dispose()
    this.renderer.dispose()
  }

  // ---------------------------------------------------------------- internals

  /**
   * Citywide: the flat map (citywide ground + colour field), every borough's fill, rim and name tag.
   * Inside an area: only that area's ground, its tiles and the prisms; the other boroughs keep their name tags so a click flies there.
   */
  private applyAreaVisibility() {
    const inArea = !!this.activeArea
    for (const [id, a] of this.areas) {
      a.fill.visible = !inArea
      a.rim.visible = !inArea
      a.label.visible = id !== this.activeArea
    }
    this.cityLayerGroup.visible = !inArea
    this.areaLayerGroup.visible = inArea
    this.hexGroup.visible = inArea
    this.visibleHexes = []
    this.visibleHexMeshes = []
    if (inArea) for (const [h3, entry] of this.hexes) {
      entry.mesh.visible = this.hexVisible(h3)
      if (entry.mesh.visible) {
        this.visibleHexes.push(entry)
        this.visibleHexMeshes.push(entry.mesh)
      }
    }
    if (this.field) this.field.visible = !inArea
    this.invalidate()
  }

  /** A prism stands only inside its own area; a cell no area claims (open water) shows everywhere. */
  private hexVisible(h3: string): boolean {
    if (!this.activeArea) return false
    const a = this.areaOfCell(h3)
    return a === null || a === this.activeArea
  }

  /** Which area an r9 cell belongs to: its centre against the borough outlines, else the area of its r7 tile. */
  private areaOfCell(h3: string): string | null {
    const cached = this.cellArea.get(h3)
    if (cached !== undefined) return cached
    const [cx, cy] = this.projector.xy(...cellToLatLng(h3))
    let area: string | null = null
    for (const [id, a] of this.areas) {
      if (pointInRing(cx, cy, a.outline)) {
        area = id
        break
      }
    }
    if (area === null) area = this.tileAreas[cellToParent(h3, 7)] ?? null
    this.cellArea.set(h3, area)
    return area
  }

  /**
   * The citywide 2D colour map: one flat mesh over every cell, vertex-coloured. Each hex corner takes the mean of the cells
   * that share it, so the field reads as a smooth gradient rather than a honeycomb; colours are muted towards the look's neutral.
   */
  private rebuildField() {
    this.fieldCellByFace = []
    if (this.field) {
      this.scene.remove(this.field)
      this.field.geometry.dispose()
      this.field.material.dispose()
      this.field = null
    }
    if (this.cells.size === 0) return
    const L = this.look
    const neutral = new THREE.Color(L.field.neutral)
    const cornerKey = (lat: number, lon: number) => `${lat.toFixed(6)},${lon.toFixed(6)}`
    const corners = new Map<string, { r: number; g: number; b: number; n: number }>()
    const rings: { cell: Cell; ring: [number, number][]; colour: THREE.Color }[] = []
    let nVerts = 0
    let nIdx = 0
    for (const cell of this.cells.values()) {
      const ring = cellToBoundary(cell.h3)
      const colour = new THREE.Color(colourFor(this.mode, cell)).lerp(neutral, L.field.mix)
      rings.push({ cell, ring, colour })
      for (const [lat, lon] of ring) {
        const k = cornerKey(lat, lon)
        const c = corners.get(k) ?? { r: 0, g: 0, b: 0, n: 0 }
        c.r += colour.r
        c.g += colour.g
        c.b += colour.b
        c.n++
        corners.set(k, c)
      }
      nVerts += ring.length + 1
      nIdx += ring.length * 3
    }
    const pos = new Float32Array(nVerts * 3)
    const col = new Float32Array(nVerts * 3)
    const idx = new Uint32Array(nIdx)
    let v = 0
    let k = 0
    for (const { cell, ring, colour } of rings) {
      const [cx, cy] = this.projector.xy(...cellToLatLng(cell.h3))
      const centre = v
      pos.set([cx, 0, -cy], v * 3)
      col.set([colour.r, colour.g, colour.b], v * 3)
      v++
      ring.forEach(([lat, lon], i) => {
        const [x, y] = this.projector.xy(lat, lon)
        const c = corners.get(cornerKey(lat, lon))!
        pos.set([x, 0, -y], v * 3)
        col.set([c.r / c.n, c.g / c.n, c.b / c.n], v * 3)
        idx[k++] = centre
        idx[k++] = centre + 1 + i
        idx[k++] = centre + 1 + ((i + 1) % ring.length)
        this.fieldCellByFace.push(cell.h3)
        v++
      })
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('color', new THREE.BufferAttribute(col, 3))
    g.setIndex(new THREE.BufferAttribute(idx, 1))
    g.computeBoundingSphere()
    // no depth test: from 36 km up a metre above the land is below depth precision, so it is ordered after the ground instead
    const material = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: L.field.opacity, depthWrite: false, depthTest: false, toneMapped: false })
    this.field = new THREE.Mesh(g, material)
    this.field.position.y = 0.6
    this.field.renderOrder = -8
    this.field.visible = !this.activeArea
    this.scene.add(this.field)
  }

  private fly(target: THREE.Vector3, position: THREE.Vector3, duration: number) {
    const p0 = this.camera.position.clone()
    this.flight = {
      p0,
      t0: this.controls.target.clone(),
      p1: position,
      t1: target,
      start: performance.now(),
      duration,
      bump: Math.min(9000, p0.distanceTo(position) * 0.28), // climb mid-flight so it reads as flying, not sliding
    }
    this.controls.enabled = false
    this.invalidate()
  }

  /** WASD / arrows slide the view across the ground, J/K lift and lower it. Speed follows the orbit distance. */
  private applyKeys(dt: number) {
    if (!this.keysEnabled || this.flight || this.keys.size === 0) return
    const dist = this.camera.position.distanceTo(this.controls.target)
    const speed = dist * 1.1 * dt
    const forward = this.controls.target.clone().sub(this.camera.position)
    forward.y = 0
    if (forward.lengthSq() < 1e-6) forward.set(0, 0, -1)
    forward.normalize()
    const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0))
    const move = new THREE.Vector3()
    let lift = 0
    for (const code of this.keys) {
      const m = KEY_MOVE[code as keyof typeof KEY_MOVE]
      if (m) move.addScaledVector(right, m[0]).addScaledVector(forward, m[1])
      const l = KEY_LIFT[code as keyof typeof KEY_LIFT]
      if (l) lift += l
    }
    if (move.lengthSq() > 0) {
      move.normalize().multiplyScalar(speed)
      this.camera.position.add(move)
      this.controls.target.add(move)
    }
    if (lift !== 0) {
      // up/down is a dolly along the view ray, clamped to the orbit limits
      const offset = this.camera.position.clone().sub(this.controls.target)
      const next = THREE.MathUtils.clamp(offset.length() * (1 + lift * 1.1 * dt), this.controls.minDistance, this.controls.maxDistance)
      offset.setLength(next)
      this.camera.position.copy(this.controls.target).add(offset)
    }
  }

  /**
   * A map pin with body: a deep red base, post and head standing on the street among the buildings, a white rim on the ground,
   * a semi-transparent white coverage disc, two slow pulse rings, and a red ripple along the coverage edge when selected.
   */
  private makeNodeMarker(node: OwlNode, i: number): NodeMarker {
    const group = new THREE.Group()
    const flat = { transparent: true, side: THREE.DoubleSide, depthWrite: false } as const
    // over = never hidden by a building (no depth test) yet under the prism glass (drawn before it): reads as ground level
    const over = { transparent: true, depthTest: false, depthWrite: false } as const
    // the badge: a squat, fully red cylinder, like a map app's marker
    const badge = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 0.22, 40), new THREE.MeshBasicMaterial({ color: NODE_RED, fog: false, toneMapped: false, ...over }))
    badge.position.y = 0.11
    badge.renderOrder = MARKER_ORDER + 0.5
    // the pink rim: a ring whose colour is decided per pixel by angle, so hovering can sweep it yellow clockwise from 12 o'clock
    const ring = new THREE.Mesh(new THREE.RingGeometry(1.08, 1.3, 64), sweepMaterial())
    ring.rotation.x = -Math.PI / 2
    ring.position.y = 0.3
    ring.renderOrder = MARKER_ORDER + 0.4
    // the click target: a wide invisible puck (raycasts hit it, nothing draws it)
    const hit = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 1, 12), new THREE.MeshBasicMaterial({ visible: false }))
    hit.position.y = 0.5
    // the pin is a real object in the street: depth-tested (buildings in front of it hide it), lit, casting a shadow,
    // with a soft contact shadow under its base so it sits on the pavement rather than hovering
    const pin = new THREE.Group()
    const red = new THREE.MeshStandardMaterial({ color: NODE_RED, roughness: 0.45, metalness: 0.08, emissive: NODE_RED, emissiveIntensity: 0.28, transparent: true, fog: false })
    const contact = new THREE.Mesh(new THREE.CircleGeometry(10, 32), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.22, depthWrite: false }))
    contact.rotation.x = -Math.PI / 2
    contact.position.y = 0.35
    const base = new THREE.Mesh(new THREE.CylinderGeometry(6.5, 8, 5, 28), red)
    base.position.y = 2.5
    const post = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 3.2, 20, 14), red)
    post.position.y = 15
    const head = new THREE.Mesh(new THREE.SphereGeometry(7.5, 24, 16), red)
    head.position.y = 28
    const gloss = new THREE.Mesh(new THREE.SphereGeometry(2.4, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.55 }))
    gloss.position.set(-2.6, 31.4, 2.6)
    ;[base, post, head, gloss].forEach((m, k) => {
      m.castShadow = true
      m.renderOrder = MARKER_ORDER + 0.6 + k * 0.1 // still before the prism, so its glass tints the pin like the buildings
    })
    contact.renderOrder = MARKER_ORDER + 0.55
    // the ghost: the same shape drawn only where something is in front of it (depth test reversed), faint, so a pin
    // behind a building is still locatable without pretending the building is not there
    const ghostMat = new THREE.MeshBasicMaterial({ color: NODE_RED, transparent: true, opacity: 0.28, depthFunc: THREE.GreaterDepth, depthWrite: false, fog: false, toneMapped: false })
    const ghosts = [base, post, head].map((m) => {
      const g = new THREE.Mesh(m.geometry, ghostMat)
      g.position.copy(m.position)
      g.renderOrder = MARKER_ORDER + 0.95
      return g
    })
    pin.add(contact, base, post, head, gloss, ...ghosts)
    const pinMats = [red, gloss.material, contact.material, ghostMat]
    const cover = new THREE.Mesh(new THREE.CircleGeometry(1, 96), new THREE.MeshBasicMaterial({ color: 0xffffff, ...flat, opacity: 0.2 }))
    cover.rotation.x = -Math.PI / 2
    cover.position.y = 1.2
    cover.scale.setScalar(NODE_RANGE)
    cover.renderOrder = 27
    const rings: NodeMarker['rings'] = []
    for (let k = 0; k < 2; k++) {
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.95, 1, 96), new THREE.MeshBasicMaterial({ color: 0xffffff, ...flat, opacity: 0.45 }))
      ring.rotation.x = -Math.PI / 2
      ring.position.y = 1.4
      ring.renderOrder = 28
      rings.push(ring)
    }
    const halo = new THREE.Mesh(new THREE.RingGeometry(0.97, 1, 96), new THREE.MeshBasicMaterial({ color: NODE_RED, ...flat, opacity: 0.7 }))
    halo.rotation.x = -Math.PI / 2
    halo.position.y = 1.5
    halo.scale.setScalar(NODE_RANGE * 1.04)
    halo.visible = false
    halo.renderOrder = 29
    for (const m of [cover, halo, ...rings]) {
      m.material.depthTest = false // the coverage disc and its pulses show through the buildings too
      m.renderOrder = MARKER_ORDER
    }
    group.add(cover, halo, ...rings, ring, badge, pin, hit)
    group.userData = { nodeId: node.id }
    return { group, badge, ring, pin, pinMats, hit, cover, rings, halo, h3: node.h3, phase: (i * 0.37) % 1, hoverT: 0, sweepT: 0, bounceAt: -1e9 }
  }

  private makeHex(cell: Cell): HexEntry {
    const ring = cellToBoundary(cell.h3).map(([lat, lon]) => this.projector.xy(lat, lon))
    const [cx, cy] = this.projector.xy(...cellToLatLng(cell.h3))
    const shape = new THREE.Shape()
    ring.forEach(([x, y], i) => {
      // shape is built around the cell centre so scale.z (the extrude axis) animates the height in place
      if (i === 0) shape.moveTo(x - cx, y - cy)
      else shape.lineTo(x - cx, y - cy)
    })
    shape.closePath()
    const geometry = new THREE.ExtrudeGeometry(shape, { depth: 1, bevelEnabled: false })
    const material = new THREE.MeshStandardMaterial({
      color: colourFor(this.mode, cell),
      roughness: 0.6,
      metalness: 0.05,
      transparent: true,
      opacity: this.look.hexOpacity,
      emissive: 0x000000,
      depthWrite: false, // glass: the owl pin inside a prism must still pass the depth test
    })
    const mesh = new THREE.Mesh(geometry, material)
    mesh.rotation.x = -Math.PI / 2
    mesh.position.set(cx, 0, -cy)
    mesh.scale.z = 1
    mesh.userData = { h3: cell.h3 }
    mesh.visible = this.hexVisible(cell.h3)
    return { mesh, targetHeight: heightFor(this.mode, cell), targetColour: new THREE.Color(material.color), flashUntil: 0 }
  }

  private retintBuildings() {
    for (const t of this.tiles.values()) this.retintTile(t)
  }

  private retintTile(t: TileMeshes) {
    if (!t.buildings) return
    const L = this.look
    const attr = t.buildings.geometry.getAttribute('color') as THREE.BufferAttribute
    const tmp = new THREE.Color()
    const base = new THREE.Color()
    const white = new THREE.Color(0xffffff)
    for (const range of t.ranges) {
      base.set(L.facades[range.band]).multiplyScalar(range.shade)
      const cell = this.cells.get(range.h3)
      if (cell) tmp.set(colourFor(this.mode, cell)).lerp(white, L.tintLift).lerp(base, 1 - L.buildingTint)
      else tmp.copy(base)
      for (let i = range.start; i < range.start + range.count; i++) attr.setXYZ(i, tmp.r, tmp.g, tmp.b)
    }
    attr.needsUpdate = true
  }

  private handlePointerMove = (e: PointerEvent) => {
    const rect = this.canvas.getBoundingClientRect()
    this.pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1)
    this.pointerClient = { x: e.clientX, y: e.clientY }
    this.pointerDirty = true
    this.invalidate()
  }

  private handlePointerLeave = () => {
    this.pointer.set(2, 2)
    this.pointerDirty = true
    this.invalidate()
  }

  private handlePointerDown = (e: PointerEvent) => {
    if (e.button !== 0) return
    this.pointerDown = { x: e.clientX, y: e.clientY, t: performance.now() }
  }

  /** `click` rather than `pointerup`: it still fires when OrbitControls holds pointer capture. */
  private handleClick = (e: MouseEvent) => {
    const down = this.pointerDown
    this.pointerDown = null
    if (e.button !== 0) return
    // a click is a press that did not drag (drags are the orbit); no time limit, a slow frame must not eat a click
    if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) return
    this.handlePointerMove(e as PointerEvent)
    this.pick()
    if (this.lastHover?.kind === 'node' && this.lastHover.nodeId) {
      const m = this.nodes.get(this.lastHover.nodeId)
      if (m) m.bounceAt = performance.now()
    }
    if (this.lastHover) this.callbacks.onClick(this.lastHover)
    this.invalidate()
  }

  private handleKeyDown = (e: KeyboardEvent) => {
    if (!this.keysEnabled || e.metaKey || e.ctrlKey || e.altKey) return
    const t = e.target as HTMLElement | null
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
    if (e.code in KEY_MOVE || e.code in KEY_LIFT) {
      this.keys.add(e.code)
      e.preventDefault()
      this.invalidate()
    }
  }

  private handleKeyUp = (e: KeyboardEvent) => {
    this.keys.delete(e.code)
    this.invalidate()
  }

  private handleBlur = () => {
    this.keys.clear()
    this.invalidate()
  }

  private handleVisibility = () => {
    if (document.hidden) {
      cancelAnimationFrame(this.raf)
      this.raf = 0
      this.keys.clear()
      this.perf?.idle('hidden')
    } else if (!this.disposed && !this.raf) {
      this.lastFrame = performance.now()
      this.invalidate()
    }
  }

  private resize = () => {
    const w = this.canvas.clientWidth || 1
    const h = this.canvas.clientHeight || 1
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    this.invalidate()
  }

  private pick() {
    this.pointerDirty = false
    let info: HoverInfo | null = null
    let hexHit: string | null = null
    let areaHit: string | null = null
    if (this.pointer.x <= 1 && this.pointer.x >= -1) {
      this.raycaster.setFromCamera(this.pointer, this.camera)
      const point = new THREE.Vector3()
      const onGround = this.raycaster.ray.intersectPlane(this.groundPlane, point) !== null
      const base: Omit<HoverInfo, 'kind'> | null = onGround
        ? (() => {
            const { lat, lon } = this.projector.latLon(point.x, -point.z)
            return { x: this.pointerClient.x, y: this.pointerClient.y, lat, lon, h3: latLngToCell(lat, lon, 9), addr: null }
          })()
        : null
      // 1. owls and suggested pins
      const markerHits = this.raycaster.intersectObjects([...this.nodeGroup.children, ...this.spotGroup.children, ...(this.planGroup.visible ? this.planGroup.children : [])], true)
      let marker: THREE.Object3D | null = null
      for (const h of markerHits) {
        let o: THREE.Object3D | null = h.object
        while (o && !o.userData.nodeId && !o.userData.plan && !o.userData.spot) o = o.parent
        if (o && (o.userData.nodeId || o.userData.plan || o.userData.spot)) {
          marker = o
          break
        }
      }
      if (marker && base) {
        if (marker.userData.nodeId) info = { ...base, kind: 'node', nodeId: marker.userData.nodeId as string }
        else if (marker.userData.spot) {
          const spot = marker.userData.spot as Spot
          info = { ...base, kind: 'spot', spotRank: spot.rank, lat: spot.lat, lon: spot.lon, h3: latLngToCell(spot.lat, spot.lon, 9), addr: spot.mount_address }
        } else {
          const plan = marker.userData.plan as PlanNode
          info = { ...base, kind: 'plan', planRank: plan.rank, lat: plan.lat, lon: plan.lon, h3: plan.h3 }
        }
      }
      // 2. the hex under the pointer (the prisms only stand inside an area; citywide the flat field carries the cell;
      //    close in they are glass over the street and no longer the thing you point at)
      const dist = this.camera.position.distanceTo(this.controls.target)
      if (!info && this.activeArea && dist > HEX_PICK_DISTANCE) {
        const hits = this.raycaster.intersectObjects(this.visibleHexMeshes, false)
        if (hits.length) hexHit = hits[0].object.userData.h3 as string
      }
      if (!info && !this.activeArea && this.field) {
        const fieldHit = this.raycaster.intersectObject(this.field, false)[0]
        if (typeof fieldHit?.faceIndex === 'number') hexHit = this.fieldCellByFace[fieldHit.faceIndex] ?? null
      }
      if (!info && !hexHit && !this.activeArea && base?.h3 && this.cells.has(base.h3)) hexHit = base.h3
      // 3. the boroughs: name tags always (except the one you are in), their shapes in the citywide view
      if (!info) {
        const targets: THREE.Object3D[] = []
        for (const [id, a] of this.areas) {
          if (id === this.activeArea) continue
          targets.push(a.label)
          if (!this.activeArea) targets.push(a.fill)
        }
        const hits = this.raycaster.intersectObjects(targets, false)
        if (hits.length) areaHit = hits[0].object.userData.areaId as string
      }
      if (!info && areaHit) {
        const a = this.areas.get(areaHit)!
        const at = base ?? (() => {
          const { lat, lon } = this.projector.latLon(a.centre.x, -a.centre.z)
          return { x: this.pointerClient.x, y: this.pointerClient.y, lat, lon, h3: null, addr: null }
        })()
        info = { ...at, kind: 'area', areaId: areaHit, h3: hexHit ?? at.h3 }
      }
      if (!info && base) {
        const at = this.index?.at(point.x, -point.z) ?? null
        if (areaHit) info = { ...base, kind: 'area', areaId: areaHit, h3: hexHit ?? base.h3 }
        else if (at) info = { ...base, kind: at.kind, addr: at.addr, h3: hexHit ?? base.h3, cellHit: !!hexHit }
        else info = { ...base, kind: hexHit ? 'cell' : 'ground', h3: hexHit ?? base.h3, cellHit: !!hexHit }
      }
    }
    if (hexHit !== this.hovered) {
      const prev = this.hovered ? this.hexes.get(this.hovered) : undefined
      const base = this.look.hexOpacity
      if (prev) prev.mesh.material.opacity = base
      const next = hexHit ? this.hexes.get(hexHit) : undefined
      if (next) next.mesh.material.opacity = Math.min(1, base + 0.15)
      this.hovered = hexHit
    }
    if (areaHit !== this.hoveredArea) {
      const prev = this.hoveredArea ? this.areas.get(this.hoveredArea) : undefined
      if (prev) prev.fill.material.opacity = 0.08
      const next = areaHit ? this.areas.get(areaHit) : undefined
      if (next) next.fill.material.opacity = 0.22
      this.hoveredArea = areaHit
    }
    this.hoveredNode = info?.kind === 'node' ? (info.nodeId ?? null) : null
    this.lastHover = info
    this.callbacks.onHover(info)
  }

  /** Tell the app where the camera looks whenever it has moved enough for the tile set to change. */
  private reportView(now: number, dist: number) {
    const t = this.controls.target
    const wide = dist > WIDE_DISTANCE
    const moved = Math.hypot(t.x - this.lastView.x, t.z - this.lastView.z)
    if (!(Number.isNaN(this.lastView.x) || moved > 200 || wide !== this.lastView.wide)) return
    if (now - this.lastView.t < VIEW_REPORT_MS) {
      if (this.viewReportTimer === null) this.viewReportTimer = setTimeout(() => {
        this.viewReportTimer = null
        this.invalidate()
      }, VIEW_REPORT_MS - (now - this.lastView.t))
      return
    }
    if (this.viewReportTimer !== null) {
      clearTimeout(this.viewReportTimer)
      this.viewReportTimer = null
    }
    this.lastView = { x: t.x, z: t.z, wide, t: now }
    const { lat, lon } = this.projector.latLon(t.x, -t.z)
    this.callbacks.onView({ lat, lon, distance: dist })
  }

  private loop = () => {
    if (this.disposed || document.hidden) {
      this.raf = 0
      return
    }
    this.raf = 0
    const now = performance.now()
    const urgent = this.urgentFrame
    this.urgentFrame = false
    if (!urgent && now + 0.5 < this.animationFrameDue) {
      this.scheduleFrame()
      return
    }
    // Decorative pulses top out near 60 rendered frames/s on high-refresh displays.
    this.animationFrameDue = urgent ? now + 1000 / 60 : Math.max(this.animationFrameDue + 1000 / 60, now + 1000 / 120)
    const frameStart = this.perf ? performance.now() : 0
    const dt = Math.min(0.05, (now - this.lastFrame) / 1000)
    this.lastFrame = now
    // camera flight
    if (this.flight) {
      const f = this.flight
      const s = smoothstep(Math.min(1, (now - f.start) / f.duration))
      this.camera.position.lerpVectors(f.p0, f.p1, s)
      this.camera.position.y += Math.sin(s * Math.PI) * f.bump
      this.controls.target.lerpVectors(f.t0, f.t1, s)
      if (s >= 1) {
        this.flight = null
        this.controls.enabled = true
        this.pointerDirty = true // what is under the still pointer has changed
      }
    }
    this.applyKeys(dt)
    const controlsChanged = this.controls.update()
    if (this.pointerDirty) this.pick()
    // the search locator starts when the flight lands: wide and bright, then it shrinks onto the cell, holds and fades
    if (this.locator) {
      const L = this.locator
      if (L.start === null && !this.flight) L.start = now
      if (L.start !== null) {
        if (L.flashesLeft > 0 && now >= L.nextFlashAt) {
          this.flash(L.h3)
          L.flashesLeft -= 1
          L.nextFlashAt = now + FLASH_MS
        }
        const t = now - L.start
        const g = L.group
        g.visible = true
        let scale = 1
        let opacity = 0
        if (t < LOCATE_GROW_MS) {
          const e = 1 - Math.pow(1 - t / LOCATE_GROW_MS, 3)
          scale = LOCATE_START_SCALE - (LOCATE_START_SCALE - 1) * e
          opacity = 0.55 + 0.4 * e
        } else if (t < LOCATE_GROW_MS + LOCATE_HOLD_MS) {
          scale = 1 + 0.03 * Math.sin((t - LOCATE_GROW_MS) / 90)
          opacity = 0.95
        } else if (t < LOCATE_GROW_MS + LOCATE_HOLD_MS + LOCATE_FADE_MS) {
          opacity = 0.95 * (1 - (t - LOCATE_GROW_MS - LOCATE_HOLD_MS) / LOCATE_FADE_MS)
        } else {
          this.clearLocator()
        }
        if (this.locator) {
          g.scale.setScalar(scale)
          L.band.material.opacity = opacity
          L.edge.material.opacity = opacity * 0.7
        }
      }
    }
    const dist = this.camera.position.distanceTo(this.controls.target)
    // the sun and its shadow box follow the target so shadows exist wherever you fly
    if (this.key.target.position.x !== this.controls.target.x || this.key.target.position.z !== this.controls.target.z) {
      this.renderer.shadowMap.needsUpdate = true
    }
    this.key.target.position.set(this.controls.target.x, 0, this.controls.target.z)
    this.key.position.set(this.controls.target.x - 3200, 4600, this.controls.target.z + 2800)
    // name tags sit on their borough and keep a constant size on screen (so they shrink in world terms as you close in),
    // bigger in the citywide view
    const labelK = this.activeArea ? LABEL_SCALE.area : LABEL_SCALE.city
    for (const [id, a] of this.areas) {
      if (!a.label.visible) continue
      const p = a.label.position.set(a.centre.x, 260, a.centre.z)
      const h = this.camera.position.distanceTo(p) * labelK * (id === this.hoveredArea ? 1.1 : 1)
      a.label.scale.set(h * ((a.label.userData.aspect as number) || 4), h, 1)
    }
    let hexAnimating = false
    const heightBlend = 1 - Math.pow(0.88, dt * 60)
    const colourBlend = 1 - Math.pow(0.85, dt * 60)
    for (const entry of this.visibleHexes) {
      const m = entry.mesh
      const heightLeft = entry.targetHeight - m.scale.z
      if (Math.abs(heightLeft) > 0.05) {
        m.scale.z += heightLeft * heightBlend
        hexAnimating = true
      } else if (heightLeft !== 0) m.scale.z = entry.targetHeight
      const colour = m.material.color
      const colourLeft = Math.abs(colour.r - entry.targetColour.r) + Math.abs(colour.g - entry.targetColour.g) + Math.abs(colour.b - entry.targetColour.b)
      if (colourLeft > 0.005) {
        colour.lerp(entry.targetColour, colourBlend)
        hexAnimating = true
      } else if (colourLeft !== 0) colour.copy(entry.targetColour)
      if (entry.flashUntil > now) {
        hexAnimating = true
        const t = (entry.flashUntil - now) / FLASH_MS
        const pulse = 0.5 + 0.5 * Math.sin(now / 80)
        m.material.emissive.set(0xffe9a8)
        m.material.emissiveIntensity = (0.4 + 0.6 * pulse) * t * 2.2
      } else if (m.material.emissiveIntensity !== 0) {
        m.material.emissiveIntensity = 0
      }
    }
    // site discs (suggested hexagons, spot options): sized like the owl badge, chip a constant size on screen, spots pulse
    for (const m of this.sites) {
      const d = this.camera.position.distanceTo(m.group.position)
      const r = SITE_RADIUS * Math.max(1, Math.pow(d / 900, 0.72))
      m.disc.scale.set(r, 1, r)
      m.rim.scale.setScalar(r)
      if (m.pulse) {
        const p = (now / 2600 + m.phase) % 1
        m.pulse.scale.setScalar(r * (1 + 1.6 * p))
        m.pulse.material.opacity = 0.55 * (1 - p) * (1 - p)
      }
      const h = Math.max(12, d * 0.04) // the letter chip stays readable at any zoom (~35 px tall)
      m.chip.scale.set(h * (m.chip.userData.aspect as number), h, 1)
      m.chip.position.y = r * 0.35 + h * 0.8
    }
    // owl markers: from afar a flat red badge that grows gently with distance and draws through the buildings (find it at a
    // glance); close in, it crossfades into the 3D pin standing on the street (see exactly where). Hover swells it and sweeps
    // the rim yellow; a click hops. The coverage disc stays true to scale and breathes slowly.
    for (const m of this.nodes.values()) {
      const oldPinVisible = m.pin.visible
      const oldPinScaleX = m.pin.scale.x
      const oldPinScaleY = m.pin.scale.y
      const oldPinY = m.group.position.y
      const id = m.group.userData.nodeId as string
      const hovered = this.hoveredNode === id
      m.hoverT += ((hovered ? 1 : 0) - m.hoverT) * (1 - Math.exp(-dt * 12))
      m.sweepT = hovered ? Math.min(1, m.sweepT + dt / 0.55) : Math.max(0, m.sweepT - dt / 0.2)
      const bounce = THREE.MathUtils.clamp((now - m.bounceAt) / BOUNCE_MS, 0, 1)
      const hop = bounce < 1 ? Math.sin(bounce * Math.PI) * (1 - bounce * 0.5) : 0
      const selected = this.selectedNode === id ? 1.15 : 1
      const sel = selected * (1 + 0.3 * m.hoverT) // the flat badge swells 30% under the pointer
      const selPin = selected * (1 + 0.15 * m.hoverT) // the 3D pin only half that: it is already big up close
      const d = this.camera.position.distanceTo(m.group.position)
      const far = smoothstep(THREE.MathUtils.clamp((d - BADGE_NEAR) / (BADGE_FAR - BADGE_NEAR), 0, 1)) // 0 close .. 1 far
      const badgeR = BADGE_RADIUS * Math.max(1, Math.pow(d / 900, 0.72)) * sel
      m.badge.visible = far > 0.02
      m.badge.scale.set(badgeR, badgeR * (0.3 + 0.7 * far) * (1 + hop * 0.6), badgeR)
      m.badge.material.opacity = far
      const pinScale = selPin * Math.max(1, Math.pow(d / 900, 0.8)) // the pin grows a little with distance so the handover is seamless
      m.pin.visible = far < 0.98
      m.pin.scale.set(pinScale * (0.6 + 0.4 * (1 - far)), pinScale * (0.6 + 0.4 * (1 - far)) * (1 + hop * 0.25), pinScale * (0.6 + 0.4 * (1 - far)))
      for (const mat of m.pinMats) mat.opacity = (1 - far) * (mat === m.pinMats[1] ? 0.55 : mat === m.pinMats[2] ? 0.22 : mat === m.pinMats[3] ? 0.28 : 1)
      // the rim is an overlay while it belongs to the badge, and a thing on the ground once the pin has taken over
      m.ring.material.depthTest = far < 0.5
      const ringR = Math.max(badgeR * far, pinScale * 9 * (1 - far) + badgeR * far)
      m.ring.scale.setScalar(ringR)
      m.ring.material.uniforms.sweep.value = m.sweepT
      m.hit.scale.set(Math.max(badgeR * 1.6, 18), Math.max(30, pinScale * 34), Math.max(badgeR * 1.6, 18))
      m.group.position.y = 0.5 + hop * badgeR * 0.9
      if (oldPinVisible !== m.pin.visible || Math.abs(oldPinScaleX - m.pin.scale.x) > 0.0001 ||
          Math.abs(oldPinScaleY - m.pin.scale.y) > 0.0001 || Math.abs(oldPinY - m.group.position.y) > 0.0001) {
        this.renderer.shadowMap.needsUpdate = true
      }
      m.rings.forEach((ring, k) => {
        const p = (now / NODE_PULSE_MS + m.phase + k / 2) % 1
        ring.scale.setScalar(NODE_RANGE * (0.1 + 0.9 * p))
        ring.material.opacity = 0.32 * (1 - p) * (1 - p)
      })
      if (m.halo.visible) {
        // the selected owl's red edge ripples outward from the coverage line and fades, over and over
        const p = (now / NODE_RIPPLE_MS + m.phase) % 1
        m.halo.scale.setScalar(NODE_RANGE * (1 + 0.12 * p))
        m.halo.material.opacity = 0.8 * (1 - p) * (1 - 0.5 * p)
      }
    }
    // fog scales with the orbit distance so pulling back to the whole city does not fog it out
    const fog = this.scene.fog as THREE.Fog | null
    if (fog) {
      const s = Math.max(1, dist / 3500)
      fog.near = this.look.fog[0] * s
      fog.far = this.look.fog[1] * s
    }
    this.reportView(now, dist)
    const renderStart = this.perf ? performance.now() : 0
    this.renderer.render(this.scene, this.camera)
    if (this.perf) {
      const end = performance.now()
      const info = this.renderer.info
      this.perf.sample(end, end - frameStart, end - renderStart, info.render.calls, info.render.triangles,
        this.hexes.size, this.tiles.size, info.memory.geometries, info.memory.textures)
    }
    if (this.flight || this.keys.size > 0 || this.locator || hexAnimating || controlsChanged || this.nodes.size > 0 || this.spots.length > 0) {
      this.scheduleFrame()
    } else if (!this.raf) {
      this.perf?.idle()
    }
  }
}

// ---------------------------------------------------------------- helpers

/** Mean of a ring's points, local metres: good enough to say which cell a road piece is in. */
function ringCentre(ring: [number, number][]): [number, number] {
  let x = 0
  let y = 0
  for (const [px, py] of ring) {
    x += px
    y += py
  }
  return [x / ring.length, y / ring.length]
}

/** Camera position on the orbit sphere around `target` (polar from the up axis, azimuth around it). */
function orbitPosition(target: THREE.Vector3, distance: number, polar: number, azimuth: number): THREE.Vector3 {
  return new THREE.Vector3(
    target.x + distance * Math.sin(polar) * Math.sin(azimuth),
    target.y + distance * Math.cos(polar),
    target.z + distance * Math.sin(polar) * Math.cos(azimuth),
  )
}

/** Gradient sky dome, unlit, behind everything; runs through the same tone mapping as the scene. */
function makeSky(): THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial> {
  const material = new THREE.ShaderMaterial({
    uniforms: { zenith: { value: new THREE.Color(0x7ea3cc) }, horizon: { value: new THREE.Color(0xe3e9ec) } },
    vertexShader: `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 zenith;
      uniform vec3 horizon;
      varying vec3 vDir;
      void main() {
        float t = pow(clamp(vDir.y, 0.0, 1.0), 0.55);
        gl_FragColor = vec4(mix(horizon, zenith, t), 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
  })
  const sky = new THREE.Mesh(new THREE.SphereGeometry(70_000, 32, 16), material)
  sky.renderOrder = -100
  sky.frustumCulled = false
  return sky
}

function hashId(id: string): number {
  let h = 2166136261
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619)
  return ((h >>> 0) % 1000) / 1000
}

/** Every ring as a triangulated flat shape in shape space (x east, y north), merged into one geometry. */
function buildFlat(polys: Poly[]): THREE.BufferGeometry | null {
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

/** One low-poly canopy per tree, instanced: thousands of trees in one draw call. */
function buildTrees(trees: Tree[], material: THREE.Material): THREE.InstancedMesh {
  const geometry = new THREE.SphereGeometry(2.8, 7, 5)
  geometry.translate(0, 4.2, 0)
  const mesh = new THREE.InstancedMesh(geometry, material, trees.length)
  const m = new THREE.Matrix4()
  trees.forEach((t, i) => {
    m.makeTranslation(t.x, 0, -t.y)
    mesh.setMatrixAt(i, m)
  })
  mesh.instanceMatrix.needsUpdate = true
  mesh.computeBoundingSphere()
  mesh.castShadow = true
  return mesh
}

/** Glass-chip text for the area labels; the canvas hugs the chip so the sprite's size is the chip's size. */
function textTexture(text: string, ink: string): THREE.CanvasTexture {
  const font = '600 84px -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", system-ui, sans-serif'
  const probe = document.createElement('canvas').getContext('2d')!
  probe.font = font
  const tw = Math.ceil(probe.measureText(text).width + 120)
  const w = tw + 16
  const h = 256
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')!
  ctx.font = font
  const x0 = (w - tw) / 2
  const light = ink === '#16202b'
  ctx.fillStyle = light ? 'rgba(255,255,255,0.72)' : 'rgba(16,19,28,0.72)'
  ctx.beginPath()
  ctx.roundRect(x0, 48, tw, 160, 80)
  ctx.fill()
  ctx.strokeStyle = light ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.18)'
  ctx.lineWidth = 4
  ctx.stroke()
  ctx.fillStyle = ink
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, w / 2, 130)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/** The badge rim: pink, turning yellow clockwise from 12 o'clock as `sweep` goes 0..1. */
function sweepMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: { base: { value: new THREE.Color(NODE_PINK) }, hot: { value: new THREE.Color(NODE_YELLOW) }, sweep: { value: 0 }, opacity: { value: 0.96 } },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 base;
      uniform vec3 hot;
      uniform float sweep;
      uniform float opacity;
      varying vec2 vUv;
      void main() {
        vec2 p = vUv - 0.5;
        float a = mod(atan(p.x, p.y) + 6.2831853, 6.2831853) / 6.2831853; // 0 at 12 o'clock, clockwise
        gl_FragColor = vec4(a < sweep ? hot : base, opacity);
        #include <colorspace_fragment>
      }`,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    side: THREE.DoubleSide,
  })
}


/**
 * Extrude every footprint into one indexed BufferGeometry: roof cap + walls, no bottom cap.
 * Built in shape space (x east, y north, z up); the mesh is rotated -90deg about x afterwards.
 * Walls get UVs in facade tiles (u along the wall, v up) and go in material group 0; roofs in group 1.
 * `ranges` receives the vertex range of each building so its colour can be updated per mode.
 */
function buildExtrusions(buildings: Building[], ranges: BuildingRange[]): THREE.BufferGeometry {
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
  const [tileU, tileV] = FACADE_TILE_M
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
