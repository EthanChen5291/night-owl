import type { RatEvent, Source } from '../types'

interface Props {
  events: RatEvent[]
  source: Source
  streaming: boolean
  latestKey: string | null
  onSelect: (h3: string) => void
}

export const eventKey = (e: RatEvent) => `${e.node_id}|${e.ts}`

const fmtTs = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour12: false })
}

export default function EventFeed({ events, source, streaming, latestKey, onSelect }: Props) {
  return (
    <aside className="feed panel">
      <div className="feed-head">
        <span>Events</span>
        <span className="muted small">
          {source === 'live' ? (streaming ? 'SSE' : 'polling 2 s') : 'fixture'} · {events.length}
        </span>
      </div>
      {events.length === 0 && <div className="muted small">no events yet</div>}
      <ul>
        {events.map((e) => {
          const key = eventKey(e)
          return (
            <li key={key} className={key === latestKey ? 'fresh' : ''} onClick={() => onSelect(e.h3)} title="fly to cell">
              <div className="feed-row">
                <b>{e.node_id}</b>
                <span className="muted">{fmtTs(e.ts)}</span>
              </div>
              <div className="feed-row small">
                <code>{e.h3}</code>
                <span>
                  {e.class} {Math.round(e.conf * 100)}% · {e.n_hits} hits
                </span>
              </div>
              {e.crop_b64 && <img className="crop" alt="rat crop" src={`data:image/jpeg;base64,${e.crop_b64}`} />}
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
