import type { ChatMessage, ChartSelection, DashboardArtifact, DashboardEvent, DashboardSpec } from './types'

const base = '/api/dashboards'

async function responseError(response: Response): Promise<Error> {
  try {
    const body = await response.json() as { detail?: string; error?: string }
    return new Error(body.detail ?? body.error ?? `HTTP ${response.status}`)
  } catch {
    return new Error(`HTTP ${response.status}`)
  }
}

export async function fetchCatalog(signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${base}/catalog`, { headers: { accept: 'application/json' }, signal })
  if (!response.ok) throw await responseError(response)
  return response.json() as Promise<unknown>
}

export async function renderDashboard(spec: DashboardSpec, version: number, signal?: AbortSignal): Promise<DashboardArtifact> {
  const response = await fetch(`${base}/render`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    body: JSON.stringify({ spec, version }),
    signal,
  })
  if (!response.ok) throw await responseError(response)
  return response.json() as Promise<DashboardArtifact>
}

export interface ChatRequest {
  message: string
  history: ChatMessage[]
  dashboard?: DashboardSpec
  selection?: ChartSelection
  version?: number
}

export async function streamDashboardChat(body: ChatRequest, onEvent: (event: DashboardEvent) => void, signal: AbortSignal): Promise<void> {
  const response = await fetch(`${base}/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await responseError(response)
  if (!response.body) throw new Error('The dashboard stream did not start.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const consume = (frame: string) => {
    const payload = frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n')
    if (!payload) return
    onEvent(JSON.parse(payload) as DashboardEvent)
  }
  try {
    for (;;) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      buffer = buffer.replace(/\r\n/g, '\n')
      let cut: number
      while ((cut = buffer.indexOf('\n\n')) >= 0) {
        consume(buffer.slice(0, cut))
        buffer = buffer.slice(cut + 2)
      }
      if (done) break
    }
    if (buffer.trim()) consume(buffer)
  } finally {
    reader.releaseLock()
  }
}
