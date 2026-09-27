/// <reference lib="webworker" />

import { FieldGeometryBuilder, type FieldArea, type FieldGeometry } from './fieldGeometry'
import type { LatLon } from './projection'
import type { Poly } from '../types'

export interface FieldRequest {
  id: number
  centre: LatLon
  land?: Poly[]
  areas?: FieldArea[]
  colours: [string, string][]
  smooth: number
}
export interface FieldReply { id: number; geometry: FieldGeometry }

const worker = self as DedicatedWorkerGlobalScope
let builder: FieldGeometryBuilder | null = null
worker.onmessage = ({ data }: MessageEvent<FieldRequest>) => {
  builder ??= new FieldGeometryBuilder(data.centre)
  if (data.land) builder.setLand(data.land)
  if (data.areas) builder.setAreas(data.areas)
  const geometry = builder.build(new Map(data.colours), data.smooth)
  worker.postMessage({ id: data.id, geometry } satisfies FieldReply,
    [geometry.pos.buffer, geometry.col.buffer, geometry.idx.buffer])
}
