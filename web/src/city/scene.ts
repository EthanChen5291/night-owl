import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'
import { cellToBoundary, cellToLatLng, cellToParent } from 'h3-js'
import { colourFor, heightFor } from '../colours'
import type { Building, Cell, CityLayers, Mode, PlanNode, Poly, Preset, Tree } from '../types'
import { makeProjector, type LatLon, type Projector } from './projection'
import { FACADE_TILE_M, facadeTextures } from './facade'

// No React in here. App owns the data; Scene.tsx owns the lifecycle; this class owns three.js.
// Coordinates: local metres, x east, y north (from the projector); mapped to three.js x / -z.

export type HoverHandler = (h3: string | null, clientX: number, clientY: number) => void

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

const FLASH_MS = 1500
const COARSE_RES = 7 // ~2.4 km across; 5k r9 cells become ~120 prisms
const COARSE_HEIGHT = 4 // r7 prisms are taller so they still read from 30 km up
const COARSE_DISTANCE = 9000 // orbit distance (m) past which the coarse prisms replace the r9 ones

// Flat layers from city/build_city.py, drawn in this order (later wins where they overlap).
const FLAT_LAYERS = ['land', 'roads', 'parks', 'water'] as const
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
  /** ground is the water: everything not covered by land */
  layers: Record<FlatLayer | 'ground' | 'trees', number>
  /** building base colours by height band: low (brick), mid (stone), tall (glass) */
  facades: [number, number, number]
  buildingTint: number // how much of the cell colour a building takes
  tintLift: number // how far the cell colour is pushed toward white before tinting (keeps day facades pastel)
  windows: number // emissive intensity of the lit-window mask
  hexOpacity: number
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
    buildingTint: 0.38,
    tintLift: 0.5,
    windows: 0,
    hexOpacity: 0.5,
  },
  night: {
    background: 0x05060a,
    fog: [3500, 14000],
    zenith: 0x04050a,
    horizon: 0x0d1220,
    ambient: { colour: 0x8090c0, intensity: 0.12 },
    hemi: { sky: 0x3a4a7a, ground: 0x0a0a10, intensity: 0.45 },
    sun: { colour: 0xffb070, intensity: 1.5, shadows: false },
    exposure: 1.0,
    layers: { ground: 0x04060c, water: 0x06091a, land: 0x10131b, roads: 0x1a1e2a, parks: 0x0e1d18, trees: 0x2c5a3a },
    facades: [0x262a35, 0x2a2d38, 0x2c3140],
    buildingTint: 0.55,
    tintLift: 0,
    windows: 0.65,
    hexOpacity: 0.88,
  },
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
  private hexes = new Map<string, HexEntry>()
  private hexGroup = new THREE.Group()
  // citywide level of detail: the cells aggregated to their r7 parents, shown when the camera pulls back
  private coarse = new Map<string, HexEntry>()
  private coarseCells = new Map<string, Cell>()
  private coarseGroup = new THREE.Group()
  private planGroup = new THREE.Group()
  private layerGroup = new THREE.Group()
  private layerMeshes = new Map<FlatLayer | 'trees', THREE.Mesh | THREE.InstancedMesh>()
  private ground: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshStandardMaterial>
  private sky: THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial>
  private grid: THREE.GridHelper
  private look: Look = LOOKS.day
  private buildingMesh: THREE.Mesh | null = null
  private buildingRanges: BuildingRange[] = []
  private wallMaterial: THREE.MeshStandardMaterial | null = null
  private roofMaterial: THREE.MeshStandardMaterial | null = null
  private facade = facadeTextures()
  private hemi: THREE.HemisphereLight
  private key: THREE.DirectionalLight
  private ambient: THREE.AmbientLight
  private projector: Projector
  private mode: Mode = 'a'
  private cells = new Map<string, Cell>()
  private hovered: string | null = null
  private onHover: HoverHandler
  private raf = 0
  private disposed = false
  private focusTarget: THREE.Vector3 | null = null
  private canvas: HTMLCanvasElement

  constructor(canvas: HTMLCanvasElement, centre: LatLon, onHover: HoverHandler) {
    this.canvas = canvas
    this.onHover = onHover
    this.projector = makeProjector(centre)
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.shadowMap.enabled = true
    this.renderer.shadowMap.type = THREE.PCFShadowMap
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping

    // near = 20 (minDistance is 150) keeps enough depth precision for the flat layers to stack cleanly
    this.camera = new THREE.PerspectiveCamera(50, 1, 20, 150_000)
    this.camera.position.set(1800, 1500, 2600)
    this.controls = new OrbitControls(this.camera, canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.maxPolarAngle = Math.PI * 0.47
    this.controls.minDistance = 150
    this.controls.maxDistance = 40_000
    this.controls.target.set(0, 0, 0)

    this.ground = new THREE.Mesh(
      new THREE.PlaneGeometry(160_000, 160_000),
      new THREE.MeshStandardMaterial({ color: LOOKS.day.layers.ground, roughness: 0.9, metalness: 0 }),
    )
    this.ground.rotation.x = -Math.PI / 2
    this.ground.position.y = -0.5
    this.ground.receiveShadow = true
    this.scene.add(this.ground)

    this.grid = new THREE.GridHelper(12_000, 60, 0x1b2030, 0x151926)
    this.grid.position.y = -0.2
    this.scene.add(this.grid)

    this.sky = makeSky()
    this.scene.add(this.sky)

    this.ambient = new THREE.AmbientLight(0xffffff, 0.15)
    this.hemi = new THREE.HemisphereLight(0x3a4a7a, 0x0a0a10, 0.5)
    // sun from the south-west so the faces the opening camera sees are lit
    this.key = new THREE.DirectionalLight(0xffb070, 1.6)
    this.key.position.set(-3200, 4600, 2800)
    this.key.target.position.set(0, 0, 0)
    this.key.shadow.mapSize.set(4096, 4096)
    const sc = this.key.shadow.camera
    sc.left = sc.bottom = -4200
    sc.right = sc.top = 4200
    sc.near = 500
    sc.far = 16_000
    this.key.shadow.bias = -0.0004
    this.key.shadow.normalBias = 2
    this.scene.add(this.ambient, this.hemi, this.key, this.key.target)
    this.coarseGroup.visible = false
    this.scene.add(this.layerGroup, this.hexGroup, this.coarseGroup, this.planGroup)
    this.setPreset('day')

    canvas.addEventListener('pointermove', this.handlePointerMove)
    canvas.addEventListener('pointerleave', this.handlePointerLeave)
    window.addEventListener('resize', this.resize)
    this.resize()
    this.loop()
  }

  // ---------------------------------------------------------------- public API

  get centre(): LatLon {
    return this.projector.centre
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
    this.rebuildCoarse()
    this.retintBuildings()
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
    for (const [h3, entry] of this.coarse) {
      const cell = this.coarseCells.get(h3)
      if (!cell) continue
      entry.targetHeight = heightFor(mode, cell) * COARSE_HEIGHT
      entry.targetColour.set(colourFor(mode, cell))
    }
    this.retintBuildings()
  }

  /** Average every r9 cell into its r7 parent (mean of the percentile fields) and keep one big prism per parent. */
  private rebuildCoarse() {
    const groups = new Map<string, Cell[]>()
    for (const cell of this.cells.values()) {
      const parent = cellToParent(cell.h3, COARSE_RES)
      const list = groups.get(parent)
      if (list) list.push(cell)
      else groups.set(parent, [cell])
    }
    const seen = new Set<string>()
    for (const [parent, members] of groups) {
      const mean = (f: (c: Cell) => number) => members.reduce((s, c) => s + f(c), 0) / members.length
      const cell: Cell = {
        ...members[0],
        h3: parent,
        score_a: mean((c) => c.score_a),
        score_b: mean((c) => c.score_b),
        pct_a: mean((c) => c.pct_a),
        pct_b: mean((c) => c.pct_b),
        silence: mean((c) => c.silence),
        n_inspections: members.reduce((s, c) => s + c.n_inspections, 0),
      }
      this.coarseCells.set(parent, cell)
      seen.add(parent)
      let entry = this.coarse.get(parent)
      if (!entry) {
        entry = this.makeHex(cell)
        entry.mesh.material.opacity = Math.min(1, this.look.hexOpacity + 0.3)
        this.coarse.set(parent, entry)
        this.coarseGroup.add(entry.mesh)
      }
      entry.targetHeight = heightFor(this.mode, cell) * COARSE_HEIGHT
      entry.targetColour.set(colourFor(this.mode, cell))
    }
    for (const [parent, entry] of this.coarse) {
      if (!seen.has(parent)) {
        this.coarseGroup.remove(entry.mesh)
        entry.mesh.geometry.dispose()
        entry.mesh.material.dispose()
        this.coarse.delete(parent)
        this.coarseCells.delete(parent)
      }
    }
  }

  setPreset(preset: Preset) {
    const L = LOOKS[preset]
    this.look = L
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
    this.renderer.toneMappingExposure = L.exposure
    this.ground.material.color.set(L.layers.ground)
    for (const [name, obj] of this.layerMeshes) (obj.material as THREE.MeshStandardMaterial).color.set(L.layers[name])
    if (this.wallMaterial) this.wallMaterial.emissiveIntensity = L.windows
    for (const [h3, entry] of this.hexes) entry.mesh.material.opacity = h3 === this.hovered ? Math.min(1, L.hexOpacity + 0.15) : L.hexOpacity
    for (const entry of this.coarse.values()) entry.mesh.material.opacity = Math.min(1, L.hexOpacity + 0.3)
    this.retintBuildings()
  }

  setPlan(nodes: PlanNode[]) {
    this.planGroup.clear()
    const cone = new THREE.ConeGeometry(18, 60, 12)
    for (const node of nodes) {
      const [x, y] = this.projector.xy(node.lat, node.lon)
      const cell = this.cells.get(node.h3)
      const base = cell ? heightFor(this.mode, cell) : 6
      const pin = new THREE.Mesh(
        cone,
        new THREE.MeshStandardMaterial({
          color: node.rank === 1 ? 0x5ff0ff : 0xfff2b0,
          emissive: node.rank === 1 ? 0x2bb8c8 : 0x8a7a30,
          emissiveIntensity: 0.9,
          roughness: 0.4,
        }),
      )
      pin.rotation.x = Math.PI
      pin.position.set(x, base + 120 + 30, -y)
      pin.userData = { node }
      const label = makeLabel(String(node.rank))
      label.position.set(x, base + 120 + 95, -y)
      const stem = new THREE.Mesh(
        new THREE.CylinderGeometry(1.5, 1.5, 120, 6),
        new THREE.MeshBasicMaterial({ color: 0x8a8f9c, transparent: true, opacity: 0.6 }),
      )
      stem.position.set(x, base + 60, -y)
      this.planGroup.add(pin, label, stem)
    }
  }

  setPlanVisible(visible: boolean) {
    this.planGroup.visible = visible
  }

  /** Emissive pulse on one cell for ~1.5 s. */
  flash(h3: string) {
    const entry = this.hexes.get(h3)
    if (!entry) return
    entry.flashUntil = performance.now() + FLASH_MS
  }

  /** Glide the orbit target to a cell (the camera keeps its offset). */
  focusCell(h3: string) {
    const entry = this.hexes.get(h3)
    if (!entry) return
    const p = entry.mesh.position
    this.focusTarget = new THREE.Vector3(p.x, 0, p.z)
  }

  /** Bake from city/build_city.py: one merged geometry, walls with the facade texture, roofs plain, vertex colours. */
  setBuildings(buildings: Building[]) {
    if (this.buildingMesh) {
      this.scene.remove(this.buildingMesh)
      this.buildingMesh.geometry.dispose()
      this.buildingMesh = null
      this.buildingRanges = []
    }
    if (buildings.length === 0) return
    const geometry = buildExtrusions(buildings, this.buildingRanges)
    this.wallMaterial ??= new THREE.MeshStandardMaterial({
      vertexColors: true,
      map: this.facade.map,
      emissiveMap: this.facade.emissive,
      emissive: new THREE.Color(0xffd9a0),
      emissiveIntensity: this.look.windows,
      roughness: 0.7,
      metalness: 0.08,
    })
    this.roofMaterial ??= new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, metalness: 0 })
    this.buildingMesh = new THREE.Mesh(geometry, [this.wallMaterial, this.roofMaterial])
    this.buildingMesh.rotation.x = -Math.PI / 2 // shape (x, y=north, z=up) -> three (x, y=up, -z)
    this.buildingMesh.castShadow = true
    this.buildingMesh.receiveShadow = true
    this.scene.add(this.buildingMesh)
    this.retintBuildings()
  }

  /** Flat layers (land, roads, parks, water) as merged meshes, trees as one instanced canopy. */
  setLayers(layers: CityLayers) {
    for (const obj of this.layerMeshes.values()) {
      this.layerGroup.remove(obj)
      obj.geometry.dispose()
      ;(obj.material as THREE.Material).dispose()
    }
    this.layerMeshes.clear()
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
      this.layerMeshes.set(name, mesh)
      this.layerGroup.add(mesh)
    })
    if (layers.trees && layers.trees.length > 0) {
      const canopy = buildTrees(layers.trees, new THREE.MeshStandardMaterial({ color: L.layers.trees, roughness: 0.95 }))
      this.layerMeshes.set('trees', canopy)
      this.layerGroup.add(canopy)
    }
    // the grid was the placeholder for a city; hide it once there is land
    this.grid.visible = !this.layerMeshes.has('land')
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    this.canvas.removeEventListener('pointermove', this.handlePointerMove)
    this.canvas.removeEventListener('pointerleave', this.handlePointerLeave)
    window.removeEventListener('resize', this.resize)
    this.controls.dispose()
    this.scene.traverse((o) => {
      if (o instanceof THREE.Mesh) {
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
    })
    const mesh = new THREE.Mesh(geometry, material)
    mesh.rotation.x = -Math.PI / 2
    mesh.position.set(cx, 0, -cy)
    mesh.scale.z = 1
    mesh.userData = { h3: cell.h3 }
    return { mesh, targetHeight: heightFor(this.mode, cell), targetColour: new THREE.Color(material.color), flashUntil: 0 }
  }

  private retintBuildings() {
    if (!this.buildingMesh) return
    const L = this.look
    const attr = this.buildingMesh.geometry.getAttribute('color') as THREE.BufferAttribute
    const tmp = new THREE.Color()
    const base = new THREE.Color()
    const white = new THREE.Color(0xffffff)
    for (const range of this.buildingRanges) {
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
  }

  private handlePointerLeave = () => {
    this.pointer.set(2, 2)
    this.pointerDirty = true
  }

  private resize = () => {
    const w = this.canvas.clientWidth || 1
    const h = this.canvas.clientHeight || 1
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
  }

  private pick() {
    this.pointerDirty = false
    let hit: string | null = null
    if (this.pointer.x <= 1 && this.pointer.x >= -1) {
      this.raycaster.setFromCamera(this.pointer, this.camera)
      const hits = this.hexGroup.visible ? this.raycaster.intersectObjects(this.hexGroup.children, false) : []
      hit = hits.length ? (hits[0].object.userData.h3 as string) : null
    }
    if (hit !== this.hovered) {
      const prev = this.hovered ? this.hexes.get(this.hovered) : undefined
      if (prev) prev.mesh.material.opacity = this.look.hexOpacity
      const next = hit ? this.hexes.get(hit) : undefined
      if (next) next.mesh.material.opacity = Math.min(1, this.look.hexOpacity + 0.15)
      this.hovered = hit
    }
    this.onHover(hit, this.pointerClient.x, this.pointerClient.y)
  }

  private loop = () => {
    if (this.disposed) return
    this.raf = requestAnimationFrame(this.loop)
    const now = performance.now()
    // past COARSE_DISTANCE the r9 prisms are a few pixels wide: show the r7 aggregates instead
    const wide = this.camera.position.distanceTo(this.controls.target) > COARSE_DISTANCE
    this.hexGroup.visible = !wide
    this.coarseGroup.visible = wide && this.coarse.size > 0
    if (wide && this.hovered) this.pointerDirty = true
    for (const entry of this.coarse.values()) {
      entry.mesh.scale.z += (entry.targetHeight - entry.mesh.scale.z) * 0.12
      entry.mesh.material.color.lerp(entry.targetColour, 0.15)
    }
    for (const entry of this.hexes.values()) {
      const m = entry.mesh
      m.scale.z += (entry.targetHeight - m.scale.z) * 0.12
      m.material.color.lerp(entry.targetColour, 0.15)
      if (entry.flashUntil > now) {
        const t = (entry.flashUntil - now) / FLASH_MS
        const pulse = 0.5 + 0.5 * Math.sin(now / 80)
        m.material.emissive.set(0xffe9a8)
        m.material.emissiveIntensity = (0.4 + 0.6 * pulse) * t * 2.2
      } else if (m.material.emissiveIntensity !== 0) {
        m.material.emissiveIntensity = 0
      }
    }
    if (this.focusTarget) {
      this.controls.target.lerp(this.focusTarget, 0.08)
      if (this.controls.target.distanceTo(this.focusTarget) < 2) this.focusTarget = null
    }
    // fog scales with the orbit distance so pulling back to the whole city does not fog it out
    const fog = this.scene.fog as THREE.Fog | null
    if (fog) {
      const s = Math.max(1, this.camera.position.distanceTo(this.controls.target) / 3500)
      fog.near = this.look.fog[0] * s
      fog.far = this.look.fog[1] * s
    }
    if (this.pointerDirty) this.pick()
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }
}

// ---------------------------------------------------------------- helpers

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

/** One low-poly canopy per tree, instanced: 41k trees in one draw call. */
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

function makeLabel(text: string): THREE.Sprite {
  const size = 96
  const c = document.createElement('canvas')
  c.width = size
  c.height = size
  const ctx = c.getContext('2d')!
  ctx.fillStyle = 'rgba(10,12,20,0.85)'
  ctx.beginPath()
  ctx.arc(size / 2, size / 2, size / 2 - 4, 0, Math.PI * 2)
  ctx.fill()
  ctx.strokeStyle = '#fff2b0'
  ctx.lineWidth = 4
  ctx.stroke()
  ctx.fillStyle = '#fff2b0'
  ctx.font = 'bold 52px system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, size / 2, size / 2 + 2)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: false, transparent: true }))
  sprite.scale.set(70, 70, 1)
  sprite.renderOrder = 10
  return sprite
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
  const index = new IndexArray(nWall + nRoof)
  index.set(wallIdx, 0)
  index.set(roofIdx, nWall)
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('normal', new THREE.BufferAttribute(nor, 3))
  g.setAttribute('color', new THREE.BufferAttribute(col, 3))
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2))
  g.setIndex(new THREE.BufferAttribute(index, 1))
  g.addGroup(0, nWall, 0) // walls: facade material
  g.addGroup(nWall, nRoof, 1) // roofs: plain
  g.computeBoundingSphere()
  return g
}
