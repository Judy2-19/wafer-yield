import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')
const dialogStart = appSource.indexOf('v-model="viewSettingsDialog"')
const dialogEnd = appSource.indexOf('</el-dialog>', dialogStart)
const viewSettingsDialog = appSource.slice(dialogStart, dialogEnd)

test('view settings is a draggable non-modal live-preview tool window', () => {
  assert.notEqual(dialogStart, -1)
  assert.match(viewSettingsDialog, /\bdraggable\b/)
  assert.match(viewSettingsDialog, /:modal="false"/)
  assert.match(viewSettingsDialog, /\bmodal-penetrable\b/)
  assert.match(viewSettingsDialog, /:lock-scroll="false"/)
  assert.match(viewSettingsDialog, /v-model="viewSettings\.waferScale"/)
  assert.match(appSource, /:settings="viewSettings"/)
})

test('view setting labels use a readable dark color on the white dialog', () => {
  assert.match(appSource, /\.view-setting-row > label\s*\{[^}]*color:\s*#303133/s)
  assert.match(appSource, /\.view-setting-row > label\s*\{[^}]*font-weight:\s*500/s)
})
