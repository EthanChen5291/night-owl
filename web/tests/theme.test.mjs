import assert from 'node:assert/strict'
import test from 'node:test'
import * as THREE from 'three'
import { installBuildingTheme } from '../src/city/themeMaterials.ts'

const average = (colours) => colours.reduce((sum, colour) => sum.add(colour), new THREE.Color(0, 0, 0)).multiplyScalar(1 / colours.length)

test('field neutral mix gives the same shared-corner colour before or after averaging', () => {
  const base = [0x440154, 0x21918c, 0xfde725].map((hex) => new THREE.Color(hex))
  for (const [neutralHex, mix] of [[0xe6e4de, 0.12], [0x171b26, 0.25]]) {
    const neutral = new THREE.Color(neutralHex)
    const oldCorner = average(base.map((colour) => colour.clone().lerp(neutral, mix)))
    const uniformCorner = average(base).lerp(neutral, mix)
    for (const channel of ['r', 'g', 'b']) {
      assert.ok(Math.abs(oldCorner[channel] - uniformCorner[channel]) < 1e-12)
    }
  }
})


test('both building materials share one selection uniform and keep a stable shader program', () => {
  const wall = new THREE.MeshStandardMaterial({ vertexColors: true, map: new THREE.Texture() })
  const roof = new THREE.MeshStandardMaterial({ vertexColors: true })
  const theme = installBuildingTheme([wall, roof])
  const compile = (material) => {
    const shader = { vertexShader: THREE.ShaderLib.standard.vertexShader, uniforms: {} }
    material.onBeforeCompile(shader)
    assert.match(shader.vertexShader, /attribute vec3 colorNight;/)
    assert.match(shader.vertexShader, /vColor\.rgb = mix\(vColor\.rgb, colorNight, uBuildingNight\);/)
    return shader
  }
  const wallShader = compile(wall)
  const roofShader = compile(roof)
  assert.strictEqual(wallShader.uniforms.uBuildingNight, roofShader.uniforms.uBuildingNight)
  const key = wall.customProgramCacheKey()
  theme.setNight(true)
  assert.equal(wallShader.uniforms.uBuildingNight.value, 1)
  assert.equal(roofShader.uniforms.uBuildingNight.value, 1)
  assert.equal(wall.customProgramCacheKey(), key)
  theme.setNight(false)
  assert.equal(wallShader.uniforms.uBuildingNight.value, 0)
  wall.map.dispose()
  wall.dispose()
  roof.dispose()
})

test('installation fails loudly if vertex colours or expected Three chunks are absent', () => {
  assert.throws(() => installBuildingTheme([new THREE.MeshStandardMaterial()]), /vertex colors/)
  const material = new THREE.MeshStandardMaterial({ vertexColors: true })
  installBuildingTheme([material])
  assert.throws(() => material.onBeforeCompile({ vertexShader: 'void main() {}', uniforms: {} }), /chunks changed/)
  material.dispose()
})
