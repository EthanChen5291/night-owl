import assert from 'node:assert/strict'
import test from 'node:test'
import { readSavedValue } from '../src/storage.ts'
import { loadOwls, saveOwls } from '../src/owls.ts'

function mockStorage(t, values, readOnly = false) {
  const data = new Map(Object.entries(values))
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => { if (readOnly) throw new Error('quota'); data.set(key, value) },
    removeItem: (key) => data.delete(key),
  } })
  t.after(() => {
    if (previous) Object.defineProperty(globalThis, 'localStorage', previous)
    else delete globalThis.localStorage
  })
  return data
}

test('legacy owl placements retain their node IDs and migrate once', (t) => {
  const nodes = [{ id: 'owl-1', nodeId: 'demo-01', lat: 40.7, lon: -74 }]
  const data = mockStorage(t, { 'barnowl.owls': JSON.stringify(nodes) })
  assert.deepEqual(loadOwls(), nodes)
  assert.equal(data.has('barnowl.owls'), false)
  assert.deepEqual(JSON.parse(data.get('nightowl.owls')), nodes)
  saveOwls([])
  assert.deepEqual(loadOwls(), [])
})

test('current placements and intentionally empty preferences win over legacy values', (t) => {
  mockStorage(t, { 'nightowl.owls': '[]', 'barnowl.owls': '[{"id":"old"}]', 'nightowl.area': '', 'barnowl.area': 'brooklyn' })
  assert.deepEqual(loadOwls(), [])
  assert.equal(readSavedValue('nightowl.area', 'barnowl.area'), '')
})

test('area and chat migrate without losing their contents', (t) => {
  const data = mockStorage(t, { 'barnowl.area': 'queens', 'barnowl.chat.v1': '{"history":[]}' })
  for (const suffix of ['area', 'chat.v1']) {
    const value = data.get(`barnowl.${suffix}`)
    assert.equal(readSavedValue(`nightowl.${suffix}`, `barnowl.${suffix}`), value)
    assert.equal(data.get(`nightowl.${suffix}`), value)
    assert.equal(data.has(`barnowl.${suffix}`), false)
  }
  data.delete('nightowl.area')
  assert.equal(readSavedValue('nightowl.area', 'barnowl.area'), null)
})

test('failed migration writes keep legacy data readable and intact', (t) => {
  const data = mockStorage(t, { 'barnowl.owls': '[{"id":"owl-1"}]' }, true)
  assert.deepEqual(loadOwls(), [{ id: 'owl-1' }])
  assert.equal(data.has('barnowl.owls'), true)
  assert.equal(data.has('nightowl.owls'), false)
})
