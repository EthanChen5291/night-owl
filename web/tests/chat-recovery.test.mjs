import assert from 'node:assert/strict'
import test from 'node:test'
import { ChatGate, ChatRequestIdentity } from '../src/chatGate.ts'
import { importLegacyChat, pendingLegacyChat } from '../src/agent.ts'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function storage(t, entries) {
  const data = new Map(Object.entries(entries))
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  } })
  t.after(() => previous ? Object.defineProperty(globalThis, 'localStorage', previous) : delete globalThis.localStorage)
  return data
}

function fetchMock(t, fn) {
  const previous = globalThis.fetch
  globalThis.fetch = fn
  t.after(() => { globalThis.fetch = previous })
}

test('late thread load cannot replace a reset or a newer thread selection', async () => {
  const gate = new ChatGate()
  gate.migrating = false
  assert.equal(gate.navigationDone(0), true)
  let selected = 'original'
  const first = deferred()
  const firstToken = gate.navigate()
  const firstLoad = first.promise.then((id) => { if (gate.current(firstToken)) selected = id })
  assert.equal(gate.send(), null, 'send is blocked before GET resolves')

  const second = deferred()
  const secondToken = gate.navigate()
  const secondLoad = second.promise.then((id) => { if (gate.current(secondToken)) selected = id })
  second.resolve('second')
  await secondLoad
  gate.navigationDone(secondToken)
  first.resolve('first')
  await firstLoad
  assert.equal(selected, 'second')

  const third = deferred()
  const thirdToken = gate.navigate()
  const thirdLoad = third.promise.then((id) => { if (gate.current(thirdToken)) selected = id })
  gate.reset()
  selected = null
  third.resolve('third')
  await thirdLoad
  assert.equal(selected, null)
  assert.equal(gate.navigationDone(thirdToken), false)
})

test('reset ignores delayed stream updates and a pending browser tool', async () => {
  const gate = new ChatGate()
  gate.migrating = false
  gate.navigationDone(0)
  const token = gate.send()
  const abort = new AbortController()
  let visible = 'question'
  const queuedReactUpdate = gate.guard(token, (items) => [...items, 'late stream delta'])
  const tool = deferred()
  const run = tool.promise.then((result) => {
    if (!abort.signal.aborted && gate.current(token)) visible += result
  }).finally(() => {
    if (gate.sendDone(token)) visible += 'finished'
  })
  abort.abort()
  gate.reset()
  visible = ''
  tool.resolve('late result')
  await run
  assert.equal(visible, '')
  assert.deepEqual(queuedReactUpdate(['new chat']), ['new chat'], 'an already queued React updater is ignored after reset')
  assert.equal(gate.sending, false)
})

test('tool continuation stays attached to its original answer', () => {
  const request = new ChatRequestIdentity('thread-a')
  assert.equal(request.acceptThread('thread-a', 12), true)
  let selectedThread = 'thread-b'
  assert.deepEqual(request.continuation(), { thread_id: 'thread-a', answer_id: 12 })
  assert.equal(request.acceptThread(selectedThread, 12), false)
  assert.equal(request.acceptThread('thread-a', 13), false)
  assert.deepEqual(request.continuation(), { thread_id: 'thread-a', answer_id: 12 })

  const newRequest = new ChatRequestIdentity(null)
  assert.throws(() => newRequest.continuation(), /missing thread/)
  assert.equal(newRequest.acceptThread('new-thread', 7), true)
  assert.deepEqual(newRequest.continuation(), { thread_id: 'new-thread', answer_id: 7 })
})

test('legacy import prefers canonical chat and marks completion only after a server response', async (t) => {
  const canonical = JSON.stringify({ items: [{ kind: 'user', text: 'current' }], history: [{ role: 'user', content: 'current' }] })
  const older = JSON.stringify({ items: [{ kind: 'user', text: 'old' }], history: [] })
  const data = storage(t, { 'nightowl.chat.client': 'test_client_123456789', 'nightowl.chat.v1': canonical, 'barnowl.chat.v1': older })
  const calls = []
  let fail = true
  fetchMock(t, async (url, init) => {
    calls.push({ url, init })
    return fail ? new Response('temporary failure', { status: 503 }) : Response.json({ thread: { id: 'imported', title: 'current' }, turns: [] })
  })
  const legacy = pendingLegacyChat()
  assert.equal(legacy.migration_key, 'nightowl.chat.v1')
  await assert.rejects(importLegacyChat(legacy), /503/)
  assert.equal(data.has('nightowl.chat.imported.v1'), false)
  assert.equal(data.get('nightowl.chat.v1'), canonical)

  fail = false
  const imported = await importLegacyChat(pendingLegacyChat())
  assert.equal(imported.thread.id, 'imported')
  assert.equal(calls.length, 2)
  assert.equal(calls[0].url, '/api/agent/threads/import')
  assert.equal(calls[0].init.headers['x-chat-client'], 'test_client_123456789')
  assert.deepEqual(JSON.parse(calls[1].init.body), legacy)
  assert.equal(data.get('nightowl.chat.v1'), canonical, 'source remains as a backup')
  assert.equal(data.get('barnowl.chat.v1'), older)
  assert.equal(pendingLegacyChat(), null, 'confirmed import is not retried on reload')
})

test('legacy-only browser chat can be imported and bad canonical data falls back to it', (t) => {
  storage(t, { 'nightowl.chat.v1': '{bad', 'barnowl.chat.v1': JSON.stringify({ items: [{ kind: 'user', text: 'old' }], history: [] }) })
  assert.equal(pendingLegacyChat().migration_key, 'barnowl.chat.v1')
})
