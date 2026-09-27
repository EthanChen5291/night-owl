import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from 'react'
import { BackIcon, CheckIcon, ChevronIcon, CloseIcon, NewChatIcon, StopIcon } from '../components/Icons'
import ChartCard from './ChartCard'
import { refreshDashboard, streamDashboardChat } from './client'
import { downloadDashboard } from './export'
import { linkClick } from '../nav'
import { ArrowUpIcon, DashIcon, DownloadIcon, OwlMark, RefreshIcon } from './icons'
import { emptySession, forActiveRequest, forCurrentGeneration, isActiveRequest, MAX_ARTIFACTS, restoreSession, STORE_KEY, type RequestIdentity, type Turn } from './requestSession'
import { appendThinking, dashboardMarkdown } from './reasoning'
import type { DashboardArtifact } from './types'
import { resolvedKind, sortedRows, visibleSeries, type CardView } from './view'
import './dashboard.css'

const STARTERS = [
  'Compare monthly rat complaints per 100k residents in the Bronx and Manhattan since 2015.',
  'Show the 10 richest ZIP code areas and their rat complaints before and after COVID-19.',
  'Compare complaints and inspections finding rat activity across years by income band.',
  'Compare rat complaints and model likelihood by borough.',
]
const HEADLINE = 'What should we look into?'
let headlineTyped = false

/** Types the headline once per page load; later empty states and reduced-motion users get it at once. */
function TypedHeadline({ text }: { text: string }) {
  const [count, setCount] = useState(() => headlineTyped || window.matchMedia('(prefers-reduced-motion: reduce)').matches ? text.length : 0)
  const typing = count < text.length
  useEffect(() => {
    if (!typing) { headlineTyped = true; return }
    const timer = setTimeout(() => setCount((value) => Math.min(text.length, value + 1)), count === 0 ? 260 : text[count - 1] === ' ' ? 46 : 26)
    return () => clearTimeout(timer)
  }, [count, text, typing])
  return <h1 className={typing ? 'typing' : ''} aria-label={text}>
    <span className="dx-typed-ghost" aria-hidden="true">{text}</span>
    <span className="dx-typed-live" aria-hidden="true">{text.slice(0, count)}</span>
  </h1>
}

/** The artifact with each card's chosen view applied: what the assistant is shown and what exports. */
function applyViews(artifact: DashboardArtifact, key: string, views: Record<string, CardView>): DashboardArtifact {
  const view = (id: string) => views[`${key}/${id}`] ?? {}
  const cards = artifact.spec.cards.map((card) => ({ ...card, kind: resolvedKind(card, artifact.results[card.id], view(card.id)), y: visibleSeries(card, view(card.id)) }))
  const results = Object.fromEntries(Object.entries(artifact.results).map(([id, result]) => [id, { ...result, rows: sortedRows(result.rows, view(id)) }]))
  return { ...artifact, spec: { ...artifact.spec, cards }, results }
}

const when = (iso: string) => {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** A few bars from the dashboard's first numeric series: a thumbnail, not a chart. */
function Thumb({ artifact }: { artifact: DashboardArtifact }) {
  const card = artifact.spec.cards.find((c) => artifact.results[c.id]?.rows.some((row) => typeof row[c.y[0]] === 'number'))
  const values = card ? artifact.results[card.id].rows.slice(0, 7).map((row) => row[card.y[0]]).filter((v): v is number => typeof v === 'number' && Number.isFinite(v)) : []
  const max = Math.max(0, ...values.map(Math.abs))
  if (!values.length || !max) return <span className="dx-thumb icon"><DashIcon size={18} /></span>
  return <span className="dx-thumb" aria-hidden="true">{values.map((v, i) => <i key={i} style={{ height: `${Math.max(12, (Math.abs(v) / max) * 100)}%` }} />)}</span>
}

/** What the assistant did: live while it works, then folded into one line once the answer streams. */
function Trace({ turn, live, status }: { turn: Turn; live: boolean; status: string }) {
  const [expanded, setExpanded] = useState(false)
  const thinkingRef = useRef<HTMLDivElement>(null)
  const steps = turn.steps ?? []
  const rounds = turn.thinkingRounds?.length ? turn.thinkingRounds : turn.thinking ? [{ round: 1, text: turn.thinking }] : []
  const thinking = rounds.map((item) => item.text).join('').trim()
  const working = live && !turn.content && !turn.error
  // While reasoning streams, keep its newest line in view; the reader can still scroll back.
  useLayoutEffect(() => {
    const node = thinkingRef.current
    if (!node || !working) return
    node.scrollTop = node.scrollHeight
    node.classList.toggle('clipped', node.scrollTop > 0)
  }, [thinking, working])
  if (!live && !steps.length && !thinking) return null
  const open = working || expanded
  const summary = steps.length ? `${steps.length} step${steps.length === 1 ? '' : 's'}` : 'the question'
  return <div className={`dx-trace${open ? ' open' : ''}`}>
    {working
      ? <div className="dx-trace-live"><span className="dx-shimmer">{status || 'Thinking'}</span></div>
      : <button type="button" className="dx-trace-toggle" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>
        {turn.error ? <span>{turn.error === 'Stopped.' ? 'Stopped' : 'Failed'}{steps.length ? ` after ${summary}` : ''}</span>
          : live ? <span className="dx-shimmer">{status || 'Writing'}</span> : <span>Worked through {summary}</span>}
        <ChevronIcon size={13} dir={expanded ? 'down' : 'right'} />
      </button>}
    {open && (thinking || steps.length > 0) && <div className="dx-trace-body">
      {thinking && <div ref={thinkingRef} className={`dx-thinking${working ? ' tail' : ''}`} onScroll={(event) => event.currentTarget.classList.toggle('clipped', event.currentTarget.scrollTop > 0)}>
        {rounds.map((item, index) => <section className="dx-thinking-round" key={`${item.round}-${index}`}>
          <span className="dx-thinking-label">Round {item.round}</span>
          <div className="dx-thinking-content" dangerouslySetInnerHTML={{ __html: dashboardMarkdown(item.text) }} />
        </section>)}
      </div>}
      {steps.length > 0 && <ol className="dx-steps">{steps.map((step, i) => <li key={i} className={step.error ? 'error' : ''}>
        <span className="dx-step-dot">{step.error ? <CloseIcon size={10} /> : <CheckIcon size={10} />}</span>
        <span>{step.text}{step.detail && <small>{step.detail}</small>}</span>
      </li>)}</ol>}
    </div>}
  </div>
}

export default function DashboardPage() {
  const [session, setSession] = useState(() => restoreSession(localStorage))
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [notice, setNotice] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const activeRequestRef = useRef<RequestIdentity | null>(null)
  const generationRef = useRef(0)
  const threadRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const openKey = session.open
  const artifact = openKey ? session.artifacts[openKey] ?? null : null

  useEffect(() => {
    const timer = setTimeout(() => {
      try { localStorage.setItem(STORE_KEY, JSON.stringify(session)) } catch { /* storage may be full or disabled */ }
    }, 400)
    return () => clearTimeout(timer)
  }, [session])

  // Follow the stream while the reader is at the bottom; leave them alone once they scroll up.
  useLayoutEffect(() => {
    const node = threadRef.current
    if (node && stickRef.current) node.scrollTop = node.scrollHeight
  }, [session.turns, status])

  useLayoutEffect(() => {
    const node = inputRef.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`
  }, [draft])

  useEffect(() => () => { generationRef.current++; activeRequestRef.current = null; abortRef.current?.abort() }, [])

  const displayed = useMemo(() => artifact && openKey ? applyViews(artifact, openKey, session.views) : null, [artifact, openKey, session.views])

  const patchTurn = (identity: RequestIdentity, update: (turn: Turn) => Turn) => setSession((previous) =>
    forActiveRequest(previous, identity, generationRef.current, (current, index) => {
      const turns = [...current.turns]
      turns[index] = update(turns[index])
      return { ...current, turns }
    }))

  /** Attaches a new revision to the streaming turn and opens it, forgetting the oldest beyond MAX_ARTIFACTS. */
  const addArtifact = (next: DashboardArtifact, identity: RequestIdentity) => {
    const key = `d${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
    const { id, version, created_at, spec, results } = next
    setSession((previous) => forActiveRequest(previous, identity, generationRef.current, (current, index) => {
      const artifacts = { ...current.artifacts, [key]: { id, version, created_at, spec, results } }
      const keys = Object.keys(artifacts)
      for (const stale of keys.slice(0, Math.max(0, keys.length - MAX_ARTIFACTS))) delete artifacts[stale]
      const turns = [...current.turns]
      turns[index] = { ...turns[index], dashboard: key }
      return {
        ...current, artifacts, open: key, selection: null,
        turns: turns.map((turn) => turn.dashboard && !artifacts[turn.dashboard] ? { ...turn, dashboard: undefined } : turn),
        views: Object.fromEntries(Object.entries(current.views).filter(([view]) => artifacts[view.split('/')[0]])),
      }
    }))
  }

  const send = async (prompt: string) => {
    const message = prompt.trim()
    if (!message || busy || activeRequestRef.current) return
    const identity: RequestIdentity = { requestId: crypto.randomUUID(), turnId: crypto.randomUUID(), generation: generationRef.current }
    const controller = new AbortController()
    activeRequestRef.current = identity
    abortRef.current = controller
    setDraft('')
    setNotice('')
    setStatus('Thinking')
    setBusy(true)
    stickRef.current = true
    const history = session.turns.filter((turn) => turn.content.trim()).slice(-12).map(({ role, content }) => ({ role, content }))
    const version = Math.min(1000, Math.max(0, ...Object.values(session.artifacts).map((a) => a.version)) + 1)
    setSession((previous) => ({ ...previous, turns: [...previous.turns, { role: 'user', content: message }, { role: 'assistant', content: '', steps: [], requestId: identity.requestId, turnId: identity.turnId }] }))
    try {
      await streamDashboardChat({ message, history, dashboard: displayed?.spec, selection: session.selection ?? undefined, version }, (event) => {
        if (!isActiveRequest(activeRequestRef.current, identity)) return
        if (event.type === 'status') setStatus(event.text)
        else if (event.type === 'step') patchTurn(identity, (turn) => ({ ...turn, steps: [...(turn.steps ?? []), { text: event.text, detail: event.detail, error: event.error }] }))
        else if (event.type === 'thinking') patchTurn(identity, (turn) => ({ ...turn,
          thinkingRounds: appendThinking(turn.thinkingRounds ?? (turn.thinking ? [{ round: 1, text: turn.thinking }] : []), event.text, event.round),
          thinking: undefined,
        }))
        else if (event.type === 'delta') { setStatus('Writing'); patchTurn(identity, (turn) => ({ ...turn, content: turn.content + event.text })) }
        else if (event.type === 'dashboard') addArtifact(event.dashboard, identity)
        else if (event.type === 'error') patchTurn(identity, (turn) => ({ ...turn, error: event.text }))
      }, controller.signal)
    } catch (cause) {
      patchTurn(identity, (turn) => ({ ...turn, error: controller.signal.aborted ? 'Stopped.' : cause instanceof Error ? cause.message : 'The request failed.' }))
    } finally {
      if (isActiveRequest(activeRequestRef.current, identity)) {
        activeRequestRef.current = null
        if (abortRef.current === controller) abortRef.current = null
        setBusy(false)
        setStatus('')
      }
    }
  }

  /** Re-runs the open dashboard's queries in place; its chart views carry over. */
  const refresh = async () => {
    if (!artifact || !openKey || busy) return
    const controller = new AbortController()
    const generation = generationRef.current
    abortRef.current = controller
    setBusy(true)
    setNotice('')
    setStatus('Refreshing')
    try {
      const { id, version, created_at, spec, results } = await refreshDashboard(artifact, controller.signal)
      setSession((previous) => forCurrentGeneration(previous, generation, generationRef.current, controller.signal.aborted,
        (current) => current.artifacts[openKey]
          ? { ...current, artifacts: { ...current.artifacts, [openKey]: { id, version, created_at, spec, results } } } : current))
    } catch (cause) {
      if (generationRef.current === generation && !controller.signal.aborted) setNotice(cause instanceof Error ? cause.message : 'Refresh failed.')
    } finally {
      if (abortRef.current === controller) { abortRef.current = null; setBusy(false); setStatus('') }
    }
  }

  const submit = (event: FormEvent) => { event.preventDefault(); void send(draft) }
  const onPromptKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(draft) }
  }
  const setView = (id: string, view: CardView) => setSession((previous) => ({ ...previous, views: { ...previous.views, [`${openKey}/${id}`]: view } }))
  const openArtifact = (key: string | null) => setSession((previous) => ({ ...previous, open: key, selection: previous.open === key ? previous.selection : null }))
  const newChat = () => {
    generationRef.current++
    activeRequestRef.current = null
    abortRef.current?.abort()
    abortRef.current = null
    setBusy(false)
    setStatus('')
    setSession(emptySession())
    setDraft('')
    setNotice('')
    inputRef.current?.focus()
  }

  const building = busy && status === 'Building dashboard'
  const canvas = !!artifact || building
  const empty = session.turns.length === 0
  const selectedCard = session.selection && artifact?.spec.cards.find((card) => card.id === session.selection?.card_id)
  const lastIndex = session.turns.length - 1

  const composer = <form className="dx-composer" onSubmit={submit}>
    {session.selection && <div className="dx-context">
      <span className="dx-context-label">Selected</span>
      <b>{String(session.selection.value)}</b>
      {selectedCard && <span className="dx-context-src">in {selectedCard.title}</span>}
      <button type="button" onClick={() => setSession((previous) => ({ ...previous, selection: null }))} aria-label="Clear chart selection"><CloseIcon size={12} /></button>
    </div>}
    <div className="dx-input">
      <textarea ref={inputRef} aria-label="Ask about the data" rows={1} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={onPromptKey}
        placeholder={session.selection ? `Ask about ${session.selection.value}…` : artifact ? 'Refine this dashboard…' : 'Ask about rats, inspections, or cameras…'} autoFocus={!empty} />
      {busy
        ? <button type="button" className="dx-send stop" onClick={() => abortRef.current?.abort()} aria-label="Stop"><StopIcon size={14} /></button>
        : <button type="submit" className="dx-send" disabled={!draft.trim()} aria-label="Send"><ArrowUpIcon size={17} /></button>}
    </div>
  </form>

  return <div className={`dx${canvas ? ' has-canvas' : ''}${empty ? ' is-empty' : ''}`}>
    <section className="dx-chat" aria-label="Conversation">
      <header className="dx-bar">
        <a className="dx-pill" href="/" title="Back to the map" onClick={linkClick('/')}><BackIcon size={15} /><span>Map</span></a>
        <div className="dx-brand"><OwlMark size={20} /><b>Night Owl</b><span>Explore</span></div>
        {empty ? <span className="dx-bar-spacer" /> : <button type="button" className="dx-icon-btn" onClick={newChat} title="New chat" aria-label="New chat"><NewChatIcon size={17} /></button>}
      </header>

      {empty ? <div className="dx-hero">
        <div className="dx-hero-mark" aria-hidden="true"><OwlMark size={34} /></div>
        <TypedHeadline text={HEADLINE} />
        {composer}
        <div className="dx-starters">{STARTERS.map((prompt, i) => <button key={prompt} type="button" style={{ '--i': i } as CSSProperties} onClick={() => void send(prompt)}>
          {prompt}
        </button>)}</div>
      </div> : <>
        <div className="dx-thread" ref={threadRef} onScroll={(event) => { const node = event.currentTarget; stickRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80 }}>
          <div className="dx-thread-inner" aria-live="polite">
            {session.turns.map((turn, index) => {
              if (turn.role === 'user') return <div className="dx-turn user" key={index}><p>{turn.content}</p></div>
              const live = busy && index === lastIndex
              const built = turn.dashboard ? session.artifacts[turn.dashboard] : undefined
              const isOpen = !!turn.dashboard && turn.dashboard === openKey
              return <div className="dx-turn assistant" key={index}>
                <div className={`dx-avatar${live ? ' live' : ''}`}><OwlMark size={19} /></div>
                <div className="dx-turn-body">
                  <Trace turn={turn} live={live} status={status} />
                  {built && <button type="button" className={`dx-artifact${isOpen ? ' open' : ''}`} onClick={() => openArtifact(isOpen ? null : turn.dashboard!)} aria-pressed={isOpen}>
                    <Thumb artifact={built} />
                    <span className="dx-artifact-text"><b>{built.spec.title}</b>
                      <small>{built.spec.cards.length} chart{built.spec.cards.length === 1 ? '' : 's'} · version {built.version}</small></span>
                    <span className="dx-artifact-cta">{isOpen ? 'Viewing' : 'Open'}</span>
                  </button>}
                  {turn.content && <div className={`dx-prose${live ? ' streaming' : ''}`} dangerouslySetInnerHTML={{ __html: dashboardMarkdown(turn.content) }} />}
                  {turn.error && <div className="dx-error" role="alert">{turn.error}</div>}
                </div>
              </div>
            })}
          </div>
        </div>
        <div className="dx-dock">{composer}<p className="dx-fineprint">Night Owl answers only from its own model and event data. Each chart names its source.</p></div>
      </>}
    </section>

    {canvas && <section className="dx-canvas" aria-label="Dashboard">
      <div className="dx-canvas-scroll">
        {artifact && displayed ? <>
          <header className="dx-canvas-head">
            <div className="dx-canvas-title">
              <h2>{artifact.spec.title}</h2>
              {artifact.spec.description && <p>{artifact.spec.description}</p>}
              <span className="dx-meta">Version {artifact.version} · {when(artifact.created_at)}</span>
            </div>
            <div className="dx-tools">
              <button type="button" className="dx-icon-btn" onClick={() => void refresh()} disabled={busy} title="Refresh data" aria-label="Refresh data"><RefreshIcon size={16} className={status === 'Refreshing' ? 'dx-spin' : undefined} /></button>
              <button type="button" className="dx-icon-btn" onClick={() => downloadDashboard(displayed)} title="Download HTML" aria-label="Download HTML"><DownloadIcon size={16} /></button>
              <button type="button" className="dx-icon-btn" onClick={() => openArtifact(null)} title="Close dashboard" aria-label="Close dashboard"><CloseIcon size={16} /></button>
            </div>
          </header>
          {notice && <div className="dx-error" role="alert">{notice}</div>}
          {building && <div className="dx-rebuild"><span className="dx-shimmer">Building the next version</span></div>}
          <div className={`dx-grid${building ? ' stale' : ''}`} key={`${openKey}:${artifact.created_at}`}>
            {artifact.spec.cards.map((card, index) => <ChartCard key={card.id} card={card} index={index} result={artifact.results[card.id]}
              view={session.views[`${openKey}/${card.id}`] ?? {}} selection={session.selection} onView={(view) => setView(card.id, view)}
              onSelect={(selection) => setSession((previous) => ({ ...previous, selection }))} />)}
          </div>
        </> : <div className="dx-skeleton" role="status" aria-label="Building dashboard">
          <div className="dx-skel-head"><i /><i /></div>
          <div className="dx-grid">{[0, 1, 2, 3].map((i) => <div key={i} className="dx-card skel" style={{ '--i': i } as CSSProperties}><i /><i /><div /></div>)}</div>
        </div>}
      </div>
    </section>}
  </div>
}
