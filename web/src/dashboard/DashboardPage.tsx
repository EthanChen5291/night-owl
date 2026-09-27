import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { markdown } from '../agent'
import ChartCard from './ChartCard'
import { fetchCatalog, renderDashboard, streamDashboardChat } from './client'
import { downloadDashboard } from './export'
import type { ChatMessage, ChartSelection, DashboardArtifact } from './types'
import { resolvedKind, sortedRows, visibleSeries, type CardView } from './view'
import './dashboard.css'

interface Catalog {
  datasets: Record<string, { label: string; notes: string[] }>
  max_cards: number
}

interface Session {
  messages: ChatMessage[]
  revisions: DashboardArtifact[]
  revision: number
  views: Record<string, CardView>
  selection: ChartSelection | null
}

const STORE_KEY = 'nightowl.dashboards.v1'
const STARTERS = [
  'Compare rat complaints and model likelihood by borough.',
  'Show how inspection results changed over time.',
  'Where have recent rat camera events been reported?',
]
const emptySession: Session = { messages: [], revisions: [], revision: -1, views: {}, selection: null }

const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === 'string')
const validQuery = (value: unknown) => record(value) && ['cells', 'backtest', 'events', 'sites'].includes(String(value.dataset))
  && ['mean', 'sum', 'count', 'raw'].includes(String(value.aggregation)) && strings(value.metrics)

function validArtifact(value: unknown): value is DashboardArtifact {
  if (!record(value) || typeof value.id !== 'string' || !Number.isInteger(value.version) || typeof value.created_at !== 'string'
    || !record(value.spec) || typeof value.spec.title !== 'string' || typeof value.spec.description !== 'string'
    || !Array.isArray(value.spec.cards) || !record(value.results)) return false
  if (!value.spec.cards.every((card: unknown) => record(card) && typeof card.id === 'string'
    && typeof card.title === 'string' && ['bar', 'line', 'scatter', 'table', 'metric'].includes(String(card.kind))
    && validQuery(card.query) && typeof card.x === 'string' && strings(card.y))) return false
  if (!Object.values(value.results).every((result) => record(result) && validQuery(result.query)
    && Array.isArray(result.rows) && result.rows.every((row: unknown) => record(row)
      && Object.values(row).every((cell) => cell === null || typeof cell === 'string' || typeof cell === 'number'))
    && Array.isArray(result.columns) && result.columns.every((column: unknown) => record(column)
      && typeof column.key === 'string' && typeof column.label === 'string' && typeof column.unit === 'string')
    && record(result.source) && typeof result.source.label === 'string' && typeof result.source.as_of === 'string'
    && ['model', 'events', 'fixture'].includes(String(result.source.kind)) && strings(result.source.notes)
    && typeof result.total_rows === 'number')) return false
  return true
}

function loadSession(): Session {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(STORE_KEY) || 'null')
    if (!record(saved) || !Array.isArray(saved.messages) || !Array.isArray(saved.revisions)) return emptySession
    const selected = saved.revisions[Number.isInteger(saved.revision) ? saved.revision as number : saved.revisions.length - 1]
    const restored = saved.revisions.filter(validArtifact).slice(-6)
    const selectedIndex = restored.indexOf(selected)
    const revisions = restored.map(({ id, version, created_at, spec, results }) => ({ id, version, created_at, spec, results }))
    const views = record(saved.views) ? Object.fromEntries(Object.entries(saved.views).filter(([, view]) => record(view)
      && (view.kind === undefined || ['bar', 'line', 'scatter', 'table', 'metric'].includes(String(view.kind)))
      && (view.hidden === undefined || strings(view.hidden))
      && (view.sortBy === undefined || typeof view.sortBy === 'string')
      && (view.sortDirection === undefined || view.sortDirection === 'asc' || view.sortDirection === 'desc')
      && (view.page === undefined || (Number.isInteger(view.page) && (view.page as number) >= 0)))) as Record<string, CardView> : {}
    const selection = record(saved.selection) && typeof saved.selection.card_id === 'string'
      && typeof saved.selection.field === 'string' && (typeof saved.selection.value === 'string' || typeof saved.selection.value === 'number')
      ? saved.selection as unknown as ChartSelection : null
    return {
      messages: saved.messages.filter((message): message is ChatMessage => record(message)
        && (message.role === 'user' || message.role === 'assistant') && typeof message.content === 'string').slice(-40),
      revisions,
      revision: revisions.length ? (selectedIndex >= 0 ? selectedIndex : revisions.length - 1) : -1,
      views,
      selection,
    }
  } catch {
    return emptySession
  }
}

function dashboardMarkdown(content: string): string {
  const withoutLinks = content.replace(/\[([^\]]+)\]\(https?:\/\/[^\s)]+\)/g, '$1').replace(/https?:\/\/[^\s<)]+/g, '')
  return markdown(withoutLinks).replace(/<a\b[^>]*>([\s\S]*?)<\/a>/gi, '$1')
}

export default function DashboardPage() {
  const [session, setSession] = useState(loadSession)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [catalogError, setCatalogError] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const threadRef = useRef<HTMLDivElement>(null)
  const artifact = session.revisions[session.revision] ?? null

  useEffect(() => {
    const controller = new AbortController()
    void fetchCatalog(controller.signal).then((data) => {
      if (record(data) && record(data.datasets)) { setCatalog(data as unknown as Catalog); setCatalogError(false) }
      else setCatalogError(true)
    }, () => { if (!controller.signal.aborted) setCatalogError(true) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      try { localStorage.setItem(STORE_KEY, JSON.stringify(session)) } catch { /* storage may be full or disabled */ }
    }, 400)
    return () => clearTimeout(timer)
  }, [session])

  useEffect(() => {
    const node = threadRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [session.messages, status])

  useEffect(() => () => abortRef.current?.abort(), [])

  const displayedArtifact = useMemo((): DashboardArtifact | null => {
    if (!artifact) return null
    const cards = artifact.spec.cards.map((card) => {
      const view = session.views[card.id] ?? {}
      return { ...card, kind: resolvedKind(card, artifact.results[card.id], view), y: visibleSeries(card, view) }
    })
    const results = Object.fromEntries(Object.entries(artifact.results).map(([id, result]) => [id, { ...result, rows: sortedRows(result.rows, session.views[id] ?? {}) }]))
    return { ...artifact, spec: { ...artifact.spec, cards }, results }
  }, [artifact, session.views])

  const addArtifact = (next: DashboardArtifact) => setSession((previous) => {
    const { id, version, created_at, spec, results } = next
    const artifact = { id, version, created_at, spec, results }
    const revisions = [...previous.revisions.slice(0, previous.revision + 1), artifact].slice(-6)
    const revision = revisions.length - 1
    return { ...previous, revisions, revision, views: {}, selection: null }
  })

  const send = async (prompt: string) => {
    const message = prompt.trim()
    if (!message || busy) return
    setDraft('')
    setError('')
    setStatus('Starting…')
    setBusy(true)
    const history = session.messages.filter((entry) => entry.content.trim()).slice(-12)
    setSession((previous) => ({ ...previous, messages: [...previous.messages, { role: 'user', content: message }, { role: 'assistant', content: '' }] }))
    const controller = new AbortController()
    abortRef.current = controller
    let answer = ''
    try {
      await streamDashboardChat({
        message, history, dashboard: displayedArtifact?.spec, selection: session.selection ?? undefined,
        version: (artifact?.version ?? 0) + 1,
      }, (event) => {
        if (event.type === 'status') setStatus(event.text)
        if (event.type === 'delta') {
          answer += event.text
          setSession((previous) => ({ ...previous, messages: [...previous.messages.slice(0, -1), { role: 'assistant', content: answer }] }))
        }
        if (event.type === 'dashboard') addArtifact(event.dashboard)
        if (event.type === 'error') setError(event.text)
      }, controller.signal)
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'The request failed.')
    } finally {
      if (!answer) setSession((previous) => ({ ...previous, messages: previous.messages.slice(0, -1) }))
      if (abortRef.current === controller) abortRef.current = null
      setBusy(false)
      setStatus('')
    }
  }

  const refresh = async () => {
    if (!artifact || busy) return
    const controller = new AbortController()
    abortRef.current = controller
    setBusy(true)
    setError('')
    setStatus('Refreshing from current data…')
    try {
      const next = await renderDashboard(displayedArtifact?.spec ?? artifact.spec, artifact.version + 1, controller.signal)
      addArtifact(next)
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Refresh failed.')
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setBusy(false)
      setStatus('')
    }
  }

  const submit = (event: FormEvent) => { event.preventDefault(); void send(draft) }
  const onPromptKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send(draft) }
  }
  const setView = (id: string, view: CardView) => setSession((previous) => ({ ...previous, views: { ...previous.views, [id]: view } }))
  const select = (selection: ChartSelection) => setSession((previous) => ({ ...previous, selection }))

  return <div className="dash-page">
    <header className="dash-topbar">
      <div className="dash-brand"><span className="dash-mark" aria-hidden="true">◉</span><div><strong>Night Owl</strong><span>Data explorer</span></div></div>
      <nav aria-label="Primary"><a href="/">Map</a><span aria-current="page">Dashboards</span></nav>
    </header>

    <div className="dash-layout">
      <section className="dash-conversation" aria-label="Dashboard conversation">
        <div className="dash-conversation-head"><div><span className="dash-eyebrow">Explore the data</span><h1>Ask Night Owl</h1><p>Ask a question, then choose a bar, point, or row to refine it.</p></div></div>
        <div className="dash-thread" ref={threadRef} aria-live="polite">
          {session.messages.length === 0 && <div className="dash-starters"><p>Try one of these questions</p>{STARTERS.map((starter) => <button key={starter} type="button" onClick={() => void send(starter)} disabled={busy}>{starter}<span aria-hidden="true">↗</span></button>)}</div>}
          {session.messages.map((message, index) => message.content && <div className={`dash-message ${message.role}`} key={index}><span>{message.role === 'user' ? 'You' : 'Night Owl'}</span>{message.role === 'assistant' ? <div className="dash-prose" dangerouslySetInnerHTML={{ __html: dashboardMarkdown(message.content) }} /> : <p>{message.content}</p>}</div>)}
          {busy && <div className="dash-progress" role="status"><span className="dash-spinner" />{status || 'Working…'}</div>}
          {error && <div className="dash-error" role="alert">{error}</div>}
        </div>
        <form className="dash-compose" onSubmit={submit}>
          {session.selection && <div className="dash-selection"><span>Selected <b>{session.selection.value}</b> in {artifact?.spec.cards.find((card) => card.id === session.selection?.card_id)?.title ?? session.selection.card_id}</span><button type="button" onClick={() => setSession((previous) => ({ ...previous, selection: null }))} aria-label="Clear chart selection">×</button></div>}
          <div className="dash-compose-row"><textarea aria-label="Ask about the data" placeholder="Ask a question or refine this dashboard…" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={onPromptKey} rows={3} disabled={busy} /><button type={busy ? 'button' : 'submit'} onClick={busy ? () => abortRef.current?.abort() : undefined} disabled={!busy && !draft.trim()}>{busy ? 'Stop' : 'Send'}</button></div>
          <span className="dash-compose-hint">Enter to send · Shift+Enter for a new line</span>
        </form>
      </section>

      <main className="dash-workspace">
        <div className="dash-workspace-head"><div><span className="dash-eyebrow">Your dashboard</span><h2>{artifact?.spec.title ?? 'Your dashboard'}</h2><p>{artifact?.spec.description ?? 'Your charts will appear here after your first question.'}</p></div>
          {artifact && <div className="dash-actions">
            <div className="dash-revisions" aria-label="Dashboard revisions"><button type="button" onClick={() => setSession((previous) => ({ ...previous, revision: previous.revision - 1, views: {}, selection: null }))} disabled={busy || session.revision <= 0} aria-label="Previous revision">←</button><span>Revision {session.revision + 1} of {session.revisions.length}</span><button type="button" onClick={() => setSession((previous) => ({ ...previous, revision: previous.revision + 1, views: {}, selection: null }))} disabled={busy || session.revision >= session.revisions.length - 1} aria-label="Next revision">→</button></div>
            <button type="button" onClick={() => void refresh()} disabled={busy}>Refresh data</button>
            <button type="button" className="dash-export" onClick={() => displayedArtifact && downloadDashboard(displayedArtifact)} disabled={!displayedArtifact}>Download HTML</button>
          </div>}
        </div>

        {!artifact && <div className="dash-welcome"><div className="dash-welcome-graphic" aria-hidden="true"><span /><span /><span /><span /></div><h3>Start with a question</h3><p>Night Owl will build charts from available model, inspection, and camera data. Each card shows its source and date.</p>{catalog && <div className="dash-datasets">{Object.values(catalog.datasets).map((dataset) => <span key={dataset.label}>{dataset.label}</span>)}</div>}{catalogError && <p className="dash-catalog-error">The data catalog is unavailable. You can still try a question.</p>}</div>}
        {artifact && <div className="dash-content">
          <div className="dash-artifact-meta"><span>Updated {artifact.created_at}</span><span>Version {artifact.version}</span></div>
          <div className="dash-cards">{artifact.spec.cards.map((card) => <ChartCard key={card.id} card={card} result={artifact.results[card.id]} view={session.views[card.id] ?? {}} selection={session.selection} onView={(view) => setView(card.id, view)} onSelect={select} />)}</div>
        </div>}
      </main>
    </div>
  </div>
}
