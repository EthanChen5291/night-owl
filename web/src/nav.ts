/** Client-side navigation between the map and the dashboard, so the two pages can animate past each other. */
import type { MouseEvent } from 'react'

type Listener = (path: string) => void
const listeners = new Set<Listener>()

export const isDashboardPath = (path: string) => /^\/dashboards\/?$/.test(path)

export function navigate(path: string): void {
  if (path === window.location.pathname) return
  window.history.pushState(null, '', path)
  for (const listener of listeners) listener(path)
}

export function onNavigate(listener: Listener): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

/** Click handler for an in-app link; modified clicks and middle clicks keep the browser's default. */
export function linkClick(path: string) {
  return (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(path)
  }
}
