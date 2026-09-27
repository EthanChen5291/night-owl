/// <reference lib="webworker" />

import { buildExtrusions, buildFlat, geometryTransfers, packGeometry, tintBuildingGeometry } from './tileGeometry'
import type { BuildingRange, TileGeometryReply, TileGeometryRequest } from './tileGeometry'

const worker = self as DedicatedWorkerGlobalScope

worker.onmessage = ({ data }: MessageEvent<TileGeometryRequest>) => {
  const { id, tileId, buildings, roads, facadeTileM, tint } = data
  try {
    const ranges: BuildingRange[] = []
    const buildingGeometry = buildings.length ? buildExtrusions(buildings, ranges, facadeTileM) : null
    if (buildingGeometry) tintBuildingGeometry(buildingGeometry, ranges, tint)
    const roadGeometry = roads.length ? buildFlat(roads) : null
    const buildingBuffers = buildingGeometry ? packGeometry(buildingGeometry) : null
    const roadBuffers = roadGeometry ? packGeometry(roadGeometry) : null
    const reply: TileGeometryReply = { id, tileId, ok: true, buildings: buildingBuffers, roads: roadBuffers, ranges }
    worker.postMessage(reply, [...geometryTransfers(buildingBuffers), ...geometryTransfers(roadBuffers)])
    buildingGeometry?.dispose()
    roadGeometry?.dispose()
  } catch (error) {
    const reply: TileGeometryReply = { id, tileId, ok: false, error: error instanceof Error ? error.message : String(error) }
    worker.postMessage(reply)
  }
}
