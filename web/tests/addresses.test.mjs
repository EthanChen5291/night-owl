import assert from 'node:assert/strict'
import test from 'node:test'
import { AddressIndex } from '../src/city/addresses.ts'

const square = (x, y) => [[x, y], [x + 10, y], [x + 10, y + 10], [x, y + 10]]
const tile = (id, x, treeX) => ({
  id,
  buildings: [{ addr: `${id} building`, footprint: square(x, 0) }],
  trees: [{ addr: `${id} street`, x: treeX, y: 0 }],
  roads: [],
})

test('tile composition preserves building order and finds the nearest tree across tiles', () => {
  const a = tile('a', 0, 30)
  const b = tile('b', 100, 20)
  const index = AddressIndex.fromTiles([a, b])
  assert.equal(index.buildingAt(5, 5)?.addr, 'a building')
  assert.equal(index.buildingAt(105, 5)?.addr, 'b building')
  assert.equal(index.nearestTree(22, 0)?.tree.addr, 'b street')
  assert.equal(index.at(22, 0)?.kind, 'street')
  assert.equal(index.empty, false)

  const overlapping = tile('overlap', 0, 40)
  assert.equal(AddressIndex.fromTiles([a, overlapping]).buildingAt(5, 5)?.addr, 'a building')
  assert.equal(AddressIndex.fromTiles([overlapping, a]).buildingAt(5, 5)?.addr, 'overlap building')
})

test('removed tiles stop answering queries and empty compositions stay empty', () => {
  const a = tile('a', 0, 30)
  const b = tile('b', 100, 120)
  assert.equal(AddressIndex.fromTiles([a, b]).buildingAt(5, 5)?.addr, 'a building')
  const onlyB = AddressIndex.fromTiles([b])
  assert.equal(onlyB.buildingAt(5, 5), null)
  assert.equal(onlyB.nearestTree(30, 0), null)
  assert.equal(onlyB.buildingAt(105, 5)?.addr, 'b building')
  assert.equal(AddressIndex.fromTiles([]).empty, true)
})

test('an unchanged tile reuses its indexed buildings and trees', () => {
  let reads = 0
  const stable = {
    id: 'stable', roads: [],
    get buildings() { reads++; return [{ addr: 'stable building', footprint: square(0, 0) }] },
    get trees() { reads++; return [] },
  }
  assert.equal(AddressIndex.fromTiles([stable]).buildingAt(5, 5)?.addr, 'stable building')
  assert.equal(reads, 2)
  assert.equal(AddressIndex.fromTiles([stable]).buildingAt(5, 5)?.addr, 'stable building')
  assert.equal(reads, 2)
})
