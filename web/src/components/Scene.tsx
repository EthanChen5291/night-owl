import { useEffect, useRef } from 'react'
import { CityScene, type SceneCallbacks } from '../city/scene'
import type { AddressIndex } from '../city/addresses'
import type { Area, Cell, CityLayers, Mode, OwlNode, PlanNode, Preset, Spot, Tile } from '../types'
import type { LatLon } from '../city/projection'

interface Props {
  centre: LatLon
  cells: Cell[]
  mode: Mode
  preset: Preset
  plan: PlanNode[]
  showPlan: boolean
  spots: Spot[]
  cityLayers: CityLayers | null
  areaLayers: CityLayers | null
  tiles: Map<string, Tile>
  areas: Area[]
  tileAreas: Record<string, string | null | undefined>
  activeArea: string | null
  nodes: OwlNode[]
  selectedNode: string | null
  index: AddressIndex | null
  flash: { h3: string; seq: number } | null
  focus: { lat: number; lon: number; distance?: number; seq: number } | null
  locate: { h3: string; seq: number } | null
  onHover: SceneCallbacks['onHover']
  onClick: SceneCallbacks['onClick']
  onView: SceneCallbacks['onView']
}

/** The only component that touches three.js. Owns one CityScene for the life of the canvas. */
export default function Scene(props: Props) {
  const { centre, cells, mode, preset, plan, showPlan, spots, cityLayers, areaLayers, tiles, areas, tileAreas, activeArea, nodes, selectedNode, index, flash, focus, locate } = props
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<CityScene | null>(null)
  const cbRef = useRef({ onHover: props.onHover, onClick: props.onClick, onView: props.onView })
  cbRef.current = { onHover: props.onHover, onClick: props.onClick, onView: props.onView }
  const firstArea = useRef(true)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const scene = new CityScene(canvas, centre, {
      onHover: (info) => cbRef.current.onHover(info),
      onClick: (info) => cbRef.current.onClick(info),
      onView: (view) => cbRef.current.onView(view),
    })
    sceneRef.current = scene
    if (import.meta.env.DEV) (window as unknown as { __barnowl?: CityScene }).__barnowl = scene // the screenshot scripts ask it where things are
    return () => {
      scene.dispose()
      sceneRef.current = null
    }
    // the centre is fixed for the life of the app (recentring would rebuild everything)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    sceneRef.current?.setCells(cells, mode)
  }, [cells, mode])
  useEffect(() => {
    sceneRef.current?.setMode(mode)
  }, [mode])
  useEffect(() => {
    sceneRef.current?.setPreset(preset)
  }, [preset])
  useEffect(() => {
    sceneRef.current?.setPlan(plan)
  }, [plan, cells])
  useEffect(() => {
    sceneRef.current?.setPlanVisible(showPlan)
  }, [showPlan])
  useEffect(() => {
    sceneRef.current?.setSpots(spots)
  }, [spots])
  useEffect(() => {
    if (cityLayers) sceneRef.current?.setCityLayers(cityLayers)
  }, [cityLayers])
  useEffect(() => {
    sceneRef.current?.setAreaLayers(areaLayers)
  }, [areaLayers])
  useEffect(() => {
    sceneRef.current?.setTiles(tiles)
  }, [tiles])
  useEffect(() => {
    sceneRef.current?.setAreas(areas)
  }, [areas])
  useEffect(() => {
    sceneRef.current?.setTileAreas(tileAreas)
  }, [tileAreas])
  useEffect(() => {
    sceneRef.current?.setActiveArea(activeArea, firstArea.current)
    firstArea.current = false
  }, [activeArea, areas])
  useEffect(() => {
    sceneRef.current?.setNodes(nodes, selectedNode)
  }, [nodes, selectedNode])
  useEffect(() => {
    sceneRef.current?.setAddressIndex(index)
  }, [index])
  useEffect(() => {
    if (flash) sceneRef.current?.flash(flash.h3)
  }, [flash])
  useEffect(() => {
    if (focus) sceneRef.current?.focusLatLon(focus.lat, focus.lon, focus.distance)
  }, [focus])
  useEffect(() => {
    if (locate) sceneRef.current?.locate(locate.h3)
  }, [locate])

  return <canvas ref={canvasRef} className="scene" />
}
