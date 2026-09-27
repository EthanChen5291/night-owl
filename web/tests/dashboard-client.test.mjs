import assert from 'node:assert/strict'
import test from 'node:test'
import { refreshDashboard, streamDashboardChat } from '../src/dashboard/client.ts'
import { visibleSeries } from '../src/dashboard/view.ts'

test('dashboard chat reads fragmented SSE frames and sends selection context', async () => {
  const previousFetch = globalThis.fetch
  const encoder = new TextEncoder()
  let sent
  globalThis.fetch = async (_url, options) => {
    sent = JSON.parse(options.body)
    const chunks = [
      'data: {"type":"status","text":"Working"}\r',
      '\n\r\ndata: {"type":"delta","text":"Done"}\n\n',
      'data: {"type":"done"}\n\n',
    ]
    return new Response(new ReadableStream({ start(controller) { for (const chunk of chunks) controller.enqueue(encoder.encode(chunk)); controller.close() } }), { status: 200, headers: { 'content-type': 'text/event-stream' } })
  }
  try {
    const events = []
    await streamDashboardChat({ message: 'Explain this borough', history: [], dashboard: { title: 'X', description: '', cards: [] }, selection: { card_id: 'a', field: 'borough', value: 'Queens' }, version: 2 }, (event) => events.push(event), new AbortController().signal)
    assert.deepEqual(events.map((event) => event.type), ['status', 'delta', 'done'])
    assert.deepEqual(sent.selection, { card_id: 'a', field: 'borough', value: 'Queens' })
    assert.equal(sent.version, 2)
    assert.equal('research' in sent, false)
  } finally {
    globalThis.fetch = previousFetch
  }
})

test('long assistant answer stays visible but fits the next chat history request', async () => {
  const previousFetch = globalThis.fetch
  let sent
  globalThis.fetch = async (_url, options) => {
    sent = JSON.parse(options.body)
    return new Response('data: {"type":"done"}\n\n', { status: 200 })
  }
  const answer = 'Intro. ' + 'x'.repeat(5500) + ' Conclusion.'
  try {
    await streamDashboardChat({ message: 'Follow up', history: [{ role: 'assistant', content: answer }] }, () => {}, new AbortController().signal)
    assert.equal(answer.length > 4000, true)
    assert.equal(sent.history[0].content.length, 4000)
    assert.equal(sent.history[0].content.startsWith('Intro. '), true)
    assert.equal(sent.history[0].content.endsWith(' Conclusion.'), true)
  } finally {
    globalThis.fetch = previousFetch
  }
})

test('refresh re-queries the canonical spec after every series is hidden', async () => {
  const previousFetch = globalThis.fetch
  let sent
  const card = { id: 'rat', title: 'Rat likelihood', kind: 'bar', query: { dataset: 'cells', metrics: ['risk'], aggregation: 'mean' }, x: 'borough', y: ['risk'] }
  const artifact = { id: 'before', version: 2, created_at: '2026-09-27', spec: { title: 'Rats', description: '', cards: [card] }, results: {} }
  globalThis.fetch = async (_url, options) => {
    sent = JSON.parse(options.body)
    return Response.json({ ...artifact, id: 'after', version: 3 })
  }
  try {
    assert.deepEqual(visibleSeries(card, { hidden: ['risk'] }), [])
    const refreshed = await refreshDashboard(artifact, new AbortController().signal)
    assert.deepEqual(sent.spec.cards[0].y, ['risk'])
    assert.equal(sent.version, 3)
    assert.equal(refreshed.id, 'after')
  } finally {
    globalThis.fetch = previousFetch
  }
})
