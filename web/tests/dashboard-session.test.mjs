import assert from 'node:assert/strict'
import test from 'node:test'
import { emptySession, forActiveRequest, forCurrentGeneration, isActiveRequest, restoreSession, STORE_KEY } from '../src/dashboard/requestSession.ts'

const artifact = (version) => ({
  id: `saved-${version}`, version, created_at: '2026-09-27T10:00:00Z',
  spec: { title: 'Saved chart', description: '', cards: [{ id: 'card', title: 'Complaints', kind: 'bar',
    query: { dataset: 'cells', aggregation: 'raw', metrics: ['complaints'] }, x: 'borough', y: ['complaints'] }] },
  results: { card: { rows: [{ borough: 'Queens', complaints: 4 }],
    columns: [{ key: 'borough', label: 'Borough', unit: '' }, { key: 'complaints', label: 'Complaints', unit: 'complaints' }],
    source: { label: 'Model', as_of: '2026-09', kind: 'model', notes: [] }, total_rows: 1,
    query: { dataset: 'cells', aggregation: 'raw', metrics: ['complaints'] } } },
})

const store = (entries) => ({ getItem: (key) => entries[key] ?? null })
const identity = (requestId, turnId, generation) => ({ requestId, turnId, generation })
const withTurn = (session, token, patch) => forActiveRequest(session, token, token.generation, (current, index) => {
  const turns = [...current.turns]
  turns[index] = { ...turns[index], ...patch }
  return { ...current, turns }
})

test('queued final stream updates apply after completion, but reset rejects late delta, error, and dashboard', () => {
  const old = identity('request-a', 'turn-a', 0)
  const pending = { ...emptySession(), turns: [{ role: 'assistant', content: '', requestId: old.requestId, turnId: old.turnId }] }
  assert.deepEqual(withTurn(pending, old, { content: 'Final answer' }).turns[0].content, 'Final answer')
  assert.equal(isActiveRequest(null, old), false)

  const cleared = emptySession()
  for (const patch of [{ content: 'late delta' }, { error: 'late error' }, { dashboard: 'old-dashboard' }]) {
    assert.equal(forActiveRequest(cleared, old, 1, (current) => ({ ...current, turns: [{ ...current.turns[0], ...patch }] })), cleared)
  }
  const next = identity('request-b', 'turn-b', 1)
  const fresh = { ...emptySession(), turns: [{ role: 'assistant', content: '', requestId: next.requestId, turnId: next.turnId }] }
  assert.equal(forActiveRequest(fresh, old, 1, () => cleared), fresh)
  assert.equal(withTurn(fresh, next, { content: 'New answer' }).turns[0].content, 'New answer')
  assert.equal(forActiveRequest(fresh, identity(next.requestId, 'wrong-turn', 1), 1, () => cleared), fresh)
})

test('v1 migration keeps the source session, selected revision, chart view, and conversation', () => {
  const old = { messages: [{ role: 'user', content: 'Compare boroughs' }, { role: 'assistant', content: 'Here is the chart' }],
    revisions: [artifact(1), { ...artifact(2), research: { summary: 'External note', sources: [{ title: 'X', url: 'https://example.com' }] } }],
    revision: 1, views: { card: { kind: 'line', hidden: [], page: 0 } },
    selection: { card_id: 'card', field: 'borough', value: 'Queens' }, research: true }
  const entries = { 'nightowl.dashboards.v1': JSON.stringify(old) }
  const restored = restoreSession(store(entries))
  assert.equal(restored.open, 'legacy-1')
  assert.equal(restored.turns[1].dashboard, 'legacy-1')
  assert.equal(restored.artifacts['legacy-1'].version, 2)
  assert.equal('research' in restored.artifacts['legacy-1'], false)
  assert.deepEqual(restored.views['legacy-1/card'], old.views.card)
  assert.deepEqual(restored.selection, old.selection)
  assert.equal(entries['nightowl.dashboards.v1'], JSON.stringify(old))
})

test('an existing v2 session takes precedence and restored turns cannot accept old stream events', () => {
  const current = { turns: [{ role: 'assistant', content: 'Saved', requestId: 'old', turnId: 'old-turn', dashboard: 'a' }],
    artifacts: { a: artifact(3) }, open: 'a', views: {}, selection: null }
  const entries = { [STORE_KEY]: JSON.stringify(current), 'nightowl.dashboards.v1': JSON.stringify({ messages: [], revisions: [artifact(1)] }) }
  const restored = restoreSession(store(entries))
  assert.equal(restored.artifacts.a.version, 3)
  assert.equal(restored.turns[0].requestId, undefined)
  assert.equal(restored.turns[0].turnId, undefined)
  assert.equal(forActiveRequest(restored, identity('old', 'old-turn', 0), 0, () => emptySession()), restored)
  assert.equal(restoreSession(store({ ...entries, [STORE_KEY]: '{bad json' })).turns.length, 0)
})

test('restored reasoning keeps its round boundaries and rejects malformed rounds', () => {
  const current = { ...emptySession(), turns: [{ role: 'assistant', content: 'Answer', thinkingRounds: [
    { round: 1, text: '### First' }, { round: 2, text: '- Second' },
    { round: '3', text: 'bad' }, { round: 4, text: { html: '<script>' } },
  ] }] }
  const restored = restoreSession(store({ [STORE_KEY]: JSON.stringify(current) }))
  assert.deepEqual(restored.turns[0].thinkingRounds, [
    { round: 1, text: '### First' }, { round: 2, text: '- Second' },
  ])
})

test('queued refresh applies after completion but cannot restore a cleared chat or aborted result', () => {
  const before = { ...emptySession(), artifacts: { a: artifact(1) }, open: 'a' }
  const update = (session) => ({ ...session, artifacts: { ...session.artifacts, a: artifact(2) } })
  assert.equal(forCurrentGeneration(before, 3, 3, false, update).artifacts.a.version, 2)
  const cleared = emptySession()
  assert.equal(forCurrentGeneration(cleared, 3, 4, false, update), cleared)
  assert.equal(forCurrentGeneration(before, 3, 3, true, update), before)
})
