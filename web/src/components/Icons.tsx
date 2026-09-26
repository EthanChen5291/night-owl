import type { SVGProps } from 'react'

// One stroke set, 24-unit grid, 1.8 stroke: the whole interface leans on these instead of labels.
type P = SVGProps<SVGSVGElement> & { size?: number }
const base = (size: number | undefined, rest: SVGProps<SVGSVGElement>) => ({
  width: size ?? 18,
  height: size ?? 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  ...rest,
})

/** What the city sees: a home, the 311 caller. */
export const HomeIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M3 11.5 12 4l9 7.5" />
    <path d="M5.5 10v9.5h13V10" />
    <path d="M10 19.5v-5h4v5" />
  </svg>
)

/** What's there: the environmental signal, waves rising from the ground. */
export const SignalIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <circle cx="12" cy="17" r="1.6" fill="currentColor" stroke="none" />
    <path d="M8.5 13.5a5 5 0 0 1 7 0" />
    <path d="M5.8 10.6a9 9 0 0 1 12.4 0" />
    <path d="M3 7.7a13 13 0 0 1 18 0" />
  </svg>
)

/** Silence: a muted bell, the block nobody calls about. */
export const SilenceIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M6.5 16.5V11a5.5 5.5 0 0 1 8.8-4.4" />
    <path d="M17.5 11v5.5h-11" />
    <path d="M10 19.5a2 2 0 0 0 4 0" />
    <path d="M4 4l16 16" />
  </svg>
)

export const SunIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8" />
  </svg>
)

export const MoonIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
  </svg>
)

/** Place an owl: a map pin with a plus. */
export const PinPlusIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11z" />
    <path d="M12 7.5v5M9.5 10h5" />
  </svg>
)

export const OwlIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M5 8.5c0-3 3-5.5 7-5.5s7 2.5 7 5.5v6c0 3.5-3 6.5-7 6.5s-7-3-7-6.5z" />
    <circle cx="9" cy="10" r="1.6" fill="currentColor" stroke="none" />
    <circle cx="15" cy="10" r="1.6" fill="currentColor" stroke="none" />
    <path d="M12 12.5l-1 2h2z" fill="currentColor" stroke="none" />
    <path d="M6 4l2 2M18 4l-2 2" />
  </svg>
)

export const ListIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M8 6h12M8 12h12M8 18h12" />
    <circle cx="4" cy="6" r="1" fill="currentColor" stroke="none" />
    <circle cx="4" cy="12" r="1" fill="currentColor" stroke="none" />
    <circle cx="4" cy="18" r="1" fill="currentColor" stroke="none" />
  </svg>
)

export const TrashIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l.8 12.5h9.4L17.5 7" />
    <path d="M10 11v5M14 11v5" />
  </svg>
)

export const CloseIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)

export const ChevronIcon = ({ size, dir = 'right', ...r }: P & { dir?: 'left' | 'right' | 'up' | 'down' }) => {
  const rot = { right: 0, down: 90, left: 180, up: 270 }[dir]
  return (
    <svg {...base(size, r)} style={{ transform: `rotate(${rot}deg)`, transition: 'transform 0.35s', ...r.style }}>
      <path d="M9 5l7 7-7 7" />
    </svg>
  )
}

export const BackIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M11 5l-7 7 7 7M4 12h16" />
  </svg>
)

/** Suggested placements from the plan. */
export const SparkIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
    <path d="M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" />
  </svg>
)

export const CityIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M3 20h18" />
    <path d="M5 20V9h5v11M10 20V4h5v16M15 20v-7h4v7" />
    <path d="M7 12h1M7 15h1M12 7h1M12 10h1M12 13h1M12 16h1" />
  </svg>
)

export const LayersIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M12 4l9 5-9 5-9-5z" />
    <path d="M3 14l9 5 9-5" />
  </svg>
)

export const RatIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}>
    <path d="M4 15c0-3.5 3-6.5 7-6.5 3.2 0 5.3 1.8 6.6 4.2L21 13" />
    <path d="M4 15c0 2.5 2.2 4 5 4h6.5c1.8 0 3-1.2 3-2.8" />
    <circle cx="9" cy="7.5" r="2.2" />
    <circle cx="15.2" cy="12.4" r="0.8" fill="currentColor" stroke="none" />
    <path d="M3 18.5c1.5 0 2.5-.6 3.2-1.6" />
  </svg>
)
