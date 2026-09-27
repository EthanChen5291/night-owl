import assert from 'node:assert/strict'
import test from 'node:test'
import { appendThinking, dashboardMarkdown } from '../src/dashboard/reasoning.ts'

test('reasoning chunks form Markdown within each round without joining separate rounds', () => {
  let rounds = []
  for (const [round, chunk] of [[1, '### **Find'], [1, 'ings**\n- Bronx'], [2, '### Next pass\n'], [2, '1. Inspect rows']]) {
    rounds = appendThinking(rounds, chunk, round)
  }
  assert.deepEqual(rounds, [
    { round: 1, text: '### **Findings**\n- Bronx' },
    { round: 2, text: '### Next pass\n1. Inspect rows' },
  ])
  assert.match(dashboardMarkdown(rounds[0].text), /<h4><b>Findings<\/b><\/h4><ul><li>Bronx<\/li><\/ul>/)
  assert.match(dashboardMarkdown(rounds[1].text), /<h4>Next pass<\/h4><ol><li>Inspect rows<\/li><\/ol>/)
})

test('reasoning renderer escapes hostile markup and removes external links', () => {
  const html = dashboardMarkdown('### Results\n- **Safe** <img src=x onerror=alert(1)>\n- [source](https://example.com/a) https://evil.test/x\n<script>alert(2)</script>')
  assert.match(html, /<h4>Results<\/h4>/)
  assert.match(html, /<b>Safe<\/b> &lt;img/)
  assert.match(html, /&lt;script&gt;alert\(2\)&lt;\/script&gt;/)
  assert.match(html, /source/)
  assert.doesNotMatch(html, /<(?:img|script|a)\b|href=|https?:\/\/|example\.com|evil\.test/i)
})

test('reasoning keeps the recent full-text limit and legacy chunks share the current round', () => {
  const first = appendThinking([], 'a'.repeat(5900), 1)
  const second = appendThinking(first, 'b'.repeat(200), 2)
  assert.deepEqual(second.map((item) => [item.round, item.text.length]), [[1, 5800], [2, 200]])
  assert.deepEqual(appendThinking(second, ' end').at(-1), { round: 2, text: 'b'.repeat(200) + ' end' })
})
