import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')
const dialogStart = appSource.indexOf('v-model="shotPickDialog"')
const dialogEnd = appSource.indexOf('</el-dialog>', dialogStart)
const dialogSource = appSource.slice(dialogStart, dialogEnd)

test('uses a compact Die picker without the explanatory paragraph', () => {
  assert.match(dialogSource, /width="min\(560px, 92vw\)"/)
  assert.doesNotMatch(dialogSource, /class="die-pick-tip"/)
  assert.match(dialogSource, /class="die-status-legend"/)
  assert.doesNotMatch(dialogSource, />无数据</)
  assert.match(dialogSource, />未测试</)
  assert.match(appSource, /\.die-cell\s*\{[^}]*min-height:\s*64px/s)
})

test('renders four saturated and distinct Die states', () => {
  assert.match(appSource, /return 'die-cell test-key'/)
  assert.match(appSource, /\.die-cell\.pass\s*\{[^}]*background:\s*#00c853/s)
  assert.match(appSource, /\.die-cell\.fail\s*\{[^}]*background:\s*#ff3d3d/s)
  assert.match(appSource, /\.die-cell\.missing\s*\{[^}]*background:\s*#cbd5e1/s)
  assert.match(appSource, /\.die-cell\.missing\s*\{[^}]*color:\s*#334155/s)
  assert.match(appSource, /\.die-cell\.manual-untested\s*\{[^}]*background:\s*#94a3b8/s)
  assert.match(appSource, /\.die-cell\.test-key\s*\{[^}]*background:\s*#ffd600/s)
})
