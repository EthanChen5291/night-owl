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
