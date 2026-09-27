/// <reference lib="webworker" />

import { buildFlat, geometryTransfers, packGeometry, type PackedGeometry } from './tileGeometry'
import type { CityLayers } from '../types'

const worker = self as DedicatedWorkerGlobalScope

export interface FlatLayersReply {
  id: number
  layers: Record<keyof CityLayers, PackedGeometry | null>
}

worker.onmessage = ({ data }: MessageEvent<{ id: number; layers: CityLayers }>) => {
  const layers = { land: null, parks: null, water: null } as FlatLayersReply['layers']
  const transfers: Transferable[] = []
  for (const name of ['land', 'parks', 'water'] as const) {
    const polys = data.layers[name]
    if (!polys?.length) continue
    const geometry = buildFlat(polys)
    if (!geometry) continue
    layers[name] = packGeometry(geometry)
    transfers.push(...geometryTransfers(layers[name]))
    geometry.dispose()
  }
  worker.postMessage({ id: data.id, layers } satisfies FlatLayersReply, transfers)
}
