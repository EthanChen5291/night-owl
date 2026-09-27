// Writes api/cell_centres.json ({h3: [lat, lon]}) for every hexagon in the model output, so the Python agent
// (api/agent.py, stdlib only) can do "near here" lookups without an h3 dependency. Run from web/: node scripts/cell-centres.mjs
import { readFileSync, writeFileSync } from 'node:fs'
import { cellToLatLng } from 'h3-js'

const root = new URL('../../', import.meta.url)
const src = ['model/out/cells.json', 'city/cells.fixture.json'].map((p) => new URL(p, root)).find((u) => { try { readFileSync(u); return true } catch { return false } })
const { cells } = JSON.parse(readFileSync(src, 'utf8'))
const out = {}
for (const c of cells) out[c.h3] = cellToLatLng(c.h3).map((v) => Math.round(v * 1e6) / 1e6)
writeFileSync(new URL('api/cell_centres.json', root), JSON.stringify(out))
console.log(`cell_centres.json: ${Object.keys(out).length} hexagons`)
