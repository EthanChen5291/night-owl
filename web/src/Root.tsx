import { lazy, startTransition, Suspense, useEffect, useRef, useState } from 'react'
import { createPageNavigation, isDashboardPath, onNavigate } from './nav'

const loadMap = () => import('./App.tsx')
const loadDashboard = () => import('./dashboard/DashboardPage.tsx')
const MapPage = lazy(loadMap)
const DashboardPage = lazy(loadDashboard)

type Direction = 'forward' | 'back'
interface Leaving { path: string; direction: Direction }

function Page({ path }: { path: string }) {
  return isDashboardPath(path) ? <DashboardPage /> : <MapPage />
}

/** Picks the page for the current URL and slides between the map and the dashboard on in-app navigation. */
export default function Root() {
  const [current, setCurrent] = useState(() => window.location.pathname)
  const [leaving, setLeaving] = useState<Leaving | null>(null)
  const currentRef = useRef(current)

  useEffect(() => {
    // Load before sliding, but never let an older chunk load override newer navigation.
    const navigation = createPageNavigation(currentRef.current,
      (path) => isDashboardPath(path) ? loadDashboard() : loadMap(),
      (path, from) => {
        const kind = isDashboardPath(path)
        currentRef.current = path
        startTransition(() => {
          setCurrent(path)
          setLeaving(kind === isDashboardPath(from) ? null : { path: from, direction: kind ? 'forward' : 'back' })
        })
      },
      () => window.location.reload(),
    )
    const go = (path: string) => { void navigation.go(path) }
    const pop = () => go(window.location.pathname)
    window.addEventListener('popstate', pop)
    const off = onNavigate(go)
    // Warm the other page's chunk once the current one is idle.
    const idle = window.setTimeout(() => { void (isDashboardPath(currentRef.current) ? loadMap() : loadDashboard()).catch(() => { /* navigation can retry */ }) }, 1500)
    return () => { navigation.cancel(); window.removeEventListener('popstate', pop); off(); window.clearTimeout(idle) }
  }, [])

  const direction = leaving?.direction
  return <Suspense fallback={<div className="loading">Loading…</div>}><div className="pages">
    {(leaving ? [leaving.path, current] : [current]).map((path) => {
      const departing = path === leaving?.path
      return <div className={`page${leaving ? ` ${departing ? 'leaving' : 'entering'} ${direction}` : ''}`}
        key={isDashboardPath(path) ? 'dashboards' : 'map'} inert={departing} aria-hidden={departing || undefined}
        onAnimationEnd={departing ? (event) => {
          if (event.target === event.currentTarget) setLeaving((active) => active === leaving ? null : active)
        } : undefined}>
        <Page path={path} />
      </div>
    })}
    {leaving && <div className={`page-veil ${direction}`} aria-hidden="true" />}
  </div></Suspense>
}
