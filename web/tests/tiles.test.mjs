import assert from 'node:assert/strict'
import test from 'node:test'
import { setTimeout as delay } from 'node:timers/promises'
import { streamTiles } from '../src/city/tiles.ts'

const tile = (id) => ({ id, buildings: [], roads: [], trees: [] })

test('cached tiles appear immediately and nearby loads publish together', async () => {
  const cached = new Map([['a', tile('a')]])
  const finish = new Map()
  const cache = {
    get: (id) => cached.get(id),
    load: (id) => new Promise((resolve) => finish.set(id, () => {
      cached.set(id, tile(id))
      resolve(cached.get(id))
    })),
  }
  const updates = []
  const stop = streamTiles(cache, ['a', 'b', 'c'], (tiles, pending) => updates.push({ ids: [...tiles.keys()], pending }), 5)
  try {
    assert.deepEqual(updates, [{ ids: ['a'], pending: 2 }])
    cached.delete('a') // another flight can evict it from the shared cache
    finish.get('b')()
    finish.get('c')()
    await delay(15)
    assert.deepEqual(updates, [
      { ids: ['a'], pending: 2 },
      { ids: ['a', 'b', 'c'], pending: 0 },
    ])
  } finally {
    stop()
  }
})

test('a cancelled tile selection cannot publish a late response or change pending count', async () => {
  let finish
  const cached = new Map()
  const cache = {
    get: (id) => cached.get(id),
    load: (id) => new Promise((resolve) => { finish = () => { cached.set(id, tile(id)); resolve(cached.get(id)) } }),
  }
  const updates = []
  const stop = streamTiles(cache, ['old'], (tiles, pending) => updates.push({ ids: [...tiles.keys()], pending }), 5)
  assert.deepEqual(updates, [{ ids: [], pending: 1 }])
  stop()
  finish()
  await delay(15)
  assert.deepEqual(updates, [{ ids: [], pending: 1 }])
})
