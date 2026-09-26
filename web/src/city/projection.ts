// Equirectangular projection to local metres, x east / y north, around a centre lat/lon.
// Mirrors Projector in city/build_city.py so a buildings.json bake lines up with the cells
// when both use the same centre.
export const M_PER_DEG = 111_320

export interface LatLon {
  lat: number
  lon: number
}

export interface Projector {
  centre: LatLon
  xy(lat: number, lon: number): [number, number]
  latLon(x: number, y: number): LatLon
}

export function makeProjector(centre: LatLon): Projector {
  const kx = M_PER_DEG * Math.cos((centre.lat * Math.PI) / 180)
  return {
    centre,
    xy: (lat, lon) => [(lon - centre.lon) * kx, (lat - centre.lat) * M_PER_DEG],
    latLon: (x, y) => ({ lat: centre.lat + y / M_PER_DEG, lon: centre.lon + x / kx }),
  }
}

export function centroid(points: LatLon[]): LatLon {
  if (points.length === 0) return { lat: 40.72, lon: -73.995 }
  let lat = 0
  let lon = 0
  for (const p of points) {
    lat += p.lat
    lon += p.lon
  }
  return { lat: lat / points.length, lon: lon / points.length }
}
