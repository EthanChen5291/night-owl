import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { cellToBoundary, cellToLatLng } from 'h3-js'
import { colourFor, heightFor } from '../colours'
import type { Building, Cell, Mode, PlanNode, Preset } from '../types'
import { makeProjector, type LatLon, type Projector } from './projection'

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
}

const GROUND = 0x0b0d14
const FOCUS_DISTANCE = 900 // metres from the camera to a focused cell
const FLASH_MS = 1500
const BUILDING_BASE = new THREE.Color(0x2a2d38)
const BUILDING_TINT = 0.55 // how much of the cell colour the building takes

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
  private planGroup = new THREE.Group()
  private buildingMesh: THREE.Mesh | null = null
  private buildingRanges: BuildingRange[] = []
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
  private focusCamera: THREE.Vector3 | null = null
  private canvas: HTMLCanvasElement

  constructor(canvas: HTMLCanvasElement, centre: LatLon, onHover: HoverHandler) {
    this.canvas = canvas
    this.onHover = onHover
    this.projector = makeProjector(centre)
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' })
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.shadowMap.enabled = false

    this.camera = new THREE.PerspectiveCamera(50, 1, 5, 30_000)
    this.camera.position.set(1800, 1500, 2600)
    this.controls = new OrbitControls(this.camera, canvas)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.maxPolarAngle = Math.PI * 0.47
    this.controls.minDistance = 150
    this.controls.maxDistance = 12_000
    this.controls.target.set(0, 0, 0)

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(40_000, 40_000),
      new THREE.MeshStandardMaterial({ color: GROUND, roughness: 1, metalness: 0 }),
    )
    ground.rotation.x = -Math.PI / 2
    ground.position.y = -0.5
    this.scene.add(ground)

    const grid = new THREE.GridHelper(12_000, 60, 0x1b2030, 0x151926)
    grid.position.y = -0.2
    this.scene.add(grid)

    this.ambient = new THREE.AmbientLight(0xffffff, 0.15)
    this.hemi = new THREE.HemisphereLight(0x3a4a7a, 0x0a0a10, 0.5)
    this.key = new THREE.DirectionalLight(0xffb070, 1.6)
    this.key.position.set(-2500, 1800, 1200)
    this.scene.add(this.ambient, this.hemi, this.key)
    this.scene.add(this.hexGroup, this.planGroup)
    this.setPreset('night')

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
    this.retintBuildings()
  }

  setPreset(preset: Preset) {
    if (preset === 'flat') {
      this.scene.background = new THREE.Color(0x14161e)
      this.scene.fog = null
      this.ambient.intensity = 1.0
      this.ambient.color.set(0xffffff)
      this.hemi.intensity = 0.0
      this.key.intensity = 0.0
    } else {
      this.scene.background = new THREE.Color(0x05060a)
      this.scene.fog = new THREE.Fog(0x05060a, 4000, 14_000)
      this.ambient.intensity = 0.12
      this.ambient.color.set(0x8090c0)
      this.hemi.intensity = 0.45
      this.key.intensity = 1.5
    }
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

  /** Fly to a cell: glide the orbit target onto it and bring the camera in to ~FOCUS_DISTANCE,
   *  keeping the current viewing angle. */
  focusCell(h3: string) {
    const entry = this.hexes.get(h3)
    if (!entry) return
    const p = entry.mesh.position
    this.focusTarget = new THREE.Vector3(p.x, 0, p.z)
    const dir = this.camera.position.clone().sub(this.controls.target).normalize()
    this.focusCamera = this.focusTarget.clone().add(dir.multiplyScalar(FOCUS_DISTANCE))
  }

  /** Optional bake from city/build_city.py. One merged geometry with vertex colours. */
  setBuildings(buildings: Building[]) {
    if (this.buildingMesh) {
      this.scene.remove(this.buildingMesh)
      this.buildingMesh.geometry.dispose()
      this.buildingMesh = null
      this.buildingRanges = []
    }
    if (buildings.length === 0) return
    const geometry = buildExtrusions(buildings, this.buildingRanges)
    const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85, metalness: 0.05 })
    this.buildingMesh = new THREE.Mesh(geometry, material)
    this.buildingMesh.rotation.x = -Math.PI / 2 // shape (x, y=north, z=up) -> three (x, y=up, -z)
    this.scene.add(this.buildingMesh)
    this.retintBuildings()
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
      opacity: 0.88,
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
    const attr = this.buildingMesh.geometry.getAttribute('color') as THREE.BufferAttribute
    const tmp = new THREE.Color()
    for (const range of this.buildingRanges) {
      const cell = this.cells.get(range.h3)
      if (cell) tmp.set(colourFor(this.mode, cell)).lerp(BUILDING_BASE, 1 - BUILDING_TINT)
      else tmp.copy(BUILDING_BASE)
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
      const hits = this.raycaster.intersectObjects(this.hexGroup.children, false)
      hit = hits.length ? (hits[0].object.userData.h3 as string) : null
    }
    if (hit !== this.hovered) {
      const prev = this.hovered ? this.hexes.get(this.hovered) : undefined
      if (prev) prev.mesh.material.opacity = 0.88
      const next = hit ? this.hexes.get(hit) : undefined
      if (next) next.mesh.material.opacity = 1
      this.hovered = hit
    }
    this.onHover(hit, this.pointerClient.x, this.pointerClient.y)
  }

  private loop = () => {
    if (this.disposed) return
    this.raf = requestAnimationFrame(this.loop)
    const now = performance.now()
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
      if (this.focusCamera) this.camera.position.lerp(this.focusCamera, 0.08)
      const doneTarget = this.controls.target.distanceTo(this.focusTarget) < 2
      const doneCamera = !this.focusCamera || this.camera.position.distanceTo(this.focusCamera) < 5
      if (doneTarget && doneCamera) {
        this.focusTarget = null
        this.focusCamera = null
      }
    }
    if (this.pointerDirty) this.pick()
    this.controls.update()
    this.renderer.render(this.scene, this.camera)
  }
}

// ---------------------------------------------------------------- helpers

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
 * Extrude every footprint into one indexed BufferGeometry (top cap + walls, no bottom cap).
 * Built in shape space (x east, y north, z up); the mesh is rotated -90deg about x afterwards.
 * `ranges` receives the vertex range of each building so its colour can be updated per mode.
 */
function buildExtrusions(buildings: Building[], ranges: BuildingRange[]): THREE.BufferGeometry {
  let nVerts = 0
  let nIndex = 0
  for (const b of buildings) {
    const n = b.footprint.length
    if (n < 3) continue
    nVerts += n + 4 * n
    nIndex += (n - 2) * 3 + 6 * n
  }
  const pos = new Float32Array(nVerts * 3)
  const nor = new Float32Array(nVerts * 3)
  const col = new Float32Array(nVerts * 3)
  const idx = nVerts > 65_535 ? new Uint32Array(nIndex) : new Uint16Array(nIndex)
  let v = 0
  let k = 0
  for (const b of buildings) {
    const pts = b.footprint
    const n = pts.length
    if (n < 3) continue
    const h = Math.max(1, b.height || 3)
    const start = v
    // enforce counter-clockwise so the walls face outward
    const ccw = THREE.ShapeUtils.isClockWise(pts.map(([x, y]) => new THREE.Vector2(x, y))) ? [...pts].reverse() : pts
    // top cap
    const tri = THREE.ShapeUtils.triangulateShape(
      ccw.map(([x, y]) => new THREE.Vector2(x, y)),
      [],
    )
    for (let i = 0; i < n; i++) {
      pos.set([ccw[i][0], ccw[i][1], h], (v + i) * 3)
      nor.set([0, 0, 1], (v + i) * 3)
    }
    for (const [a, b2, c] of tri) {
      idx[k++] = v + a
      idx[k++] = v + b2
      idx[k++] = v + c
    }
    v += n
    // walls, 4 verts per edge for flat normals
    for (let i = 0; i < n; i++) {
      const [x0, y0] = ccw[i]
      const [x1, y1] = ccw[(i + 1) % n]
      const dx = x1 - x0
      const dy = y1 - y0
      const len = Math.hypot(dx, dy) || 1
      const nx = dy / len
      const ny = -dx / len
      const base = v
      pos.set([x0, y0, 0, x1, y1, 0, x1, y1, h, x0, y0, h], base * 3)
      for (let j = 0; j < 4; j++) nor.set([nx, ny, 0], (base + j) * 3)
      idx[k++] = base
      idx[k++] = base + 1
      idx[k++] = base + 2
      idx[k++] = base
      idx[k++] = base + 2
      idx[k++] = base + 3
      v += 4
    }
    ranges.push({ h3: b.h3, start, count: v - start })
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  g.setAttribute('normal', new THREE.BufferAttribute(nor, 3))
  g.setAttribute('color', new THREE.BufferAttribute(col, 3))
  g.setIndex(new THREE.BufferAttribute(idx, 1))
  g.computeBoundingSphere()
  return g
}
