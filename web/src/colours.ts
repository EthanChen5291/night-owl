import type { Cell, Mode } from './types'

// Percentile modes use a five-stop sequential ramp. Silence uses blue through neutral to orange,
// with orange for cells where Model B ranks above Model A.
const SEQUENTIAL = ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725']
const DIVERGING = ['#1f5aa6', '#86b3da', '#dedbd3', '#e0964f', '#b8471a']

export const MODES: { id: Mode; label: string; field: 'pct_a' | 'pct_b' | 'silence'; hint: string }[] = [
  { id: 'a', label: 'Complaints', field: 'pct_a', hint: 'where people call 311 about rats' },
  { id: 'b', label: 'Likelihood of rats', field: 'pct_b', hint: 'from buildings, trash and street conditions' },
  { id: 'silence', label: 'Silent blocks', field: 'silence', hint: 'rats likely, few complaints' },
]

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  const c = (v: number) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}

function ramp(stops: string[], t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(x))
  const f = x - i
  const a = hexToRgb(stops[i])
  const b = hexToRgb(stops[i + 1])
  return rgbToHex([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f])
}

/** t in 0..1 */
export const sequential = (t: number) => ramp(SEQUENTIAL, t)

/** t in -1..1, 0 is the neutral centre */
export const diverging = (t: number) => ramp(DIVERGING, (Math.max(-1, Math.min(1, t)) + 1) / 2)

export function valueFor(mode: Mode, cell: Cell): number {
  return mode === 'a' ? cell.pct_a : mode === 'b' ? cell.pct_b : cell.silence
}

export function colourFor(mode: Mode, cell: Cell): string {
  return mode === 'silence' ? diverging(cell.silence / 100) : sequential(valueFor(mode, cell) / 100)
}

/** Colour for a raw value on the mode's scale (used by the legend). */
export function colourForValue(mode: Mode, v: number): string {
  return mode === 'silence' ? diverging(v / 100) : sequential(v / 100)
}

export function rangeFor(mode: Mode): [number, number] {
  return mode === 'silence' ? [-100, 100] : [0, 100]
}

/** Prism height in metres: percentiles rise with rank; in silence mode only silent blocks stand up. */
export function heightFor(mode: Mode, cell: Cell): number {
  const v = valueFor(mode, cell)
  if (mode === 'silence') return 6 + Math.max(0, v) * 1.4
  return 6 + v * 1.2
}
