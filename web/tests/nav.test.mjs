import assert from 'node:assert/strict'
import test from 'node:test'
import { createPageNavigation, isDashboardPath, linkClick, navigate, onNavigate } from '../src/nav.ts'

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('Back cancels a pending page load even when returning to the page still on screen', async () => {
  const chunk = deferred()
  const commits = []
  const nav = createPageNavigation('/', () => chunk.promise, (...args) => commits.push(args), assert.fail)
  const opening = nav.go('/dashboards')
  await nav.go('/')
  chunk.resolve()
  await opening
  assert.deepEqual(commits, [])
})

test('latest navigation wins out-of-order loads and uses the currently committed source', async () => {
  const loads = []
  const commits = []
  const nav = createPageNavigation('/', () => { const d = deferred(); loads.push(d); return d.promise }, (...args) => commits.push(args), assert.fail)
  const older = nav.go('/dashboards')
  const latest = nav.go('/dashboards/')
  loads[1].resolve(); await latest
  loads[0].resolve(); await older
  const back = nav.go('/')
  loads[2].resolve(); await back
  assert.deepEqual(commits, [['/dashboards/', '/'], ['/', '/dashboards/']])
})

test('unmount and stale load failures cannot commit or reload; active failures can recover', async () => {
  const loads = []
  const failed = []
  const nav = createPageNavigation('/', () => { const d = deferred(); loads.push(d); return d.promise }, assert.fail, (path) => failed.push(path))
  const stale = nav.go('/dashboards')
  await nav.go('/')
  loads[0].reject(new Error('offline')); await stale
  assert.deepEqual(failed, [])
  const active = nav.go('/dashboards')
  loads[1].reject(new Error('offline')); await active
  assert.deepEqual(failed, ['/dashboards'])
  const cancelled = nav.go('/dashboards')
  nav.cancel(); loads[2].resolve(); await cancelled
})

test('normal links update history once; modified clicks preserve native browser behavior', () => {
  const oldWindow = globalThis.window
  const history = [], delivered = []
  globalThis.window = { location: { pathname: '/' }, history: { pushState(_state, _unused, path) { history.push(path); globalThis.window.location.pathname = path } } }
  const off = onNavigate((path) => delivered.push(path))
  try {
    let prevented = 0
    const base = { button: 0, preventDefault() { prevented++ } }
    for (const modifier of ['metaKey', 'ctrlKey', 'shiftKey', 'altKey', 'defaultPrevented']) linkClick('/dashboards')({ ...base, [modifier]: true })
    linkClick('/dashboards')({ ...base, button: 1 })
    assert.equal(prevented, 0)
    linkClick('/dashboards')(base)
    navigate('/dashboards')
    assert.deepEqual(history, ['/dashboards'])
    assert.deepEqual(delivered, ['/dashboards'])
    assert.equal(prevented, 1)
    assert.equal(isDashboardPath('/dashboards/'), true)
    assert.equal(isDashboardPath('/dashboards/fake'), false)
  } finally { off(); globalThis.window = oldWindow }
})
