import * as THREE from 'three'

// Procedural facade: one texture tile covers FACADE_TILE_M metres of wall (4 bays x 4 floors), repeated.
// `map` is the daytime albedo (light frames, blue-grey panes); `emissive` is the lit-window mask for night.
const BAYS = 4
const FLOORS = 4
const BAY_M = 3.2
const FLOOR_M = 3.4
export const FACADE_TILE_M: [number, number] = [BAY_M * BAYS, FLOOR_M * FLOORS]

export function facadeTextures(): { map: THREE.CanvasTexture; emissive: THREE.CanvasTexture } {
  const size = 256
  const bw = size / BAYS
  const fh = size / FLOORS
  const albedo = document.createElement('canvas')
  const lit = document.createElement('canvas')
  albedo.width = albedo.height = lit.width = lit.height = size
  const a = albedo.getContext('2d')!
  const e = lit.getContext('2d')!
  a.fillStyle = '#e6e3dc' // frames and spandrels
  a.fillRect(0, 0, size, size)
  e.fillStyle = '#000'
  e.fillRect(0, 0, size, size)
  let seed = 7
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    return seed / 0x7fffffff
  }
  for (let f = 0; f < FLOORS; f++) {
    for (let b = 0; b < BAYS; b++) {
      const x = b * bw + bw * 0.14
      const y = f * fh + fh * 0.2
      const w = bw * 0.72
      const h = fh * 0.56
      const shade = 0.72 + rnd() * 0.28
      a.fillStyle = `rgb(${Math.round(118 * shade)}, ${Math.round(140 * shade)}, ${Math.round(162 * shade)})`
      a.fillRect(x, y, w, h)
      a.fillStyle = 'rgba(255,255,255,0.35)' // a glint along the top of the pane
      a.fillRect(x, y, w, h * 0.12)
      a.fillStyle = '#cdc9c1' // sill
      a.fillRect(x - bw * 0.04, y + h, w + bw * 0.08, fh * 0.06)
      if (rnd() < 0.38) {
        e.fillStyle = `rgba(255, 214, 160, ${(0.55 + rnd() * 0.45).toFixed(2)})`
        e.fillRect(x, y, w, h)
      }
    }
  }
  const make = (c: HTMLCanvasElement) => {
    const t = new THREE.CanvasTexture(c)
    t.wrapS = t.wrapT = THREE.RepeatWrapping
    t.colorSpace = THREE.SRGBColorSpace
    t.anisotropy = 8
    return t
  }
  return { map: make(albedo), emissive: make(lit) }
}
