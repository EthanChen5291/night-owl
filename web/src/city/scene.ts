import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { cellToBoundary, cellToLatLng, cellToParent, gridDisk, latLngToCell, polygonToCells } from 'h3-js'
import { colourFor, heightFor } from '../colours'
import type { Area, Building, Cell, CityLayers, HoverInfo, Mode, OwlNode, PlanNode, Poly, Preset, Spot, Tile, Tree, ViewInfo } from '../types'
import { makeProjector, type LatLon, type Projector } from './projection'
import { FACADE_TILE_M, facadeTextures } from './facade'
import { pointInRing, type AddressIndex } from './addresses'
import { BuildingOcclusionIndex } from './occlusion'
import { buildHexPrism } from './hexGeometry'
import { installBuildingTheme, installFieldTheme } from './themeMaterials'
import { buildFlat, tintBuildingGeometry, unpackGeometry, type BuildingRange, type TileGeometryReply, type TileGeometryRequest } from './tileGeometry'
import type { FlatLayersReply } from './flatLayers.worker'

// No React in here. App owns the data; Scene.tsx owns the lifecycle; this class owns three.js.
// Coordinates: local metres, x east, y north (from the projector); mapped to three.js x / -z.

export interface SceneCallbacks {
  onHover: (info: HoverInfo | null) => void
  onClick: (info: HoverInfo) => void
  onView: (view: ViewInfo) => void
}

interface HexEntry {
  mesh: THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial>
  targetHeight: number
  targetColour: THREE.Color
  flashUntil: number
}

interface TileMeshes {
  area: string | null
  occlusion: BuildingOcclusionIndex | null
  footprints: Building[]
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
  bounds: { minX: number; minY: number; maxX: number; maxY: number }
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
  t0: THREE.Vector3
  t1: THREE.Vector3
  radius0: number
  radius1: number
  polar0: number
  polar1: number
  azimuth0: number
  azimuthDelta: number
  start: number
  duration: number
}

const FLASH_MS = 1500
const MAX_PIXEL_RATIO = 1.5
const FIELD_FEATHER = [0, 0.18, 0.38, 0.6, 0.8, 0.92] // the colour field's alpha ring by ring in from a land border (Westchester, Nassau): it fades out over ~1 km instead of stopping on the city line. At the coast it runs at full strength to the shore and the land stencil cuts it there
const FIELD_ISLAND_MAX = 400 // land outside the borough outlines in pieces up to this many hexes (the Rockaways, Rikers, Randalls, the Jamaica Bay marshes) is still the city; bigger pieces are the neighbours
const FIELD_REACH = 30 // rings searched for the nearest coloured hex when an island has no coloured neighbour to inherit from (~5 km)
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
// Markers draw after the prisms; the far badge skips depth testing, while the close pin sits among buildings.
const MARKER_ORDER = 1
const HEX_PICK_DISTANCE = 1000 // closer than this, let streets and buildings receive the pointer
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
  /**
   * the citywide 2D colour field: every cell colour is pulled `mix` of the way to `neutral` (in the shader, so day/night
   * only touch uniforms) and blurred over `smooth` rings when the mesh is built, so the map stays calm
   */
  field: { neutral: number; mix: number; opacity: number; smooth: number }
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
    field: { neutral: 0xe6e4de, mix: 0.12, opacity: 1, smooth: 6 },
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
    field: { neutral: 0x171b26, mix: 0.2, opacity: 1, smooth: 6 },
    locator: { band: 0xfff0b0, edge: 0x1b202a },
    area: { fill: 0x9fc4ff, rim: 0xbfd8ff, ink: '#e6e8ef' },
  },
}

const smoothstep = (t: number) => t * t * (3 - 2 * t)

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
  private pendingHexes: Cell[] = []
  private pendingAreaHexes: string[] = []
  private pendingPriorityHexes = 0
  private hexBuildHandle: number | null = null
  private hexBuildKind: 'idle' | 'frame' | 'timeout' | null = null
  private visibleHexes: HexEntry[] = []
  private visibleHexMeshes: THREE.Object3D[] = []
  private hexGroup = new THREE.Group()
  private buildingTheme: ReturnType<typeof installBuildingTheme>
  private preset: Preset | null = null
  private planGroup = new THREE.Group()
  private cityLayerGroup = new THREE.Group() // citywide land / parks / water: the map under the colour field
  private field: THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial> | null = null // the citywide 2D colour map
  private fieldNeutral: THREE.IUniform<THREE.Color> = { value: new THREE.Color() }
  private fieldMix: THREE.IUniform<number> = { value: 0 }
  private fieldNeighbours: Map<string, string[]> | null = null // ring-1 neighbours of every hex the field covers, rebuilt when that set changes
  private landHexes: string[] = [] // every r9 hex whose centre is on land in the citywide bake (NYC and the land around it)
  private landHexHandle: number | null = null
  private landHexKind: 'idle' | 'timeout' | null = null
  private areaLayerGroup = new THREE.Group() // the active area's own ground: the only land drawn inside an area
  private cityLayerMeshes = new Map<FlatLayer, THREE.Mesh>()
  private cityLayerWorker: Worker | null = null
  private cityLayerRequestId = 0
  private pendingCityLayers: CityLayers | null = null
  private areaLayerMeshes = new Map<FlatLayer, THREE.Mesh>()
  private areaLayerWorker: Worker | null = null
  private areaLayerRequestId = 0
  private pendingAreaLayers: CityLayers | null = null
  private tileGroup = new THREE.Group()
  private tiles = new Map<string, TileMeshes>()
  private requestedTiles = new Map<string, Tile>()
  private tileWorker: Worker | null = null
  private tileRequestId = 0
  private tileInFlight: number | null = null
  private tileWorkerFailures = 0
  private tileRequests = new Map<string, { id: number; area: string | null; buildings: Building[]; roads: Poly[]; trees: Tree[]; tintRevision: number }>()
  private tintRevision = 0
  private nodeGroup = new THREE.Group()
  private nodes = new Map<string, NodeMarker>()
  private selectedNode: string | null = null
  private areaGroup = new THREE.Group()
  private areas = new Map<string, AreaMarker>()
  private activeArea: string | null = null
  private hoveredArea: string | null = null
  private tileAreas: Record<string, string | null | undefined> = {} // r7 tile -> area id, from tiles.json
  private cellArea = new Map<string, string | null>() // r9 cell -> area id (by the borough outline, else the tile's area), memoised
  private cellInBorough = new Map<string, boolean>() // r9 cell -> centre inside a borough outline (no tile fallback), for the field's extent
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
  private spots: Spot[] = []
  private lastHover: HoverInfo | null = null
  private callbacks: SceneCallbacks
  private index: AddressIndex | null = null
  private flight: Flight | null = null
  private flightAreas = new Set<string>()
  private renderedHexes = new WeakSet<HexEntry>()
  private pendingHexReveal: HexEntry[] = []
  private locator: Locator | null = null
  private raf = 0
  private urgentFrame = false
  private animationFrameDue = 0
  private updatingControls = false
  private viewReportTimer: ReturnType<typeof setTimeout> | null = null
  private disposed = false
  private canvas: HTMLCanvasElement

  constructor(canvas: HTMLCanvasElement, centre: LatLon, callbacks: SceneCallbacks) {
    this.loop = this.loop.bind(this)
    this.invalidate = this.invalidate.bind(this)
    this.handleVisibility = this.handleVisibility.bind(this)
    this.canvas = canvas
    this.callbacks = callbacks
    this.projector = makeProjector(centre)
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, stencil: true, powerPreference: 'high-performance' }) // stencil: the land clips the colour field
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
    this.controls.addEventListener('change', this.handleControlsChange)
    this.controls.target.set(0, 0, 0)
    this.camera.position.copy(orbitPosition(this.controls.target, CITY_DISTANCE, CITY_POLAR, 0.35))

    this.ground = new THREE.Mesh(
      new THREE.PlaneGeometry(160_000, 160_000),
      new THREE.MeshStandardMaterial({ color: LOOKS.day.layers.ground, roughness: 0.9, metalness: 0 }),
    )
    this.ground.rotation.x = -Math.PI / 2
    this.ground.position.y = -3
    this.ground.receiveShadow = true
    this.scene.add(this.ground)

    this.sky = makeSky()
    this.scene.add(this.sky)

    this.ambient = new THREE.AmbientLight(0xffffff, 0.15)
    this.hemi = new THREE.HemisphereLight(0x3a4a7a, 0x0a0a10, 0.5)
    // sun from the south-west so the faces the opening camera sees are lit; it follows the camera target
    this.key = new THREE.DirectionalLight(0xffb070, 1.6)
    this.key.position.set(-3200, 4600, 2800)
    this.key.castShadow = true
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
    this.buildingTheme = installBuildingTheme([this.wallMaterial, this.roofMaterial])
    this.setPreset('day')

    this.interruptFlight = this.interruptFlight.bind(this)
    canvas.addEventListener('pointerdown', this.interruptFlight, true)
    canvas.addEventListener('wheel', this.interruptFlight, { capture: true, passive: true })
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
    this.invalidate()
  }

  // ---------------------------------------------------------------- public API

  private scheduleFrame() {
    if (this.disposed || document.hidden || this.raf) return
    this.raf = requestAnimationFrame(this.loop)
  }

  private handleControlsChange = () => {
    // Damping and programmed flights already schedule their next frame.
    if (!this.updatingControls) this.invalidate()
  }

  private invalidate() {
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

  /** Build or recolour the original raised hexagons from the contract data. */
  setCells(cells: Cell[], mode: Mode) {
    this.tintRevision++
    this.mode = mode
    const seen = new Set<string>()
    for (const cell of cells) {
      this.cells.set(cell.h3, cell)
      seen.add(cell.h3)
      const entry = this.hexes.get(cell.h3)
      if (!entry) continue
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
    for (const h3 of this.cells.keys()) if (!seen.has(h3)) this.cells.delete(h3)
    this.pendingHexes = cells.filter((cell) => !this.hexes.has(cell.h3))
    this.prioritizePendingHexes()
    this.scheduleHexBuild()
    this.applyAreaVisibility()
    this.retintBuildings()
    this.fieldNeighbours = null
    this.rebuildField()
    this.invalidate()
  }

  setMode(mode: Mode) {
    if (mode === this.mode) return
    this.mode = mode
    this.tintRevision++
    for (const [h3, entry] of this.hexes) {
      const cell = this.cells.get(h3)
      if (!cell) continue
      entry.targetHeight = heightFor(mode, cell)
      entry.targetColour.set(colourFor(mode, cell))
    }
    this.retintBuildings()
    this.rebuildField()
    this.invalidate()
  }

  setPreset(preset: Preset) {
    if (this.preset === preset) return
    this.preset = preset
    const L = LOOKS[preset]
    this.look = L
    if (this.locator) {
      this.locator.band.material.color.set(L.locator.band)
      this.locator.edge.material.color.set(L.locator.edge)
    }
    if (this.field) {
      this.fieldNeutral.value.set(L.field.neutral)
      this.fieldMix.value = L.field.mix
      this.field.material.opacity = L.field.opacity
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
    this.key.shadow.intensity = L.sun.shadows ? 1 : 0
    this.buildingTheme.setNight(preset === 'night')
    this.renderer.shadowMap.needsUpdate = true
    this.renderer.toneMappingExposure = L.exposure
    this.ground.material.color.set(L.layers.ground)
    for (const [name, mesh] of this.cityLayerMeshes) (mesh.material as THREE.MeshBasicMaterial).color.set(L.layers[name]).multiplyScalar(preset === 'night' ? 2 : 1)
    for (const [name, mesh] of this.areaLayerMeshes) (mesh.material as THREE.MeshStandardMaterial).color.set(L.layers[name])
    this.roadMaterial.color.set(L.layers.roads)
    this.treeMaterial.color.set(L.layers.trees)
    this.wallMaterial.emissiveIntensity = L.windows
    this.wallMaterial.emissive.set(L.windowColour)
    for (const [h3, entry] of this.hexes) entry.mesh.material.opacity = h3 === this.hovered ? Math.min(1, L.hexOpacity + 0.15) : L.hexOpacity
    for (const site of this.sites) {
      site.chip.material.map?.dispose()
      site.chip.material.map = textTexture(site.chip.userData.text as string, L.area.ink)
    }
    for (const [id, a] of this.areas) {
      a.fill.material.color.set(L.area.fill)
      a.rim.material.color.set(L.area.rim)
      a.label.material.map?.dispose()
      const tex = textTexture((a.label.userData.name as string) ?? id, L.area.ink)
      a.label.material.map = tex
      a.label.userData.aspect = tex.image.width / tex.image.height
    }
    this.invalidate()
  }

  setPlan(nodes: PlanNode[]) {
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

  /** Same family as the owl badge: a squat translucent disc with a rim. */
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
    chip.userData = { text, aspect: (chip.material.map as THREE.CanvasTexture).image.width / (chip.material.map as THREE.CanvasTexture).image.height }
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
    edge.renderOrder = MARKER_ORDER + 2 // above map fills and markers, never hidden by a building
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
    // Keep the shadow shader variant stable, but skip its map pass at night.
    if (!this.look.sun.shadows && this.key.shadow.map) this.renderer.shadowMap.needsUpdate = false
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
    this.fly(target, p1)
  }

  /** Try nearby viewing angles until the camera-to-pin line clears the loaded buildings. */
  private clearApproach(target: THREE.Vector3, distance: number, polar: number, azimuth: number): { polar: number; azimuth: number } {
    const aim = target.clone().setY(12)
    const clear = (p: number, az: number) => {
      const pos = orbitPosition(target, distance, p, az)
      const from = { east: pos.x, north: -pos.z, height: pos.y }
      const to = { east: aim.x, north: -aim.z, height: aim.y }
      for (const tile of this.tiles.values()) {
        const sphere = tile.buildings?.geometry.boundingSphere
        if (!sphere || Math.hypot(sphere.center.x - target.x, sphere.center.y + target.z) > sphere.radius + distance + 20) continue
        tile.occlusion ??= new BuildingOcclusionIndex(tile.footprints)
        if (tile.occlusion.blocks(from, to)) return false
      }
      return true
    }
    for (const p of [polar, 0.5, 0.35]) {
      for (let k = 0; k < 12; k++) {
        const az = azimuth + (k % 2 ? 1 : -1) * Math.ceil(k / 2) * (Math.PI / 6)
        if (clear(p, az)) return { polar: p, azimuth: az }
      }
    }
    return { polar: 0.25, azimuth }
  }

  /** Citywide flat layers (land, parks, water). */
  setCityLayers(layers: CityLayers) {
    this.pendingCityLayers = layers
    this.scheduleLandHexes(layers.land ?? [])
    if (!this.cityLayerWorker) {
      try {
        this.cityLayerWorker = new Worker(new URL('./flatLayers.worker.ts', import.meta.url), { type: 'module' })
        this.cityLayerWorker.onmessage = (event: MessageEvent<FlatLayersReply>) => {
          if (this.disposed || event.data.id !== this.cityLayerRequestId) return
          this.pendingCityLayers = null
          this.replaceLayers(this.cityLayerGroup, this.cityLayerMeshes, (name) => {
            const packed = event.data.layers[name]
            return packed ? unpackGeometry(packed) : null
          })
          this.invalidate()
        }
        this.cityLayerWorker.onerror = () => {
          this.cityLayerWorker?.terminate()
          this.cityLayerWorker = null
          const pending = this.pendingCityLayers
          this.pendingCityLayers = null
          if (pending && !this.disposed) {
            this.buildLayers(this.cityLayerGroup, this.cityLayerMeshes, pending)
            this.invalidate()
          }
        }
      } catch {
        this.buildLayers(this.cityLayerGroup, this.cityLayerMeshes, layers)
        this.pendingCityLayers = null
        this.invalidate()
        return
      }
    }
    this.cityLayerWorker.postMessage({ id: ++this.cityLayerRequestId, layers })
  }

  /** The active area's own ground, the only land drawn while you are in it (null clears it). */
  setAreaLayers(layers: CityLayers | null) {
    if (!layers) {
      this.areaLayerRequestId++
      this.areaLayerWorker?.terminate()
      this.areaLayerWorker = null
      this.pendingAreaLayers = null
      // Retain the last detailed ground during travel; the coast always remains underneath.
      if (!this.flight && !this.activeArea) this.buildLayers(this.areaLayerGroup, this.areaLayerMeshes, { land: null, parks: null, water: null })
      this.updateBaseMapVisibility()
      this.invalidate()
      return
    }
    this.pendingAreaLayers = layers
    if (!this.areaLayerWorker) {
      try {
        this.areaLayerWorker = new Worker(new URL('./flatLayers.worker.ts', import.meta.url), { type: 'module' })
        this.areaLayerWorker.onmessage = (event: MessageEvent<FlatLayersReply>) => {
          if (this.disposed || event.data.id !== this.areaLayerRequestId) return
          this.pendingAreaLayers = null
          this.replaceLayers(this.areaLayerGroup, this.areaLayerMeshes, (name) => {
            const packed = event.data.layers[name]
            return packed ? unpackGeometry(packed) : null
          })
          this.updateBaseMapVisibility()
          this.invalidate()
        }
        this.areaLayerWorker.onerror = () => {
          this.areaLayerWorker?.terminate()
          this.areaLayerWorker = null
          const pending = this.pendingAreaLayers
          this.pendingAreaLayers = null
          if (pending && !this.disposed) {
            this.buildLayers(this.areaLayerGroup, this.areaLayerMeshes, pending)
            this.updateBaseMapVisibility()
            this.invalidate()
          }
        }
      } catch {
        this.buildLayers(this.areaLayerGroup, this.areaLayerMeshes, layers)
        this.pendingAreaLayers = null
        this.updateBaseMapVisibility()
        this.invalidate()
        return
      }
    }
    this.areaLayerWorker.postMessage({ id: ++this.areaLayerRequestId, layers })
  }

  private buildLayers(group: THREE.Group, meshes: Map<FlatLayer, THREE.Mesh>, layers: CityLayers) {
    this.replaceLayers(group, meshes, (name) => {
      const polys = layers[name]
      return polys?.length ? buildFlat(polys) : null
    })
  }

  private replaceLayers(group: THREE.Group, meshes: Map<FlatLayer, THREE.Mesh>, geometryFor: (name: FlatLayer) => THREE.BufferGeometry | null) {
    for (const mesh of meshes.values()) {
      group.remove(mesh)
      mesh.geometry.dispose()
      ;(mesh.material as THREE.Material).dispose()
    }
    meshes.clear()
    const L = this.look
    FLAT_LAYERS.forEach((name, i) => {
      const geometry = geometryFor(name)
      if (!geometry) return
      const city = group === this.cityLayerGroup
      const common = {
        color: new THREE.Color(L.layers[name]).multiplyScalar(city && this.preset === 'night' ? 2 : 1),
        polygonOffset: true, // stack the coplanar layers without z-fighting
        polygonOffsetFactor: -(i + 1) * 2,
        polygonOffsetUnits: -(i + 1) * 2,
      }
      // citywide, the land marks the stencil so the colour field is clipped to the coastline
      const material = city
        ? new THREE.MeshBasicMaterial({ ...common, toneMapped: false, ...(name === 'land' ? { stencilWrite: true, stencilRef: 1, stencilFunc: THREE.AlwaysStencilFunc, stencilZPass: THREE.ReplaceStencilOp } : {}) })
        : new THREE.MeshStandardMaterial({ ...common, roughness: name === 'water' ? 0.35 : 1, metalness: 0 })
      const mesh = new THREE.Mesh(geometry, material)
      mesh.rotation.x = -Math.PI / 2
      mesh.position.y = city ? -2 : -0.4
      mesh.renderOrder = -20 + i
      mesh.receiveShadow = !city
      meshes.set(name, mesh)
      group.add(mesh)
    })
    this.syncCityLayerVisibility()
  }

  /**
   * Citywide, the colour field is the map: while it is showing, the parks and inner water of the citywide bake stay hidden
   * (they would speckle the field, and the water polygons stop at the bake's tile edges); the ground plane is the sea.
   */
  private syncCityLayerVisibility() {
    const fieldShowing = !!this.field?.visible
    for (const [name, mesh] of this.cityLayerMeshes ?? []) if (name !== 'land') mesh.visible = !fieldShowing
  }

  /** Build incoming tile geometry in a worker; discard replies for tiles that left the view. */
  setTiles(tiles: Map<string, Tile>) {
    if (this.disposed) return
    this.requestedTiles = tiles
    let changed = false
    for (const [id, t] of this.tiles) {
      if (this.flight && t.area && this.flightAreas.has(t.area)) continue
      if (tiles.has(id) && t.area === this.activeArea) continue
      changed = true
      this.tileGroup.remove(t.group)
      t.buildings?.geometry.dispose()
      t.roads?.geometry.dispose()
      t.trees?.geometry.dispose()
      this.tiles.delete(id)
    }
    for (const [id, request] of this.tileRequests) {
      if (!tiles.has(id) || request.area !== this.activeArea) this.tileRequests.delete(id)
    }
    if (this.tileInFlight !== null && ![...this.tileRequests.values()].some((request) => request.id === this.tileInFlight)) {
      this.tileWorker?.terminate()
      this.tileWorker = null
      this.tileInFlight = null
    }
    for (const [id, tile] of tiles) {
      if (this.tiles.has(id) || this.tileRequests.has(id)) continue
      const mine = (h3: string) => !this.activeArea || this.areaOfCell(h3) === this.activeArea
      const buildings = tile.buildings.filter((b) => mine(b.h3))
      const roads = tile.roads.filter((r) => {
        const { lat, lon } = this.projector.latLon(...ringCentre(r.ring))
        return mine(latLngToCell(lat, lon, 9))
      })
      const trees = tile.trees.filter((t) => mine(t.h3))
      this.tileRequests.set(id, { id: ++this.tileRequestId, area: this.activeArea, buildings, roads, trees, tintRevision: this.tintRevision })
    }
    this.startNextTile()
    if (changed) {
      this.renderer.shadowMap.needsUpdate = true
      this.invalidate()
    }
  }

  private startNextTile() {
    if (this.disposed || this.tileInFlight !== null || this.tileWorkerFailures >= 2) return
    const next = this.tileRequests.entries().next().value
    if (!next) return
    if (!this.tileWorker) {
      this.tileWorker = new Worker(new URL('./tileGeometry.worker.ts', import.meta.url), { type: 'module' })
      this.tileWorker.onmessage = (event: MessageEvent<TileGeometryReply>) => this.receiveTile(event.data)
      this.tileWorker.onerror = () => {
        this.tileWorker?.terminate()
        this.tileWorker = null
        this.tileInFlight = null
        if (++this.tileWorkerFailures < 2) this.startNextTile()
        else {
          this.tileRequests.clear()
          console.error('Map tile worker failed to load')
        }
      }
    }
    const [tileId, tile] = next
    this.tileInFlight = tile.id
    const colours: Record<string, string> = {}
    for (const building of tile.buildings) {
      const cell = this.cells.get(building.h3)
      if (cell && !(building.h3 in colours)) colours[building.h3] = colourFor(this.mode, cell)
    }
    tile.tintRevision = this.tintRevision
    const request: TileGeometryRequest = { id: tile.id, tileId, buildings: tile.buildings, roads: tile.roads, facadeTileM: FACADE_TILE_M,
      tint: { colours, day: LOOKS.day, night: LOOKS.night } }
    this.tileWorker.postMessage(request)
  }

  private receiveTile(data: TileGeometryReply) {
    if (this.disposed || data.id !== this.tileInFlight) return
    this.tileInFlight = null
    const request = this.tileRequests.get(data.tileId)
    if (!request || request.id !== data.id || request.area !== this.activeArea) {
      if (request?.id === data.id) this.tileRequests.delete(data.tileId)
      this.startNextTile()
      return
    }
    this.tileRequests.delete(data.tileId)
    this.startNextTile()
    if (!data.ok) {
      console.error('Unable to build map tile', data.tileId, data.error)
      return
    }
    const group = new THREE.Group()
    let buildings: THREE.Mesh | null = null
    if (data.buildings) {
      buildings = new THREE.Mesh(unpackGeometry(data.buildings), [this.wallMaterial, this.roofMaterial])
      buildings.rotation.x = -Math.PI / 2
      buildings.castShadow = true
      buildings.receiveShadow = true
      group.add(buildings)
    }
    let roads: THREE.Mesh | null = null
    if (data.roads) {
      roads = new THREE.Mesh(unpackGeometry(data.roads), this.roadMaterial)
      roads.rotation.x = -Math.PI / 2
      roads.position.y = -0.4
      roads.renderOrder = -18
      roads.receiveShadow = true
      group.add(roads)
    }
    const trees = request.trees.length ? buildTrees(request.trees, this.treeMaterial) : null
    if (trees) group.add(trees)
    const entry = { group, buildings, ranges: data.ranges, roads, trees,
      area: request.area, occlusion: null, footprints: request.buildings }
    this.tileGroup.add(group)
    this.tiles.set(data.tileId, entry)
    if (request.tintRevision !== this.tintRevision) this.retintTile(entry)
    this.renderer.shadowMap.needsUpdate = true
    this.invalidate()
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
      const xs = a.outline.map(([x]) => x)
      const ys = a.outline.map(([, y]) => y)
      this.areas.set(a.id, { fill, rim, label, centre: new THREE.Vector3(cx, 0, -cy), outline: a.outline,
        bounds: { minX: Math.min(...xs), minY: Math.min(...ys), maxX: Math.max(...xs), maxY: Math.max(...ys) } })
    }
    this.cellArea.clear()
    this.cellInBorough.clear()
    this.rebuildField()
    this.applyAreaVisibility()
    this.invalidate()
  }

  /** Which area each r7 tile belongs to (tiles.json). */
  setTileAreas(tileAreas: Record<string, string | null | undefined>) {
    this.tileAreas = tileAreas
    this.cellArea.clear()
    this.prioritizePendingHexes()
    this.applyAreaVisibility()
    this.invalidate()
  }

  /** Fly into an area (or out to the city with null). `immediate` snaps, for the first frame. */
  setActiveArea(id: string | null, immediate = false) {
    if (!immediate && id === this.activeArea && this.flight &&
        this.flight.t1.equals(id ? this.areas.get(id)?.centre ?? new THREE.Vector3() : new THREE.Vector3())) return
    if (immediate) this.flightAreas.clear()
    else if (this.activeArea) this.flightAreas.add(this.activeArea)
    this.activeArea = id
    this.prioritizePendingHexes()
    this.keysEnabled = id !== null
    this.keys.clear()
    this.applyAreaVisibility()
    const a = id ? this.areas.get(id) : null
    const target = a ? a.centre.clone() : new THREE.Vector3(0, 0, 0)
    const current = this.camera.position.clone().sub(this.controls.target)
    const azimuth = Math.atan2(current.x, current.z)
    const distance = a ? Math.min(current.length(), AREA_DISTANCE) : CITY_DISTANCE
    const p1 = orbitPosition(target, distance, a ? 0.95 : CITY_POLAR, azimuth)
    if (immediate) {
      this.flight = null
      this.controls.enabled = true
      this.controls.target.copy(target)
      this.camera.position.copy(p1)
      this.controls.update()
      this.renderer.shadowMap.needsUpdate = true
      this.invalidate()
      return
    }
    this.fly(target, p1)
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

  dispose() {
    this.disposed = true
    this.areaLayerWorker?.terminate()
    this.areaLayerWorker = null
    this.pendingAreaLayers = null
    this.cityLayerWorker?.terminate()
    this.cityLayerWorker = null
    this.pendingCityLayers = null
    this.cancelLandHexes()
    this.cancelHexBuild()
    this.tileWorker?.terminate()
    this.tileWorker = null
    this.tileInFlight = null
    this.tileRequests.clear()
    cancelAnimationFrame(this.raf)
    if (this.viewReportTimer !== null) clearTimeout(this.viewReportTimer)
    this.canvas.removeEventListener('pointerdown', this.interruptFlight, true)
    this.canvas.removeEventListener('wheel', this.interruptFlight, true)
    this.canvas.removeEventListener('pointermove', this.handlePointerMove)
    this.canvas.removeEventListener('pointerleave', this.handlePointerLeave)
    this.canvas.removeEventListener('pointerdown', this.handlePointerDown)
    this.canvas.removeEventListener('click', this.handleClick)
    window.removeEventListener('keydown', this.handleKeyDown)
    window.removeEventListener('keyup', this.handleKeyUp)
    window.removeEventListener('blur', this.handleBlur)
    window.removeEventListener('resize', this.resize)
    document.removeEventListener('visibilitychange', this.handleVisibility)
    this.controls.removeEventListener('change', this.handleControlsChange)
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

  /** Put the selected borough's pending cells at the end of the stack, where construction starts. */
  private prioritizePendingHexes() {
    this.pendingPriorityHexes = 0
    if (!this.activeArea || this.pendingHexes.length === 0) {
      this.cancelHexBuild()
      return
    }
    const other: Cell[] = []
    const selected: Cell[] = []
    for (const cell of this.pendingHexes) {
      if (this.tileAreas[cellToParent(cell.h3, 7)] === this.activeArea) selected.push(cell)
      else other.push(cell)
    }
    this.pendingHexes = [...other, ...selected]
    this.pendingPriorityHexes = selected.length
    this.cancelHexBuild()
  }

  private cancelHexBuild() {
    if (this.hexBuildHandle == null) return
    if (this.hexBuildKind === 'frame') cancelAnimationFrame(this.hexBuildHandle)
    else if (this.hexBuildKind === 'idle' && typeof window.cancelIdleCallback === 'function') window.cancelIdleCallback(this.hexBuildHandle)
    else clearTimeout(this.hexBuildHandle)
    this.hexBuildHandle = null
    this.hexBuildKind = null
  }

  /** Build visible borough prisms across short frames; finish offscreen cells when the browser is idle. */
  private scheduleHexBuild() {
    if (this.disposed || this.hexBuildHandle !== null || (this.pendingHexes.length === 0 && this.pendingAreaHexes.length === 0)) return
    const build = (deadline?: IdleDeadline) => {
      this.hexBuildHandle = null
      this.hexBuildKind = null
      const start = performance.now()
      let built = 0
      while (this.pendingHexes.length && (this.pendingPriorityHexes > 0 || this.pendingAreaHexes.length === 0) && performance.now() - start < 4 && (!deadline || deadline.didTimeout || deadline.timeRemaining() > 1)) {
        const h3 = this.pendingHexes.pop()!.h3
        if (this.pendingPriorityHexes > 0) this.pendingPriorityHexes--
        const cell = this.cells.get(h3)
        if (this.hexes.has(h3) || !cell) continue
        this.areaOfCell(h3)
        const entry = this.makeHex(cell)
        this.hexes.set(h3, entry)
        this.hexGroup.add(entry.mesh)
        if (entry.mesh.visible && this.activeArea) {
          this.visibleHexes.push(entry)
          this.visibleHexMeshes.push(entry.mesh)
        }
        built++
      }
      while (this.pendingAreaHexes.length && performance.now() - start < 4 && (!deadline || deadline.didTimeout || deadline.timeRemaining() > 1)) {
        const h3 = this.pendingAreaHexes.pop()!
        const entry = this.hexes.get(h3)
        if (!entry) continue
        const area = this.areaOfCell(h3)
        if (this.activeArea && (area === null || area === this.activeArea || this.flightAreas.has(area))) {
          entry.mesh.visible = true
          this.visibleHexes.push(entry)
          this.visibleHexMeshes.push(entry.mesh)
        }
        built++
      }
      if (built) this.invalidate()
      this.scheduleHexBuild()
    }
    if (this.activeArea && (this.pendingPriorityHexes > 0 || this.pendingAreaHexes.length > 0)) {
      this.hexBuildKind = 'frame'
      this.hexBuildHandle = requestAnimationFrame(() => build())
    } else if (typeof window.requestIdleCallback === 'function') {
      this.hexBuildKind = 'idle'
      this.hexBuildHandle = window.requestIdleCallback(build, { timeout: 1000 })
    } else {
      this.hexBuildKind = 'timeout'
      this.hexBuildHandle = setTimeout(() => build(), 0) as unknown as number
    }
  }

  /**
   * Citywide: coast, borough fills, rims and name tags.
   * Inside an area: detailed ground, tiles and coloured prisms; the other boroughs keep their name tags.
   */
  private applyAreaVisibility() {
    this.pendingHexReveal = []
    const inArea = !!this.activeArea || this.flightAreas.size > 0
    for (const [id, a] of this.areas) {
      a.fill.visible = !inArea
      a.rim.visible = !inArea
      a.label.visible = id !== this.activeArea
    }
    this.areaLayerGroup.visible = inArea
    this.hexGroup.visible = inArea
    if (this.field) this.field.visible = !inArea
    this.syncCityLayerVisibility()
    this.visibleHexes = []
    this.visibleHexMeshes = []
    this.pendingAreaHexes = []
    if (inArea) for (const [h3, entry] of this.hexes) {
      const area = this.cellArea.get(h3)
      entry.mesh.visible = area !== undefined && (area === null || area === this.activeArea || this.flightAreas.has(area))
      if (entry.mesh.visible) {
        this.visibleHexes.push(entry)
        this.visibleHexMeshes.push(entry.mesh)
      } else if (area === undefined) this.pendingAreaHexes.push(h3)
    }
    else if (!inArea) for (const h3 of this.hexes.keys()) if (!this.cellArea.has(h3)) this.pendingAreaHexes.push(h3)
    this.queueHexDisplay()
    this.updateBaseMapVisibility()
    this.scheduleHexBuild()
    this.invalidate()
  }

  /** Work out which r9 hexes the colour field should cover, off the critical path: the land polygons are large. */
  private scheduleLandHexes(land: Poly[]) {
    this.cancelLandHexes()
    const run = () => {
      this.landHexHandle = null
      this.landHexKind = null
      if (this.disposed) return
      this.landHexes = this.hexesOverLand(land)
      this.fieldNeighbours = null
      this.rebuildField()
      this.invalidate()
    }
    if (typeof window.requestIdleCallback === 'function') {
      this.landHexKind = 'idle'
      this.landHexHandle = window.requestIdleCallback(run, { timeout: 1500 })
    } else {
      this.landHexKind = 'timeout'
      this.landHexHandle = setTimeout(run, 0) as unknown as number
    }
  }

  private cancelLandHexes() {
    if (this.landHexHandle == null) return
    if (this.landHexKind === 'idle') window.cancelIdleCallback(this.landHexHandle)
    else clearTimeout(this.landHexHandle)
    this.landHexHandle = null
    this.landHexKind = null
  }

  /** Every r9 hex whose centre is on land in the citywide bake. */
  private hexesOverLand(land: Poly[]): string[] {
    const set = new Set<string>()
    for (const poly of land) {
      if (poly.ring.length < 3) continue
      const loop = poly.ring.map(([x, y]) => {
        const { lat, lon } = this.projector.latLon(x, y)
        return [lat, lon] as [number, number]
      })
      const cells = polygonToCells([loop], 9)
      for (const h of cells) set.add(h)
      if (cells.length === 0) {
        // an islet smaller than a hex has no hex centre inside it: give it the hex under its centroid so it is still coloured
        const lat = loop.reduce((sum, [la]) => sum + la, 0) / loop.length
        const lon = loop.reduce((sum, [, lo]) => sum + lo, 0) / loop.length
        set.add(latLngToCell(lat, lon, 9))
      }
    }
    return [...set]
  }

  /**
   * The citywide 2D colour map: one flat triangle fan per r9 hex over every land hex inside the five boroughs, colours
   * averaged at shared corners and blurred over the neighbouring rings so it reads as a soft gradient rather than a
   * honeycomb. Hexes with no cell (parks, yards) take the mean of their coloured neighbours. The field overshoots its
   * edge by one ring: at the coast that ring is cut by the land stencil, so the colour runs to the shoreline; where land
   * continues past the city line the ring is transparent and the rings inside it feather out. Colours are stored unmixed
   * and the look's neutral mix is applied in the shader, so day/night changes touch uniforms, not geometry. Needs the
   * land hexes, the borough outlines and the cells.
   */
  private rebuildField() {
    if (this.field) {
      this.scene.remove(this.field)
      this.field.geometry.dispose()
      this.field.material.dispose()
      this.field = null
    }
    const L = this.look
    if (!L.field || !this.landHexes?.length || !this.cells?.size || !this.areas?.size) {
      this.syncCityLayerVisibility()
      return
    }
    // 1. the hexes the field covers: land inside a borough plus every cell (the core), then one ring past that edge; with
    //    ring-1 neighbours within the set (cached until the set changes)
    const land = new Set(this.landHexes)
    const core = new Set<string>()
    for (const h of land) if (this.insideBorough(h)) core.add(h)
    for (const h3 of this.cells.keys()) core.add(h3)
    // land outside the outlines comes in pieces: small ones are the city's own islands and airports, so they join the core;
    // the large ones (Nassau past Far Rockaway) stay outside and get the feather
    const outside = new Set([...land].filter((h) => !core.has(h)))
    const seen = new Set<string>()
    for (const start of outside) {
      if (seen.has(start)) continue
      const piece = [start]
      seen.add(start)
      for (let i = 0; i < piece.length; i++) for (const nb of gridDisk(piece[i], 1)) if (outside.has(nb) && !seen.has(nb)) {
        seen.add(nb)
        piece.push(nb)
      }
      if (piece.length <= FIELD_ISLAND_MAX) for (const h of piece) core.add(h)
    }
    const hexes = new Set(core)
    for (const h of core) for (const n of gridDisk(h, 1)) hexes.add(n)
    let neighbours = this.fieldNeighbours
    if (!neighbours || neighbours.size !== hexes.size) {
      neighbours = new Map()
      for (const h of hexes) neighbours.set(h, gridDisk(h, 1).filter((n) => n !== h && hexes.has(n)))
      this.fieldNeighbours = neighbours
    }
    const colours = new Map<string, THREE.Color>()
    for (const [h3, cell] of this.cells) colours.set(h3, new THREE.Color(colourFor(this.mode, cell)))
    // 2. hexes with no cell take the mean of their coloured neighbours, ring by ring outwards, so nothing on land is left grey
    let pending = [...hexes].filter((h) => !colours.has(h))
    while (pending.length) {
      const next: string[] = []
      const found = new Map<string, THREE.Color>()
      for (const h of pending) {
        const c = new THREE.Color(0, 0, 0)
        let n = 0
        for (const nb of neighbours.get(h) ?? []) {
          const cc = colours.get(nb)
          if (cc) {
            c.add(cc)
            n++
          }
        }
        if (n) found.set(h, c.multiplyScalar(1 / n))
        else next.push(h)
      }
      if (found.size === 0) {
        // islands: nothing coloured touches them, so each takes the mean of the nearest coloured hexes across the water
        for (const h of pending) {
          for (let k = 2; k <= FIELD_REACH; k++) {
            const near = gridDisk(h, k).filter((n) => colours.has(n))
            if (near.length === 0) continue
            const c = new THREE.Color(0, 0, 0)
            for (const n of near) c.add(colours.get(n)!)
            colours.set(h, c.multiplyScalar(1 / near.length))
            break
          }
        }
        break
      }
      for (const [h, c] of found) colours.set(h, c)
      pending = next
    }
    // 3. blur: each hex takes the mean of itself and its ring, `smooth` times
    let current = colours
    for (let pass = 0; pass < L.field.smooth; pass++) {
      const blurred = new Map<string, THREE.Color>()
      for (const [h, own] of current) {
        const c = own.clone()
        let n = 1
        for (const nb of neighbours.get(h) ?? []) {
          const cc = current.get(nb)
          if (cc) {
            c.add(cc)
            n++
          }
        }
        blurred.set(h, c.multiplyScalar(1 / n))
      }
      current = blurred
    }
    // 4. edges: the overshoot ring is transparent. Off land it only exists for the stencil to cut, so the shore hexes inside
    //    it keep full strength; on land (past the city line) it seeds a feather that climbs over the next rings in
    const alpha = new Map<string, number>()
    let frontier: string[] = []
    for (const h of current.keys()) {
      if (core.has(h)) continue
      alpha.set(h, FIELD_FEATHER[0])
      if (land.has(h)) frontier.push(h)
    }
    for (let ring = 1; ring < FIELD_FEATHER.length; ring++) {
      const next: string[] = []
      for (const h of frontier) for (const nb of neighbours.get(h) ?? []) if (current.has(nb) && !alpha.has(nb)) {
        alpha.set(nb, FIELD_FEATHER[ring])
        next.push(nb)
      }
      frontier = next
    }
    // 5. one fan per hex, corner colours and alpha averaged across the hexes that share the corner
    const cornerKey = (lat: number, lon: number) => `${lat.toFixed(6)},${lon.toFixed(6)}`
    const corners = new Map<string, { r: number; g: number; b: number; a: number; n: number }>()
    const rings: { h3: string; ring: [number, number][]; colour: THREE.Color; a: number }[] = []
    let nVerts = 0
    let nIdx = 0
    for (const [h3, colour] of current) {
      const ring = cellToBoundary(h3)
      const a = alpha.get(h3) ?? 1
      rings.push({ h3, ring, colour, a })
      for (const [lat, lon] of ring) {
        const k = cornerKey(lat, lon)
        const c = corners.get(k) ?? { r: 0, g: 0, b: 0, a: 0, n: 0 }
        c.r += colour.r
        c.g += colour.g
        c.b += colour.b
        c.a += a
        c.n++
        corners.set(k, c)
      }
      nVerts += ring.length + 1
      nIdx += ring.length * 3
    }
    const pos = new Float32Array(nVerts * 3)
    const col = new Float32Array(nVerts * 4) // rgba: three.js reads vertex alpha from a 4-wide colour attribute
    const idx = new Uint32Array(nIdx)
    let v = 0
    let k = 0
    for (const { h3, ring, colour, a } of rings) {
      const [cx, cy] = this.projector.xy(...cellToLatLng(h3))
      const centre = v
      pos.set([cx, 0, -cy], v * 3)
      col.set([colour.r, colour.g, colour.b, a], v * 4)
      v++
      ring.forEach(([lat, lon], i) => {
        const [x, y] = this.projector.xy(lat, lon)
        const c = corners.get(cornerKey(lat, lon))!
        pos.set([x, 0, -y], v * 3)
        col.set([c.r / c.n, c.g / c.n, c.b / c.n, c.a / c.n], v * 4)
        idx[k++] = centre
        idx[k++] = centre + 1 + i
        idx[k++] = centre + 1 + ((i + 1) % ring.length)
        v++
      })
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    g.setAttribute('color', new THREE.BufferAttribute(col, 4))
    g.setIndex(new THREE.BufferAttribute(idx, 1))
    g.computeBoundingSphere()
    // no depth test: from 36 km up a metre above the land is below depth precision, so it is ordered after the ground instead;
    // drawn only where the citywide land wrote the stencil, so the edge is the coastline rather than a hex stair
    const material = new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true, opacity: L.field.opacity, depthWrite: false, depthTest: false, toneMapped: false,
      stencilWrite: true, stencilWriteMask: 0, stencilRef: 1, stencilFunc: THREE.EqualStencilFunc,
      stencilFail: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, stencilZPass: THREE.KeepStencilOp,
    })
    this.fieldNeutral.value.set(L.field.neutral)
    this.fieldMix.value = L.field.mix
    installFieldTheme(material, this.fieldNeutral, this.fieldMix)
    this.field = new THREE.Mesh(g, material)
    this.field.position.y = 0.6
    this.field.renderOrder = -8
    this.field.visible = !this.activeArea
    this.scene.add(this.field)
    this.syncCityLayerVisibility()
  }

  /** Keep the city coast around the detailed borough map. */
  private updateBaseMapVisibility() {
    this.cityLayerGroup.visible = true
  }

  /** Keep departing borough cells visible until the camera reaches its destination. */
  private hexVisible(h3: string): boolean {
    if (!this.activeArea && this.flightAreas.size === 0) return false
    const a = this.areaOfCell(h3)
    return a === null || a === this.activeArea || this.flightAreas.has(a)
  }

  /** Whether an r9 cell's centre lies inside a borough outline. Unlike areaOfCell there is no tile fallback: this is the city line. */
  private insideBorough(h3: string): boolean {
    const cached = this.cellInBorough.get(h3)
    if (cached !== undefined) return cached
    const [cx, cy] = this.projector.xy(...cellToLatLng(h3))
    let inside = false
    for (const a of this.areas.values()) {
      if (cx >= a.bounds.minX && cx <= a.bounds.maxX && cy >= a.bounds.minY && cy <= a.bounds.maxY && pointInRing(cx, cy, a.outline)) {
        inside = true
        break
      }
    }
    this.cellInBorough.set(h3, inside)
    return inside
  }

  /** Which area an r9 cell belongs to: its centre against the borough outlines, else the area of its r7 tile. */
  private areaOfCell(h3: string): string | null {
    const cached = this.cellArea.get(h3)
    if (cached !== undefined) return cached
    const [cx, cy] = this.projector.xy(...cellToLatLng(h3))
    let area: string | null = null
    for (const [id, a] of this.areas) {
      if (cx >= a.bounds.minX && cx <= a.bounds.maxX && cy >= a.bounds.minY && cy <= a.bounds.maxY && pointInRing(cx, cy, a.outline)) {
        area = id
        break
      }
    }
    if (area === null) area = this.tileAreas[cellToParent(h3, 7)] ?? null
    this.cellArea.set(h3, area)
    return area
  }

  private queueHexDisplay() {
    const f = this.flight
    if (!f || f.duration <= 100 || f.radius0 <= AREA_DISTANCE || f.radius1 > AREA_DISTANCE + 1) return
    // CPU geometry can already exist for the whole borough, but its first GPU upload
    // must not happen in a single wide-view frame. Reveal nearest cells during approach.
    this.pendingHexReveal = this.visibleHexes.filter((entry) => !this.renderedHexes.has(entry))
    this.pendingHexReveal.sort((a, b) => b.mesh.position.distanceToSquared(f.t1) - a.mesh.position.distanceToSquared(f.t1))
    for (const entry of this.pendingHexReveal) entry.mesh.visible = false
  }

  private interruptFlight() {
    if (!this.flight) return
    this.flight = null
    const revealing = this.pendingHexReveal
    this.controls.enabled = true
    this.flightAreas.clear()
    this.applyAreaVisibility()
    this.pendingHexReveal = revealing.filter((entry) => entry.mesh.visible)
    for (const entry of this.pendingHexReveal) entry.mesh.visible = false
    this.setTiles(this.requestedTiles)
    this.lastView.x = NaN // resume viewport-driven requests at the user's current position
    this.invalidate()
  }

  private fly(target: THREE.Vector3, position: THREE.Vector3, duration?: number) {
    // Flush OrbitControls inertia without letting a leftover pan/zoom move the starting pose.
    const savedTarget = this.controls.target.clone()
    const savedPosition = this.camera.position.clone()
    const damping = this.controls.enableDamping
    this.controls.enableDamping = false
    this.updatingControls = true
    this.controls.update()
    this.controls.target.copy(savedTarget)
    this.camera.position.copy(savedPosition)
    this.controls.update()
    this.updatingControls = false
    this.controls.enableDamping = damping
    const from = new THREE.Spherical().setFromVector3(this.camera.position.clone().sub(this.controls.target))
    const to = new THREE.Spherical().setFromVector3(position.clone().sub(target))
    this.flight = {
      t0: this.controls.target.clone(), t1: target,
      radius0: from.radius, radius1: to.radius,
      polar0: from.phi, polar1: to.phi,
      azimuth0: from.theta,
      azimuthDelta: Math.atan2(Math.sin(to.theta - from.theta), Math.cos(to.theta - from.theta)),
      start: performance.now(),
      duration: typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 1 : duration ?? THREE.MathUtils.clamp(
        450 + 210 * Math.abs(Math.log(to.radius / from.radius)) +
        140 * Math.log1p(savedTarget.distanceTo(target) / Math.max(600, Math.min(from.radius, to.radius))),
        450, 1400,
      ),
    }
    this.controls.enabled = false
    this.queueHexDisplay()
    // Load the destination while the camera moves, without requesting intermediate tiles.
    if (this.viewReportTimer !== null) {
      clearTimeout(this.viewReportTimer)
      this.viewReportTimer = null
    }
    this.lastView = { x: target.x, z: target.z, wide: to.radius > WIDE_DISTANCE, t: performance.now() }
    const { lat, lon } = this.projector.latLon(target.x, -target.z)
    this.callbacks.onView({ lat, lon, distance: to.radius })
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
    // The far badge remains visible above buildings at a distance.
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
      m.renderOrder = MARKER_ORDER + 0.6 + k * 0.1
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
    // Geometry stays centred on the cell so scale.z raises it from street level.
    const geometry = buildHexPrism(ring.map(([x, y]) => [x - cx, y - cy]))
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
    const height = heightFor(this.mode, cell)
    mesh.scale.z = height
    mesh.userData = { h3: cell.h3 }
    mesh.visible = this.hexVisible(cell.h3)
    const entry = { mesh, targetHeight: height, targetColour: new THREE.Color(material.color), flashUntil: 0 }
    mesh.onAfterRender = () => {
      this.renderedHexes.add(entry)
      mesh.onAfterRender = THREE.Object3D.prototype.onAfterRender
    }
    return entry
  }

  private retintBuildings() {
    for (const t of this.tiles.values()) this.retintTile(t)
  }

  private retintTile(t: TileMeshes) {
    if (!t.buildings) return
    const colours: Record<string, string> = {}
    for (const range of t.ranges) {
      const cell = this.cells.get(range.h3)
      if (cell && !(range.h3 in colours)) colours[range.h3] = colourFor(this.mode, cell)
    }
    tintBuildingGeometry(t.buildings.geometry, t.ranges, { colours, day: LOOKS.day, night: LOOKS.night })
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
      this.interruptFlight()
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

  private handleVisibility() {
    if (document.hidden) {
      cancelAnimationFrame(this.raf)
      this.raf = 0
      this.keys.clear()
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
      // 2. the coloured prism under the pointer (inside a borough only).
      const dist = this.camera.position.distanceTo(this.controls.target)
      if (!info && this.activeArea && dist > HEX_PICK_DISTANCE) {
        const hits = this.raycaster.intersectObjects(this.visibleHexMeshes, false)
        if (hits.length) hexHit = hits[0].object.userData.h3 as string
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
    if (this.flight) return
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

  private loop() {
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
    const dt = Math.min(0.05, (now - this.lastFrame) / 1000)
    this.lastFrame = now
    // camera flight
    if (this.flight) {
      const f = this.flight
      const s = smoothstep(Math.min(1, (now - f.start) / f.duration))
      // Constant proportional zoom feels even across city and street scales. Couple pan to
      // radius so an inward flight centres the destination while there is still room to see it.
      const radius = f.radius0 * Math.pow(f.radius1 / f.radius0, s)
      const pan = Math.abs(f.radius1 - f.radius0) > 1 ? (radius - f.radius0) / (f.radius1 - f.radius0) : s
      this.controls.target.lerpVectors(f.t0, f.t1, pan)
      this.camera.position.setFromSphericalCoords(
        radius,
        THREE.MathUtils.lerp(f.polar0, f.polar1, s),
        f.azimuth0 + f.azimuthDelta * s,
      ).add(this.controls.target)
      if (s >= 1) {
        this.flight = null
        if (this.flightAreas.size) {
          this.flightAreas.clear()
          this.applyAreaVisibility()
          this.setTiles(this.requestedTiles)
        }
        this.updateBaseMapVisibility()
        this.controls.enabled = true
        this.pointerDirty = true // what is under the still pointer has changed
      }
    }
    this.applyKeys(dt)
    this.updatingControls = true
    const controlsChanged = this.controls.update()
    this.updatingControls = false
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
    // The shadow box spans 8.4 km. Move it in 512 m steps so ordinary camera
    // motion reuses the map instead of redrawing every building into it each frame.
    // An overview-to-borough approach loads only destination buildings. Anchor their
    // shadow box there immediately instead of redrawing it at each intermediate pan step.
    const shadowTarget = this.flight && this.flight.radius0 > AREA_DISTANCE && this.flight.radius1 <= AREA_DISTANCE + 1
      ? this.flight.t1 : this.controls.target
    const shadowX = Math.round(shadowTarget.x / 512) * 512
    const shadowZ = Math.round(shadowTarget.z / 512) * 512
    if (this.key.target.position.x !== shadowX || this.key.target.position.z !== shadowZ) {
      this.renderer.shadowMap.needsUpdate = true
      this.key.target.position.set(shadowX, 0, shadowZ)
      this.key.position.set(shadowX - 3200, 4600, shadowZ + 2800)
    }
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
      if (oldPinVisible !== m.pin.visible || (m.pin.visible && (Math.abs(oldPinScaleX - m.pin.scale.x) > 0.0001 ||
          Math.abs(oldPinScaleY - m.pin.scale.y) > 0.0001 || Math.abs(oldPinY - m.group.position.y) > 0.0001))) {
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
    // Keep first-time GPU uploads within a small batch even when the camera sees a whole borough.
    for (let n = 0; n < 48 && this.pendingHexReveal.length; n++) {
      const entry = this.pendingHexReveal.pop()!
      entry.mesh.visible = true
    }
    // Keep the shadow shader variant stable, but skip its map pass at night.
    if (!this.look.sun.shadows && this.key.shadow.map) this.renderer.shadowMap.needsUpdate = false
    this.renderer.render(this.scene, this.camera)
    if (this.pendingHexReveal.length || this.flight || this.keys.size > 0 || this.locator || hexAnimating || controlsChanged || this.nodes.size > 0 || this.spots.length > 0) {
      this.scheduleFrame()
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
