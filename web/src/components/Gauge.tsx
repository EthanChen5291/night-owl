// An activity ring around a node icon. The ring sweeps from green (quiet) through amber to red (busy):
// the filled arc grows thicker and more opaque as it approaches `value` (0..1), so a busy owl reads as a
// heavy, vivid ring and a quiet one as a thin trace. The centre is the sensor node itself (dark caps,
// glowing body, main lens, IR lens, PIR dome). The number under the ring is whatever the caller passes.

import { useId } from 'react'

interface Props {
  value: number
  label: string | number
  size?: number
}

const START = -135 // degrees, 7 o'clock
const SWEEP = 270
const SEGMENTS = 24

function colourAt(t: number): string {
  // green -> amber -> red, stops tuned to read on both glass themes
  const stops: [number, [number, number, number]][] = [
    [0, [31, 138, 88]],
    [0.5, [214, 158, 46]],
    [1, [211, 55, 44]],
  ]
  const i = t <= 0.5 ? 0 : 1
  const [t0, a] = stops[i]
  const [t1, b] = stops[i + 1]
  const f = Math.max(0, Math.min(1, (t - t0) / (t1 - t0)))
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)}, ${Math.round(a[1] + (b[1] - a[1]) * f)}, ${Math.round(a[2] + (b[2] - a[2]) * f)})`
}

function arc(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const p = (a: number) => [cx + r * Math.cos((a * Math.PI) / 180), cy + r * Math.sin((a * Math.PI) / 180)]
  const [x0, y0] = p(a0)
  const [x1, y1] = p(a1)
  const large = a1 - a0 > 180 ? 1 : 0
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`
}

const EASE = 'stroke-width 0.6s cubic-bezier(.2,.8,.2,1), opacity 0.6s cubic-bezier(.2,.8,.2,1)'

/** The sensor node, drawn in a 20 x 26 box whose centre is (0, 0). */
function NodeIcon({ glowId }: { glowId: string }) {
  return (
    <g>
      {/* glowing body */}
      <rect x={-9} y={-11.5} width={18} height={23} rx={2.6} fill="#f2f5fa" stroke="rgba(40,48,60,0.45)" strokeWidth={0.6} filter={`url(#${glowId})`} />
      {/* side light rails */}
      <rect x={-7.2} y={-8} width={1.6} height={16} rx={0.8} fill="#ffffff" opacity={0.9} />
      <rect x={5.6} y={-8} width={1.6} height={16} rx={0.8} fill="#ffffff" opacity={0.9} />
      {/* dark caps, flush with the body, rounded outer corners; a notch on the top one */}
      <path d="M -7.4 -13 h 14.8 a 2.6 2.6 0 0 1 2.6 2.6 v 2.4 h -20 v -2.4 a 2.6 2.6 0 0 1 2.6 -2.6 z" fill="#262b34" />
      <path d="M -7.4 13 h 14.8 a 2.6 2.6 0 0 0 2.6 -2.6 v -2.4 h -20 v 2.4 a 2.6 2.6 0 0 0 2.6 2.6 z" fill="#262b34" />
      <rect x={-2.6} y={-13} width={5.2} height={1.5} rx={0.4} fill="#3d4453" />
      {/* main lens */}
      <circle cx={0} cy={-4.6} r={4.1} fill="#c9ced8" stroke="#7d8593" strokeWidth={0.5} />
      <circle cx={0} cy={-4.6} r={2.9} fill="#1b1f27" />
      <circle cx={0} cy={-4.6} r={1.6} fill="#2c3340" />
      <circle cx={-0.9} cy={-5.5} r={0.7} fill="#dff1ff" opacity={0.95} />
      {/* IR lens */}
      <rect x={-2.1} y={1} width={4.2} height={3.6} rx={0.7} fill="#1b1f27" />
      <circle cx={0} cy={2.8} r={1} fill="#3a4150" />
      <circle cx={-0.35} cy={2.45} r={0.3} fill="#ffe9f2" />
      {/* PIR dome */}
      <circle cx={0} cy={8} r={3.1} fill="#ffffff" stroke="rgba(120,130,150,0.45)" strokeWidth={0.4} />
      <path d="M -1.6 6.6 l 1.6 -0.9 l 1.6 0.9 v 1.8 l -1.6 0.9 l -1.6 -0.9 z" fill="none" stroke="rgba(120,130,150,0.5)" strokeWidth={0.35} />
    </g>
  )
}

export default function Gauge({ value, label, size = 56 }: Props) {
  const v = Math.max(0, Math.min(1, value))
  const c = size / 2
  const r = size / 2 - 5
  const glowId = useId()
  const maxWidth = 2 + 3 * v // the arc's weight at its tip grows with activity
  const iconScale = (r * 1.3) / 26 // the 26-unit-tall icon fills ~65% of the ring
  return (
    <svg className="gauge" width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`activity ${Math.round(v * 100)}%`}>
      <defs>
        <filter id={glowId} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="1.2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {Array.from({ length: SEGMENTS }, (_, i) => {
        const a0 = START + (SWEEP * i) / SEGMENTS
        const a1 = START + (SWEEP * (i + 1)) / SEGMENTS - 1.5
        const t = (i + 0.5) / SEGMENTS
        const filled = t <= v + 0.02
        // along the filled arc the stroke swells from a thin trace to maxWidth; unfilled segments stay faint
        const along = filled && v > 0 ? Math.min(1, t / Math.max(v, 0.04)) : 0
        const width = filled ? 1.6 + (maxWidth - 1.6) * along : 1.4
        const opacity = filled ? 0.45 + 0.55 * along : 0.16
        return <path key={i} d={arc(c, c, r, a0, a1)} stroke={colourAt(t)} strokeWidth={width} strokeLinecap="round" fill="none" opacity={opacity} style={{ transition: EASE }} />
      })}
      <g transform={`translate(${c} ${c - 1}) scale(${iconScale})`}>
        <NodeIcon glowId={glowId} />
      </g>
      <text x={c} y={size - 3} textAnchor="middle" fontSize={10} fontWeight={600} fill="currentColor">
        {label}
      </text>
    </svg>
  )
}
