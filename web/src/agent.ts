// Assistant chat streams responses from POST /api/agent/chat using Server-Sent Events.
// The server keeps each thread's history in SQLite (api/chat_store.py); the browser sends the new question and runs
// the "client tools" (things only the page knows) between rounds.

export type AgentEvent =
  | { type: 'tool'; id: string; name: string; label: string; state: 'start' | 'done' | 'error' }
  | { type: 'image'; src: string; caption?: string }
  | { type: 'thinking'; state: 'start' | 'done' }
  | { type: 'delta'; text: string }
  | { type: 'client_tools'; calls: ClientCall[]; pending_images: { src: string; caption?: string }[] }
  | { type: 'messages'; messages: WireMessage[] }
  | { type: 'thread'; id: string; title: string; answer_id: number }
  | { type: 'error'; text: string }
  | { type: 'done' }

export interface ClientCall {
  id: string
  name: string
  label: string
  args: Record<string, unknown>
}
export interface ClientResult {
  id: string
  content: string
  image?: string
}
/** OpenAI-style chat message, as the server hands it back. */
export type WireMessage = { role: 'user' | 'assistant' | 'tool'; content: string; tool_calls?: unknown[]; tool_call_id?: string }

// ---------------------------------------------------------------- stored threads (api/chat_store.py, SQLite)

/** This browser's anonymous id: its threads are the ones saved under it. Not a login; clearing site data starts afresh. */
let memoryId: string | undefined // private mode: this tab only
function clientId(): string {
  const KEY = 'nightowl.chat.client'
  try {
    const saved = localStorage.getItem(KEY)
    if (saved) return saved
    const id = crypto.randomUUID()
    localStorage.setItem(KEY, id)
    return id
  } catch {
    return (memoryId ??= crypto.randomUUID())
  }
}
const headers = (extra: Record<string, string> = {}) => ({ 'x-chat-client': clientId(), ...extra })

export interface ThreadSummary {
  id: string
  title: string
  updated_at: number
  questions: number
}
export interface StoredTurn {
  id: number
  role: 'user' | 'bot'
  text: string
  steps: { id: string; label: string; state: 'start' | 'done' | 'error' }[]
  images: { src: string; caption?: string }[]
  error: string | null
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch('/api/agent/threads' + path, { ...init, headers: headers(init.body ? { 'content-type': 'application/json' } : {}) })
  if (!res.ok) throw Object.assign(new Error(`${res.status}`), { status: res.status })
  return (await res.json()) as T
}
export const listThreads = () => api<{ threads: ThreadSummary[] }>('').then((r) => r.threads)
export const getThread = (id: string) => api<{ thread: ThreadSummary; turns: StoredTurn[] }>('/' + encodeURIComponent(id))
export const deleteThread = (id: string) => api<{ ok: boolean }>('/' + encodeURIComponent(id), { method: 'DELETE' })

const LEGACY_KEYS = ['nightowl.chat.v1', 'barnowl.chat.v1'] as const
const IMPORTED_KEY = 'nightowl.chat.imported.v1'
export type LegacyChat = { migration_key: (typeof LEGACY_KEYS)[number]; items: unknown[]; history: WireMessage[] }

/** Keep the old record until the server confirms an import. The canonical NightOwl copy wins when both exist. */
export function pendingLegacyChat(): LegacyChat | null {
  try {
    let marker: { migration_key?: string } | null = null
    try { marker = JSON.parse(localStorage.getItem(IMPORTED_KEY) || 'null') as { migration_key?: string } | null } catch { /* retry */ }
    for (const key of LEGACY_KEYS) {
      const source = localStorage.getItem(key)
      if (!source) continue
      let saved: { items?: unknown; history?: unknown }
      try { saved = JSON.parse(source) as { items?: unknown; history?: unknown } } catch { continue }
      if (!Array.isArray(saved?.items) || !saved.items.length || !Array.isArray(saved?.history)) continue
      if (marker?.migration_key === key) return null
      return { migration_key: key, items: saved.items, history: saved.history as WireMessage[] }
    }
  } catch {
    // Private mode, damaged storage, or a failed earlier migration: leave source untouched.
  }
  return null
}

export async function importLegacyChat(chat: LegacyChat): Promise<{ thread: ThreadSummary; turns: StoredTurn[] }> {
  const imported = await api<{ thread: ThreadSummary; turns: StoredTurn[] }>('/import', {
    method: 'POST', body: JSON.stringify(chat),
  })
  if (!imported?.thread?.id || !Array.isArray(imported.turns)) throw new Error('invalid imported chat response')
  try {
    localStorage.setItem(IMPORTED_KEY, JSON.stringify({ migration_key: chat.migration_key, thread_id: imported.thread.id }))
  } catch {
    // The server's migration key makes a retry safe if this marker could not be saved.
  }
  return imported
}

/** One request of an answer. A stored thread sends `text` (a new question) or `client_results` (the page's tool
 * results, to continue); the server keeps the history. */
export async function streamAgent(
  body: { thread_id: string | null; text?: string; month: string; plan_k: number; answer_id?: number; client_results?: ClientResult[]; pending_images?: { src: string }[] },
  onEvent: (e: AgentEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: headers({ 'content-type': 'application/json', accept: 'text/event-stream' }),
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = `${res.status}`
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail
    } catch {
      /* not json */
    }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let cut
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, cut)
      buf = buf.slice(cut + 2)
      for (const line of frame.split('\n')) {
        if (!line.startsWith('data:')) continue
        try {
          onEvent(JSON.parse(line.slice(5)) as AgentEvent)
        } catch {
          /* partial or keepalive */
        }
      }
    }
  }
}

// ---------------------------------------------------------------- markdown (escaped first, so model text can't inject HTML)

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

function inline(s: string): string {
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
}

export function markdown(src: string): string {
  const lines = src.replace(/\r/g, '').split('\n')
  const out: string[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('```')) {
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++])
      i++
      out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`)
      continue
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const cells = (l: string) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      const align = cells(lines[i + 1]).map((c) => (c.endsWith(':') ? ' class="num"' : ''))
      const head = cells(line).map((c, k) => `<th${align[k] ?? ''}>${inline(c)}</th>`).join('')
      i += 2
      const rows: string[] = []
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push('<tr>' + cells(lines[i]).map((c, k) => `<td${align[k] ?? ''}>${inline(c)}</td>`).join('') + '</tr>')
        i++
      }
      out.push(`<div class="md-table"><table><thead><tr>${head}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`)
      continue
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line)
    if (h) {
      out.push(`<h4>${inline(h[2])}</h4>`)
      i++
      continue
    }
    if (/^\s*([-*•]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line)
      const items: string[] = []
      while (i < lines.length && /^\s*([-*•]|\d+\.)\s+/.test(lines[i])) items.push(`<li>${inline(lines[i++].replace(/^\s*([-*•]|\d+\.)\s+/, ''))}</li>`)
      out.push(ordered ? `<ol>${items.join('')}</ol>` : `<ul>${items.join('')}</ul>`)
      continue
    }
    if (!line.trim()) {
      i++
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\s*([-*•]|\d+\.)\s+|\s*\|)/.test(lines[i])) para.push(inline(lines[i++]))
    if (para.length) out.push(`<p>${para.join('<br>')}</p>`)
    else out.push(`<p>${inline(lines[i++])}</p>`)
  }
  return out.join('')
}
