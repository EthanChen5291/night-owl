import { lazy, Suspense } from 'react'

const MapPage = lazy(() => import('./App.tsx'))
const DashboardPage = lazy(() => import('./dashboard/DashboardPage.tsx'))

export default function Root() {
  const dashboards = /^\/dashboards\/?$/.test(window.location.pathname)
  return <Suspense fallback={<div className="loading">Loading…</div>}>
    {dashboards ? <DashboardPage /> : <MapPage />}
  </Suspense>
}
