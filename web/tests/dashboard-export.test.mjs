import assert from 'node:assert/strict'
import test from 'node:test'
import vm from 'node:vm'
import { buildDashboardHtml, downloadDashboard } from '../src/dashboard/export.ts'

const artifact = () => ({
  id: 'night-owl-export', version: 2, created_at: '2026-09-27T12:34:56Z',
  spec: {
    title: 'Rat activity <North> & South', description: 'Frozen results, including </script><script>alert(1)</script> and \u2028\u2029.',
    cards: [
      { id: 'activity', title: 'Events by day', kind: 'bar', query: { dataset: 'events', metrics: ['count'], aggregation: 'count' }, x: 'day', y: ['count', 'people'] },
      { id: 'locations', title: 'Locations', kind: 'scatter', query: { dataset: 'sites', metrics: ['score'], aggregation: 'raw' }, x: 'x', y: ['score'] },
      { id: 'total', title: 'Total', kind: 'metric', query: { dataset: 'events', metrics: ['count'], aggregation: 'count' }, x: 'day', y: ['count'] },
    ],
  },
  results: {
    activity: { columns: [{ key: 'day', label: 'Day', unit: '' }, { key: 'count', label: 'Rats', unit: '' }, { key: 'people', label: 'People', unit: '' }], rows: [{ day: '2026-09-25', count: 1, people: 2 }, { day: '=HYPERLINK("evil")', count: 3, people: 0 }, { day: '<img src=x onerror=alert(1)>', count: 5, people: 2 }], total_rows: 300, source: { label: 'Barn Owl', as_of: '2026-09-27', kind: 'events', notes: ['Model-estimated data'] }, query: { dataset: 'events', metrics: ['count'], aggregation: 'count' } },
    locations: { columns: [{ key: 'x', label: 'X', unit: 'm' }, { key: 'score', label: 'Score', unit: '' }], rows: [{ x: 1, score: 0.2 }, { x: 2, score: 0.8 }], total_rows: 2, source: { label: 'Sites', as_of: '2026-09-27', kind: 'model', notes: [] }, query: { dataset: 'sites', metrics: ['score'], aggregation: 'raw' } },
    total: { columns: [{ key: 'count', label: 'Count', unit: '' }], rows: [{ count: 9 }], total_rows: 1, source: { label: 'Events', as_of: '2026-09-27', kind: 'events', notes: [] }, query: { dataset: 'events', metrics: ['count'], aggregation: 'count' } },
  },
  research: { summary: 'Legacy research must not be exported', sources: [
    { title: 'Legacy citation', url: 'https://example.org/study?q=rat' },
  ] },
})

function snapshot(html) {
  const match = html.match(/<script id="snapshot" type="application\/json">([\s\S]*?)<\/script>/)
  assert.ok(match)
  return JSON.parse(match[1])
}

function renderOffline(input) {
  const html = buildDashboardHtml(input)
  const script = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)][1][1]
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.attributes = {}; this.style = { setProperty() {} }; this.textContent = ''; this.value = '' }
    append(...children) { this.children.push(...children) }
    replaceChildren(...children) { this.children = [...children] }
    setAttribute(key, val) { this.attributes[key] = String(val) }
    addEventListener(name, callback) { this.listeners[name] = callback }
    dispatch(name) { this.listeners[name]?.() }
  }
  const roots = Object.fromEntries(['header', 'cards'].map((id) => [id, new Element(id)]))
  const document = {
    getElementById(id) { return id === 'snapshot' ? { textContent: JSON.stringify(snapshot(html)) } : roots[id] },
    createElement(tag) { return new Element(tag) },
    createElementNS(_ns, tag) { return new Element(tag) },
    createTextNode(text) { const node = new Element('#text'); node.textContent = text; return node },
  }
  vm.runInNewContext(script, { document, URL, Intl, Blob, setTimeout })
  const all = (root, tag) => [root, ...root.children.flatMap((child) => all(child, tag))].filter((node) => !tag || node.tag === tag)
  const text = (root) => root.textContent + root.children.map(text).join('')
  return { roots, all, text }
}

test('snapshot preserves every saved row and escapes hostile text from the HTML parser', () => {
  const input = artifact()
  input.external_notes = 'PRIVATE LEGACY EXTRA'
  const html = buildDashboardHtml(input)
  const saved = snapshot(html)
  assert.deepEqual(Object.keys(saved), ['id', 'version', 'created_at', 'spec', 'results'])
  assert.equal(saved.spec.description, input.spec.description)
  assert.deepEqual(saved.results.activity.rows, input.results.activity.rows)
  assert.equal(saved.results.activity.total_rows, 300)
  assert.equal(saved.created_at, input.created_at)
  assert.ok(html.includes('Rat activity &lt;North&gt; &amp; South'))
  assert.ok(!html.includes('</script><script>alert(1)</script>'))
  assert.ok(!html.includes('\u2028') && !html.includes('\u2029'))
  assert.ok(html.includes('\\u003c/script\\u003e'))
  assert.equal(input.research.sources[0].url, 'https://example.org/study?q=rat', 'export must not mutate the input')
  assert.doesNotMatch(html, /Legacy research|Legacy citation|example\.org|PRIVATE LEGACY EXTRA/)
})

test('export contains only authored inline code and has offline chart/table controls', () => {
  const html = buildDashboardHtml(artifact())
  assert.match(html, /Frozen snapshot/)
  assert.match(html, /chat and live data refresh remain in the Night Owl app/)
  assert.doesNotMatch(html, /research|citation|external link/i)
  assert.doesNotMatch(html, /<script[^>]+src=|<link[^>]+href=|@import|fetch\s*\(|XMLHttpRequest|WebSocket/i)
  assert.match(html, /connect-src 'none'/)
  assert.match(html, /createElementNS\('http:\/\/www\.w3\.org\/2000\/svg'/)
  assert.match(html, /Download CSV/)
  assert.match(html, /Search rows/)
  assert.match(html, /Sort by /)
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)]
  assert.equal(scripts.length, 2)
  new vm.Script(scripts[1][1])
})

test('download creates a named HTML blob without contacting a provider', () => {
  const previousDocument = globalThis.document
  const previousCreate = URL.createObjectURL
  const previousRevoke = URL.revokeObjectURL
  const previousTimeout = globalThis.setTimeout
  let clicked = false, blob, filename
  globalThis.document = { createElement: () => ({ click() { clicked = true; filename = this.download } }) }
  URL.createObjectURL = (value) => { blob = value; return 'blob:local-snapshot' }
  URL.revokeObjectURL = () => {}
  globalThis.setTimeout = () => 0
  try {
    downloadDashboard(artifact())
    assert.equal(clicked, true)
    assert.equal(filename, 'Rat-activity-North-South.html')
    assert.equal(blob.type, 'text/html;charset=utf-8')
  } finally {
    globalThis.document = previousDocument
    URL.createObjectURL = previousCreate
    URL.revokeObjectURL = previousRevoke
    globalThis.setTimeout = previousTimeout
  }
})

test('chart percentages, result-group limits, and missing-value gaps render faithfully', () => {
  const input = artifact()
  input.spec.cards = [input.spec.cards[0]]
  input.spec.cards[0].kind = 'line'
  input.spec.cards[0].y = ['count']
  input.results.activity.query.group_by = 'day'
  input.results.activity.columns[1].unit = 'fraction'
  input.results.activity.rows = [
    { day: 'A', count: 0.033 }, { day: 'B', count: 0.04 },
    { day: 'C', count: null }, { day: 'D', count: 0.08 }, { day: 'E', count: 0.1 },
  ]
  const view = renderOffline(input)
  const card = view.roots.cards.children[0]
  assert.match(view.text(card), /5 of 300 result groups saved/)
  assert.match(view.text(card), /Query limit omitted 295 result groups; charts, tables, and CSV use only saved data/)
  assert.match(view.text(card), /Rats \(%\)/)
  assert.match(view.text(card), /3\.3%/)
  assert.equal(view.all(card, 'polyline').length, 2, 'missing y must split the line into two runs')
  for (const line of view.all(card, 'polyline')) assert.equal(line.attributes.points.split(' ').length, 2)
  assert.ok(view.all(card, 'text').some((node) => node.textContent.endsWith('%')), 'y-axis ticks use percent units')
})

test('table nulls stay last in either direction and percentile values are unscaled', () => {
  const input = artifact()
  input.spec.cards = [input.spec.cards[0], input.spec.cards[2]]
  input.spec.cards[0].y = ['count']
  input.results.activity.columns[1].unit = 'probability'
  input.results.activity.rows = [
    { day: 'A', count: 0.033 }, { day: 'B', count: null }, { day: 'C', count: 0.8 },
  ]
  input.results.total.columns[0].unit = 'percentile 0–100'
  input.results.total.rows = [{ count: 73.4 }]
  const view = renderOffline(input)
  assert.match(view.text(view.roots.cards.children[1]), /73\.4 percentile 0–100/)
  const card = view.roots.cards.children[0]
  const type = view.all(card, 'select')[0]
  type.value = 'table'; type.dispatch('change')
  const sort = view.all(card, 'button').find((node) => node.textContent === 'Rats')
  const values = () => view.all(card, 'tbody')[0].children.map((row) => row.children[1].textContent)
  sort.dispatch('click')
  assert.deepEqual(values(), ['3.3%', '80%', '—'])
  sort.dispatch('click')
  assert.deepEqual(values(), ['80%', '3.3%', '—'])
})
