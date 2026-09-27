import type { CityScene } from './scene'

/** The mounted scene for browser tools outside React. */
export const sceneHandle: { current: CityScene | null } = { current: null }
