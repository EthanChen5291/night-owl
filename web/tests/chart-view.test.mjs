import assert from 'node:assert/strict'
import test from 'node:test'
import { availableKinds, resolvedKind, rowFromChartClick } from '../src/dashboard/view.ts'

const card = { id: 'mix', title: 'Mixed metrics', kind: 'table', x: 'day', y: ['risk', 'hits'] }
const result = {
  rows: [{ day: 'Monday', risk: 0.2, hits: 3 }, { day: 'Tuesday', risk: 0.4, hits: 4 }],
  columns: [
    { key: 'day', label: 'Day', unit: '' },
    { key: 'risk', label: 'Risk', unit: 'probability' },
    { key: 'hits', label: 'Hits', unit: 'hits' },
  ],
}

test('chart background without a valid index does not select the first row', () => {
  const rows = result.rows
  for (const event of [null, {}, { activeIndex: null }, { activeIndex: '' },
    { activeIndex: -1 }, { activeIndex: 2 }, { activeIndex: '1.0' }]) {
    assert.equal(rowFromChartClick(rows, event), undefined)
  }
  assert.equal(rowFromChartClick(rows, { activeIndex: 0 }), rows[0])
  assert.equal(rowFromChartClick(rows, { activeIndex: '1' }), rows[1])
  assert.equal(rowFromChartClick(rows, { activePayload: [{ payload: rows[1] }], activeIndex: null }), rows[1])
})

test('mixed-unit table cannot become a shared-axis chart, even with one series hidden', () => {
  const view = { kind: 'bar' }
  assert.deepEqual([...availableKinds(card, result, view)], ['table'])
  assert.equal(resolvedKind(card, result, view), 'table')
  const hidden = { kind: 'line', hidden: ['hits'] }
  assert.equal(availableKinds(card, result, hidden).has('line'), false)
  assert.equal(resolvedKind(card, result, hidden), 'table')
})

test('same-unit series can use bar and line; a single visible series can use scatter', () => {
  const compatible = { ...result, columns: result.columns.map((column) =>
    column.key === 'hits' ? { ...column, unit: 'probability' } : column) }
  const choices = availableKinds(card, compatible, {})
  assert.equal(choices.has('bar'), true)
  assert.equal(choices.has('line'), true)
  assert.equal(resolvedKind(card, compatible, { kind: 'line' }), 'line')
  assert.equal(availableKinds(card, compatible, { hidden: ['hits'] }).has('scatter'), false,
    'the x field is categorical')
  const numericX = { ...card, x: 'risk', y: ['hits'] }
  assert.equal(availableKinds(numericX, compatible, {}).has('scatter'), true)
})
