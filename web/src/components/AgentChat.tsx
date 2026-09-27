import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { deleteThread, getThread, listThreads, markdown, streamAgent, type AgentEvent, type ClientCall, type ClientResult, type StoredTurn, type ThreadSummary } from '../agent'
import { ChatIcon, CheckIcon, CloseIcon, ListIcon, NewChatIcon, SendIcon, SparkIcon, StopIcon, TrashIcon } from './Icons'

/** What the page can do for the assistant between rounds (things the server can't see). */
export interface ClientTools {
  get_app_state: () => unknown
  screenshot_map: () => string | null
  /** Map actions (fly_to, set_map_mode, show_panel, …): resolve once the animation has landed. */
  act: (name: string, args: Record<string, unknown>) => Promise<unknown>
}

interface Step {
  id: string
  label: string
  state: 'start' | 'done' | 'error'
}
interface Img {
  src: string
  caption?: string
}
type Item = { kind: 'user'; text: string } | { kind: 'bot'; text: string; steps: Step[]; images: Img[]; error?: string; busy: boolean }

const SUGGESTIONS = [
  'Where are the worst silent blocks in the city?',
  'Is the owl online? Show me what it sees.',
  'Screenshot the map and explain what I’m looking at.',
  'Where should we put the next owl in Brooklyn?',
  'Does this actually find more rats than 311 calls?',
]
// Conversations live on the server (SQLite, api/chat_store.py); the page only remembers which one is open.
const THREAD_KEY = 'nightowl.chat.thread'
const savedThread = (): string | null => {
  try {
    return localStorage.getItem(THREAD_KEY)
  } catch {
    return null
  }
}
const rememberThread = (id: string | null) => {
  try {
    if (id) localStorage.setItem(THREAD_KEY, id)
    else localStorage.removeItem(THREAD_KEY)
  } catch {
    /* private mode */
  }
}
const toItems = (turns: StoredTurn[]): Item[] =>
  turns.map((t) => (t.role === 'user' ? { kind: 'user', text: t.text } : { kind: 'bot', text: t.text, steps: t.steps, images: t.images, error: t.error ?? undefined, busy: false }))
const since = (t: number) => {
  const s = Math.max(0, Date.now() / 1000 - t)
  return s < 60 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : new Date(t * 1000).toLocaleDateString()
}

const CORNER = 150 // px from the bottom-right corner that wakes the button

function AgentChat({ tools, month, planBudget, onShown }: { tools: ClientTools; month: string; planBudget: number; onShown?: (shown: boolean) => void }) {
  const [open, setOpen] = useState(false)
  const [near, setNear] = useState(false)
  // no hover on touch screens: there the button just stays out
  const [touch] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(hover: none)').matches)
  const [items, setItems] = useState<Item[]>([])
  const threadRef = useRef<string | null>(savedThread())
  const [current, setCurrent] = useState<string | null>(savedThread) // the same id, for rendering the list
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null) // the History list, loaded when opened
  const [showList, setShowList] = useState(false)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [zoom, setZoom] = useState<Img | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const thinkSeq = useRef(0)
  const toolsRef = useRef(tools)
  useEffect(() => {
    toolsRef.current = tools
  }, [tools])

  // reopen the conversation this browser had open last
  useEffect(() => {
    const id = threadRef.current
    if (!id) return
    getThread(id)
      .then((t) => setItems((cur) => (cur.length ? cur : toItems(t.turns))))
      .catch(() => {
        threadRef.current = null // deleted, or saved under another browser
        rememberThread(null)
        setCurrent(null)
      })
  }, [])

  const refreshThreads = useCallback(() => {
    listThreads().then(setThreads).catch(() => setThreads([]))
  }, [])

  const openThread = useCallback(async (id: string) => {
    if (busy) return
    const t = await getThread(id).catch(() => null)
    setShowList(false)
    if (!t) return refreshThreads()
    threadRef.current = id
    rememberThread(id)
    setCurrent(id)
    setItems(toItems(t.turns))
  }, [busy, refreshThreads])

  const removeThread = useCallback(async (id: string) => {
    await deleteThread(id).catch(() => {})
    if (threadRef.current === id) {
      threadRef.current = null
      rememberThread(null)
      setCurrent(null)
      setItems([])
    }
    refreshThreads()
  }, [refreshThreads])

  // stick to the bottom while the answer streams
  useLayoutEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [items, open])

  useEffect(() => {
    if (!open) return
    const timer = setTimeout(() => inputRef.current?.focus(), 250)
    return () => clearTimeout(timer)
  }, [open])

  // the button hides off the right edge until the pointer comes into the bottom-right corner. A window listener
  // rather than an invisible hit area, so nothing in that corner (the Owls panel) stops taking clicks.
  useEffect(() => {
    let frame = 0
    let hideTimer: ReturnType<typeof setTimeout> | undefined
    const onMove = (e: PointerEvent) => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        const inside = e.clientX >= window.innerWidth - CORNER && e.clientY >= window.innerHeight - CORNER
        clearTimeout(hideTimer)
        if (inside) setNear(true)
        else hideTimer = setTimeout(() => setNear(false), 350) // a short grace so a wobble on the edge doesn't flicker
      })
    }
    const onLeave = () => {
      clearTimeout(hideTimer)
      hideTimer = setTimeout(() => setNear(false), 350)
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('pointerleave', onLeave)
    return () => {
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerleave', onLeave)
      cancelAnimationFrame(frame)
      clearTimeout(hideTimer)
    }
  }, [])

  // Esc closes the lightbox, then the panel
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (zoom) setZoom(null)
      else if (open && !busy) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [zoom, open, busy])

  const patchBot = useCallback((fn: (b: Extract<Item, { kind: 'bot' }>) => Extract<Item, { kind: 'bot' }>) => {
    setItems((prev) => {
      const last = prev[prev.length - 1]
      if (!last || last.kind !== 'bot') return prev
      return [...prev.slice(0, -1), fn(last)]
    })
  }, [])

  const runClientTool = useCallback(async (c: ClientCall): Promise<ClientResult> => {
    try {
      if (c.name === 'screenshot_map') {
        const src = toolsRef.current.screenshot_map()
        if (!src) return { id: c.id, content: JSON.stringify({ error: 'the map is not on screen yet' }) }
        return { id: c.id, content: JSON.stringify({ ok: true, note: 'screenshot attached below' }), image: src }
      }
      if (c.name === 'get_app_state') return { id: c.id, content: JSON.stringify(toolsRef.current.get_app_state()) }
      return { id: c.id, content: JSON.stringify(await toolsRef.current.act(c.name, c.args ?? {})) }
    } catch (e) {
      return { id: c.id, content: JSON.stringify({ error: String(e) }) }
    }
  }, [])

  const send = useCallback(
    async (text: string) => {
      const q = text.trim()
      if (!q || busy) return
      setInput('')
      setBusy(true)
      setItems((prev) => [...prev, { kind: 'user', text: q }, { kind: 'bot', text: '', steps: [], images: [], busy: true }])
      const ctl = new AbortController()
      abortRef.current = ctl
      setShowList(false)
      let body: Parameters<typeof streamAgent>[0] = { thread_id: threadRef.current, text: q, month, plan_k: planBudget }
      try {
        for (let round = 0; round < 6; round++) {
          let next: ClientCall[] = []
          let pending: Img[] = []
          await streamAgent(
            body,
            (e: AgentEvent) => {
              if (e.type === 'delta') patchBot((b) => ({ ...b, text: b.text + e.text }))
              else if (e.type === 'thinking') {
                if (e.state === 'start') {
                  const id = `think-${++thinkSeq.current}`
                  patchBot((b) => ({ ...b, steps: [...b.steps, { id, label: 'Thinking', state: 'start' }] }))
                } else {
                  const id = `think-${thinkSeq.current}`
                  patchBot((b) => ({ ...b, steps: b.steps.map((s) => (s.id === id ? { ...s, state: 'done' } : s)) }))
                }
              } else if (e.type === 'tool')
                patchBot((b) => {
                  const has = b.steps.some((s) => s.id === e.id)
                  // text before a tool call ("Let me check…") and the answer after it are separate paragraphs
                  const text = !has && b.text && !b.text.endsWith('\n\n') ? b.text + '\n\n' : b.text
                  return { ...b, text, steps: has ? b.steps.map((s) => (s.id === e.id ? { ...s, state: e.state } : s)) : [...b.steps, { id: e.id, label: e.label, state: e.state }] }
                })
              else if (e.type === 'image') patchBot((b) => ({ ...b, images: [...b.images, { src: e.src, caption: e.caption }] }))
              else if (e.type === 'client_tools') {
                next = e.calls
                pending = e.pending_images ?? []
              } else if (e.type === 'thread') {
                threadRef.current = e.id // a new conversation gets its id with the first answer
                rememberThread(e.id)
                setCurrent(e.id)
              } else if (e.type === 'error') patchBot((b) => ({ ...b, error: e.text }))
            },
            ctl.signal,
          )
          if (!next.length) break
          // run the page's tools, show what they produced, and go again
          const results: ClientResult[] = []
          patchBot((b) => (b.text && !b.text.endsWith('\n\n') ? { ...b, text: b.text + '\n\n' } : b))
          for (const c of next) {
            patchBot((b) => ({ ...b, steps: [...b.steps, { id: c.id, label: c.label, state: 'start' }] }))
            const r = await runClientTool(c)
            results.push(r)
            if (r.image) {
              const img = r.image
              patchBot((b) => ({ ...b, images: [...b.images, { src: img, caption: 'Your map view' }] }))
            }
            patchBot((b) => ({ ...b, steps: b.steps.map((s) => (s.id === c.id ? { ...s, state: r.content.includes('"error"') ? 'error' : 'done' } : s)) }))
          }
          body = { thread_id: threadRef.current, month, plan_k: planBudget, client_results: results, pending_images: pending }
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') patchBot((b) => ({ ...b, error: `Couldn’t reach the assistant (${(e as Error).message}).` }))
      } finally {
        patchBot((b) => ({ ...b, busy: false, steps: b.steps.map((s) => (s.state === 'start' ? { ...s, state: 'error' } : s)) }))
        setBusy(false)
        abortRef.current = null
      }
    },
    [busy, month, planBudget, patchBot, runClientTool],
  )

  const reset = () => {
    abortRef.current?.abort()
    threadRef.current = null // the next question starts a new saved thread
    rememberThread(null)
    setCurrent(null)
    setShowList(false)
    setItems([])
    setInput('')
    inputRef.current?.focus()
  }

  const shown = open || near || busy || touch
  useEffect(() => onShown?.(shown), [shown, onShown])

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(input)
    }
  }

  return (
    <>
      <section className={`agent panel ${open ? 'open' : ''}`} aria-hidden={!open} aria-label="NightOwl assistant">
        <header className="agent-head">
          <span className="agent-avatar">
            <SparkIcon size={16} />
          </span>
          <div className="agent-title">
            <b>NightOwl assistant</b>
            <span className="muted small">Grok · map, model and node tools</span>
          </div>
          <button
            className={`icon-btn ${showList ? 'on' : ''}`}
            title="History"
            aria-pressed={showList}
            onClick={() => {
              if (!showList) refreshThreads()
              setShowList((v) => !v)
            }}
          >
            <ListIcon size={16} />
          </button>
          <button className="icon-btn" title="New chat" onClick={reset} disabled={!items.length && !busy}>
            <NewChatIcon size={16} />
          </button>
          <button className="icon-btn" title="Close" onClick={() => setOpen(false)}>
            <CloseIcon size={16} />
          </button>
        </header>

        {showList && (
          <div className="agent-threads">
            <div className="agent-threads-head muted small">Saved chats on this browser</div>
            {threads === null ? (
              <div className="muted small">Loading…</div>
            ) : !threads.length ? (
              <div className="muted small">No saved chats yet. Ask something and it is saved here.</div>
            ) : (
              threads.map((t) => (
                <div key={t.id} className={`agent-thread ${t.id === current ? 'current' : ''}`}>
                  <button className="agent-thread-open" onClick={() => void openThread(t.id)} disabled={busy}>
                    <b>{t.title}</b>
                    <span className="muted small">
                      {since(t.updated_at)} · {t.questions} question{t.questions === 1 ? '' : 's'}
                    </span>
                  </button>
                  <button className="icon-btn" title="Delete chat" onClick={() => void removeThread(t.id)} disabled={busy && t.id === current}>
                    <TrashIcon size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        <div className="agent-body" ref={listRef}>
          {!items.length && (
            <div className="agent-hello">
              <div className="agent-hello-icon">
                <ChatIcon size={26} />
              </div>
              <b>Ask about rats, blocks and owls</b>
              <p className="muted">Ask about a block, the track record, or what you are looking at. Camera questions work when an owl is connected.</p>
              <div className="agent-suggest">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => void send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {items.map((it, k) =>
            it.kind === 'user' ? (
              <div key={k} className="msg user">
                {it.text}
              </div>
            ) : (
              <div key={k} className="msg bot">
                {it.steps.length > 0 && (
                  <ul className="steps">
                    {it.steps.map((s) => (
                      <li key={s.id} className={s.state}>
                        {s.state === 'start' ? <span className="spin" /> : s.state === 'done' ? <CheckIcon size={13} /> : <CloseIcon size={12} />}
                        {s.label}
                      </li>
                    ))}
                  </ul>
                )}
                {it.images.length > 0 && (
                  <div className="shots">
                    {it.images.map((im, j) => (
                      <button key={j} className="shot" onClick={() => setZoom(im)} title={im.caption}>
                        <img src={im.src} alt={im.caption ?? 'image'} />
                        {im.caption && <span>{im.caption}</span>}
                      </button>
                    ))}
                  </div>
                )}
                {it.text ? (
                  <div className="md" dangerouslySetInnerHTML={{ __html: markdown(it.text) }} />
                ) : (
                  it.busy && !it.steps.some((s) => s.state === 'start') && <span className="typing"><i /><i /><i /></span>
                )}
                {it.error && <div className="agent-error">{it.error}</div>}
              </div>
            ),
          )}
        </div>

        <form
          className="agent-input"
          onSubmit={(e) => {
            e.preventDefault()
            void send(input)
          }}
        >
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            placeholder="Ask about a block, a borough, an owl…"
            onChange={(e) => {
              setInput(e.target.value)
              e.target.style.height = 'auto'
              e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`
            }}
            onKeyDown={onKeyDown}
          />
          {busy ? (
            <button type="button" className="agent-send stop" title="Stop" onClick={() => abortRef.current?.abort()}>
              <StopIcon size={16} />
            </button>
          ) : (
            <button type="submit" className="agent-send" title="Send" disabled={!input.trim()}>
              <SendIcon size={16} />
            </button>
          )}
        </form>
        <div className="agent-foot muted">Answers may use model files and queued events. Check the source labels.</div>
      </section>

      <button
        className={`agent-fab panel ${open ? 'open' : ''} ${shown ? 'shown' : ''}`}
        onClick={() => setOpen((o) => !o)}
        onFocus={() => setNear(true)}
        title={open ? 'Close assistant' : 'Ask NightOwl'}
        aria-expanded={open}
      >
        <span className="fab-icon chat">
          <ChatIcon size={22} />
        </span>
        <span className="fab-icon close">
          <CloseIcon size={20} />
        </span>
      </button>

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <figure className="panel">
            <img src={zoom.src} alt={zoom.caption ?? ''} />
            {zoom.caption && <figcaption className="muted">{zoom.caption}</figcaption>}
          </figure>
        </div>
      )}
    </>
  )
}

export default memo(AgentChat)
