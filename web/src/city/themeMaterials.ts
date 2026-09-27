import type * as THREE from 'three'

const PARS = '#include <color_pars_vertex>'
const COLOR = '#include <color_vertex>'

/** Select precomputed day/night vertex colours without rewriting building buffers. */
export function installBuildingTheme(materials: readonly THREE.MeshStandardMaterial[]) {
  const night = { value: 0 }
  for (const material of materials) {
    if (!material.vertexColors) throw new Error('Building theme requires vertex colors')
    material.onBeforeCompile = (shader) => {
      if (!shader.vertexShader.includes(PARS) || !shader.vertexShader.includes(COLOR)) {
        throw new Error('Three building color shader chunks changed')
      }
      shader.uniforms.uBuildingNight = night
      shader.vertexShader = shader.vertexShader
        .replace(PARS, `${PARS}\n#ifdef USE_COLOR\nattribute vec3 colorNight;\nuniform float uBuildingNight;\n#endif`)
        .replace(COLOR, `${COLOR}\n#ifdef USE_COLOR\nvColor.rgb = mix(vColor.rgb, colorNight, uBuildingNight);\n#endif`)
    }
    material.customProgramCacheKey = () => 'building-theme-v1'
  }
  return { setNight(value: boolean) { night.value = value ? 1 : 0 } }
}

/** Keep the field geometry unchanged when its neutral colour and opacity change. */
export function installFieldTheme(material: THREE.MeshBasicMaterial, neutral: THREE.IUniform<THREE.Color>, mix: THREE.IUniform<number>) {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.fieldNeutral = neutral
    shader.uniforms.fieldMix = mix
    shader.vertexShader = 'uniform vec3 fieldNeutral;\nuniform float fieldMix;\n' + shader.vertexShader.replace(
      COLOR, `${COLOR}\n#ifdef USE_COLOR\nvColor.rgb = mix(vColor.rgb, fieldNeutral, fieldMix);\n#endif`,
    )
  }
  material.customProgramCacheKey = () => 'field-theme-v1'
}
