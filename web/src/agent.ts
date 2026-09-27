// Assistant chat streams responses from POST /api/agent/chat using Server-Sent Events.
// The browser keeps the history and runs the "client tools" (things only the page knows) between rounds.

export type AgentEvent =
  | { type: 'tool'; id: string; name: string; label: string; state: 'start' | 'done' | 'error' }
  | { type: 'image'; src: string; caption?: string }
  | { type: 'thinking'; state: 'start' | 'done' }
  | { type: 'delta'; text: string }
  | { type: 'client_tools'; calls: ClientCall[]; pending_images: { src: string; caption?: string }[] }
  | { type: 'messages'; messages: WireMessage[] }
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

export async function streamAgent(
  body: { messages: WireMessage[]; month: string; plan_k: number; client_results?: ClientResult[]; pending_images?: { src: string }[] },
  onEvent: (e: AgentEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch('/api/agent/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
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
