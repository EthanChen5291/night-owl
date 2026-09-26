import { useEffect, useRef } from 'react'
import { CityScene, type HoverHandler } from '../city/scene'
import type { Spot, Building, Cell, Mode, PlanNode, Preset } from '../types'
import type { LatLon } from '../city/projection'

interface Props {
  centre: LatLon
  cells: Cell[]
  mode: Mode
  preset: Preset
  plan: PlanNode[]
  showPlan: boolean
  buildings: Building[] | null
  flash: { h3: string; seq: number } | null
  focus: { h3: string; seq: number } | null
  spots?: Spot[]
  spotsFor?: string | null
  spotFocus?: { lat: number; lon: number; seq: number } | null
  onHover: HoverHandler
}

/** The only component that touches three.js. Owns one CityScene for the life of the canvas. */
export default function Scene({ centre, cells, mode, preset, plan, showPlan, buildings, flash, focus, onHover, spots = [], spotsFor = null, spotFocus = null }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const sceneRef = useRef<CityScene | null>(null)
  const hoverRef = useRef(onHover)
  hoverRef.current = onHover

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const scene = new CityScene(canvas, centre, (h3, x, y) => hoverRef.current(h3, x, y))
    sceneRef.current = scene
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
    if (buildings) sceneRef.current?.setBuildings(buildings)
  }, [buildings])

  useEffect(() => {
    if (flash) sceneRef.current?.flash(flash.h3)
  }, [flash])

  useEffect(() => {
    if (focus) sceneRef.current?.focusCell(focus.h3)
  }, [focus])
  useEffect(() => {
    sceneRef.current?.setSpots(spots, spotsFor)
  }, [spots, spotsFor])
  useEffect(() => {
    if (spotFocus) sceneRef.current?.focusLatLon(spotFocus.lat, spotFocus.lon)
  }, [spotFocus])

  return <canvas ref={canvasRef} className="scene" />
}
