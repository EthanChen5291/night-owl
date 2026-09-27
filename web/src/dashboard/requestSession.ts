import type { AgentStep, ChartSelection, DashboardArtifact } from './types'
import type { CardView } from './view'

export interface Turn {
  role: 'user' | 'assistant'
  content: string
  requestId?: string
  turnId?: string
  steps?: AgentStep[]
  thinking?: string
  dashboard?: string
  error?: string
}

export interface Session {
  turns: Turn[]
  artifacts: Record<string, DashboardArtifact>
  open: string | null
  views: Record<string, CardView>
  selection: ChartSelection | null
}

export interface RequestIdentity { requestId: string; turnId: string; generation: number }

export const STORE_KEY = 'nightowl.dashboards.v2'
export const MAX_ARTIFACTS = 8
export const emptySession = (): Session => ({ turns: [], artifacts: {}, open: null, views: {}, selection: null })

export function isActiveRequest(active: RequestIdentity | null, expected: RequestIdentity): boolean {
  return active?.requestId === expected.requestId && active.turnId === expected.turnId && active.generation === expected.generation
}

export function forActiveRequest<T extends { turns: { requestId?: string; turnId?: string }[] }>(
  session: T, expected: RequestIdentity, generation: number, update: (session: T, turnIndex: number) => T,
): T {
  if (expected.generation !== generation) return session
  const index = session.turns.findIndex((turn) => turn.requestId === expected.requestId && turn.turnId === expected.turnId)
  return index < 0 ? session : update(session, index)
}

export function forCurrentGeneration<T>(state: T, expected: number, current: number, aborted: boolean, update: (state: T) => T): T {
  return expected === current && !aborted ? update(state) : state
}

const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === 'string')
const KINDS = ['bar', 'line', 'scatter', 'table', 'metric']
const validQuery = (value: unknown) => record(value) && typeof value.dataset === 'string' && value.dataset.length > 0
  && ['mean', 'sum', 'count', 'raw'].includes(String(value.aggregation)) && strings(value.metrics)

function validArtifact(value: unknown): value is DashboardArtifact {
  if (!record(value) || typeof value.id !== 'string' || !Number.isInteger(value.version) || typeof value.created_at !== 'string'
    || !record(value.spec) || typeof value.spec.title !== 'string' || typeof value.spec.description !== 'string'
    || !Array.isArray(value.spec.cards) || !record(value.results)) return false
  if (!value.spec.cards.every((card: unknown) => record(card) && typeof card.id === 'string'
    && typeof card.title === 'string' && KINDS.includes(String(card.kind))
    && validQuery(card.query) && typeof card.x === 'string' && strings(card.y)
    && (card.description === undefined || typeof card.description === 'string'))) return false
  return Object.values(value.results).every((result) => record(result) && validQuery(result.query)
    && Array.isArray(result.rows) && result.rows.every((row: unknown) => record(row)
      && Object.values(row).every((cell) => cell === null || typeof cell === 'string' || typeof cell === 'number'))
    && Array.isArray(result.columns) && result.columns.every((column: unknown) => record(column)
      && typeof column.key === 'string' && typeof column.label === 'string' && typeof column.unit === 'string')
    && record(result.source) && typeof result.source.label === 'string' && typeof result.source.as_of === 'string'
    && ['model', 'events', 'fixture', 'history'].includes(String(result.source.kind)) && strings(result.source.notes)
    && typeof result.total_rows === 'number')
}

const validView = (view: unknown): view is CardView => record(view)
  && (view.kind === undefined || KINDS.includes(String(view.kind)))
  && (view.hidden === undefined || strings(view.hidden))
  && (view.sortBy === undefined || typeof view.sortBy === 'string')
  && (view.sortDirection === undefined || view.sortDirection === 'asc' || view.sortDirection === 'desc')
  && (view.page === undefined || (Number.isInteger(view.page) && (view.page as number) >= 0))
const validSelection = (value: unknown): value is ChartSelection => record(value)
  && typeof value.card_id === 'string' && typeof value.field === 'string'
  && (typeof value.value === 'string' || typeof value.value === 'number')
const cleanArtifact = ({ id, version, created_at, spec, results }: DashboardArtifact): DashboardArtifact => ({ id, version, created_at, spec, results })

function parseCurrent(saved: unknown): Session {
  if (!record(saved) || !Array.isArray(saved.turns) || !record(saved.artifacts)) return emptySession()
  const artifacts: Record<string, DashboardArtifact> = {}
  for (const [key, value] of Object.entries(saved.artifacts).slice(-MAX_ARTIFACTS)) {
    if (validArtifact(value)) artifacts[key] = cleanArtifact(value)
  }
  const turns: Turn[] = saved.turns.filter((turn): turn is Turn => record(turn)
    && (turn.role === 'user' || turn.role === 'assistant') && typeof turn.content === 'string').slice(-40).map((turn) => ({
    role: turn.role, content: turn.content,
    steps: Array.isArray(turn.steps) ? turn.steps.filter((step): step is AgentStep => record(step) && typeof step.text === 'string')
      .map((step) => ({ text: step.text, detail: typeof step.detail === 'string' ? step.detail : undefined, error: step.error === true })) : undefined,
    thinking: typeof turn.thinking === 'string' ? turn.thinking : undefined,
    dashboard: typeof turn.dashboard === 'string' && artifacts[turn.dashboard] ? turn.dashboard : undefined,
    error: typeof turn.error === 'string' ? turn.error : undefined,
  }))
  const open = typeof saved.open === 'string' && artifacts[saved.open] ? saved.open : null
  const views = record(saved.views) ? Object.fromEntries(Object.entries(saved.views).filter(([key, view]) =>
    artifacts[key.split('/')[0]] && validView(view))) as Record<string, CardView> : {}
  return { turns, artifacts, open, views, selection: open && validSelection(saved.selection) ? saved.selection : null }
}

function migrateLegacy(saved: unknown): Session {
  if (!record(saved) || !Array.isArray(saved.messages) || !Array.isArray(saved.revisions)) return emptySession()
  const turns: Turn[] = saved.messages.filter((message): message is Turn => record(message)
    && (message.role === 'user' || message.role === 'assistant') && typeof message.content === 'string')
    .slice(-40).map(({ role, content }) => ({ role, content }))
  const artifacts: Record<string, DashboardArtifact> = {}
  const retained = saved.revisions.map((value, index) => ({ value, index })).filter(({ value }) => validArtifact(value)).slice(-MAX_ARTIFACTS)
  const assistantIndices = turns.map((turn, index) => turn.role === 'assistant' ? index : -1).filter((index) => index >= 0)
  for (const [position, { value, index }] of retained.entries()) {
    if (!validArtifact(value)) continue
    const key = `legacy-${index}`
    artifacts[key] = cleanArtifact(value)
    const assistantIndex = assistantIndices[assistantIndices.length - retained.length + position]
    if (assistantIndex === undefined) turns.push({ role: 'assistant', content: '', dashboard: key })
    else turns[assistantIndex].dashboard = key
  }
  const selected = retained.find(({ index }) => index === saved.revision)
  const open = selected ? `legacy-${selected.index}` : retained.length ? `legacy-${retained[retained.length - 1].index}` : null
  const views = record(saved.views) && open ? Object.fromEntries(Object.entries(saved.views).filter(([, view]) => validView(view))
    .map(([cardId, view]) => [`${open}/${cardId}`, view])) as Record<string, CardView> : {}
  return { turns: turns.slice(-40), artifacts, open, views, selection: open && validSelection(saved.selection) ? saved.selection : null }
}

export function restoreSession(storage: { getItem(key: string): string | null }): Session {
  try {
    const current = storage.getItem(STORE_KEY)
    if (current !== null) return parseCurrent(JSON.parse(current) as unknown)
    const legacy = storage.getItem('nightowl.dashboards.v1')
    return legacy === null ? emptySession() : migrateLegacy(JSON.parse(legacy) as unknown)
  } catch {
    return emptySession()
  }
}
