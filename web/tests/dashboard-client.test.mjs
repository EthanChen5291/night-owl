import assert from 'node:assert/strict'
import test from 'node:test'
import { streamDashboardChat } from '../src/dashboard/client.ts'

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
