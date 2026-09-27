import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { isDashboardPath, onNavigate } from './nav'

const loadMap = () => import('./App.tsx')
const loadDashboard = () => import('./dashboard/DashboardPage.tsx')
const MapPage = lazy(loadMap)
const DashboardPage = lazy(loadDashboard)

type Direction = 'forward' | 'back'
interface Leaving { path: string; direction: Direction }

function Page({ path }: { path: string }) {
  return <Suspense fallback={<div className="loading">Loading…</div>}>
    {isDashboardPath(path) ? <DashboardPage /> : <MapPage />}
  </Suspense>
}

/** Picks the page for the current URL and slides between the map and the dashboard on in-app navigation. */
export default function Root() {
  const [current, setCurrent] = useState(() => window.location.pathname)
  const [leaving, setLeaving] = useState<Leaving | null>(null)
  const currentRef = useRef(current)

  useEffect(() => {
    let cancelled = false
    const go = (path: string) => {
      const from = currentRef.current
      if (from === path) return
      const kind = isDashboardPath(path)
      // Load the target chunk first so the slide never reveals a loading screen.
      void (kind ? loadDashboard() : loadMap()).then(() => {
        if (cancelled || currentRef.current === path) return
        currentRef.current = path
        setCurrent(path)
        setLeaving(kind === isDashboardPath(from) ? null : { path: from, direction: kind ? 'forward' : 'back' })
      })
    }
    const pop = () => go(window.location.pathname)
    window.addEventListener('popstate', pop)
    const off = onNavigate(go)
    // Warm the other page's chunk once the current one is idle.
    const idle = window.setTimeout(() => { void (isDashboardPath(currentRef.current) ? loadMap() : loadDashboard()) }, 1500)
    return () => { cancelled = true; window.removeEventListener('popstate', pop); off(); window.clearTimeout(idle) }
  }, [])

  const direction = leaving?.direction
  return <div className="pages">
    {leaving && <div className={`page leaving ${direction}`} key={`leaving:${leaving.path}`} inert aria-hidden="true"
      onAnimationEnd={(event) => { if (event.target === event.currentTarget) setLeaving(null) }}>
      <Page path={leaving.path} />
    </div>}
    <div className={`page${leaving ? ` entering ${direction}` : ''}`} key={`page:${isDashboardPath(current) ? 'dashboards' : 'map'}`}>
      <Page path={current} />
    </div>
    {leaving && <div className={`page-veil ${direction}`} aria-hidden="true" />}
  </div>
}
