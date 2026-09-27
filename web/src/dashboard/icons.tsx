import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement> & { size?: number }
const base = (size: number | undefined, rest: SVGProps<SVGSVGElement>) => ({
  width: size ?? 16,
  height: size ?? 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  ...rest,
})

export const BarIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><path d="M5 20V11M12 20V5M19 20v-6" /></svg>
export const LineIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><path d="m4 16 5-6 4 4 7-8" /><path d="M4 20h16" /></svg>
export const ScatterIcon = ({ size, ...r }: P) => (
  <svg {...base(size, r)}><circle cx="7" cy="15" r="1.6" /><circle cx="11" cy="9" r="1.6" /><circle cx="16" cy="13" r="1.6" /><circle cx="18" cy="6" r="1.6" /><path d="M4 20h16" /></svg>
)
export const TableIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><rect x="4" y="5" width="16" height="14" rx="2.5" /><path d="M4 10h16M4 14.5h16M10 10v9" /></svg>
export const MetricIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><path d="M7 7h2v10M15 17V7l-3 4h5" /></svg>
export const RefreshIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><path d="M20 11a8 8 0 0 0-14.3-4.3L4 8.5" /><path d="M4 4v4.5h4.5" /><path d="M4 13a8 8 0 0 0 14.3 4.3L20 15.5" /><path d="M20 20v-4.5h-4.5" /></svg>
export const DownloadIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14" /></svg>
export const InfoIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8h.01" /></svg>
export const DashIcon = ({ size, ...r }: P) => <svg {...base(size, r)}><rect x="3.5" y="4" width="17" height="16" rx="3" /><path d="M8 15.5v-3M12 15.5V9M16 15.5v-5" /></svg>
export const ArrowUpIcon = ({ size, ...r }: P) => <svg {...base(size, r)} strokeWidth={2.1}><path d="M12 19V5M6 11l6-6 6 6" /></svg>

/** The Night Owl logo as a filled mark. It takes currentColor, so the surrounding rule sets its tint. */
export const OwlMark = ({ size, ...r }: P) => (
  <svg width={size ?? 16} height={size ?? 16} viewBox="19 9 62 79" fill="currentColor" aria-hidden {...r}>
    <path d="M24.5 14.5 C28.5 20 35 20.2 44 20.4 C56 20.6 64 26 64.2 36 C64.2 37.5 64 38.8 63.6 40 C60.5 32.5 55 29.4 47 28.7 C42 28.4 38.5 28.2 35.5 28.4 C30 26 26.5 20.5 24.5 14.5 Z" />
    <path fillRule="evenodd" d="M35.6 30 C46 29.8 56.5 32 61.8 42.6 C55.5 44.3 43 45.4 38.4 40.6 C36.4 38 35.2 34 35.6 30 Z M50 36.2 m-3.5 0 a3.5 3.5 0 1 0 7 0 a3.5 3.5 0 1 0 -7 0 Z" />
    <path d="M60.4 44.2 L63.5 41.2 L62.4 47.4 Z" />
    <path d="M34.2 30.6 C27.5 36.5 25.6 46 27 56 C28.4 65 37 72.6 51.6 74.2 C45 65.5 41.5 55.5 39.4 44.6 C38.4 39.5 36.4 34.8 34.2 30.6 Z" />
    <path d="M42.8 46 C52.5 46.4 64 48.5 70 54.6 L76.6 83.2 Z" />
  </svg>
)
