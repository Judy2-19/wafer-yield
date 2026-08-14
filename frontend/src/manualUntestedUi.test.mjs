import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')
const apiSource = readFileSync(new URL('./api.ts', import.meta.url), 'utf8')

test('die picker distinguishes manual untested and owns both state actions', () => {
  const pickerStart = appSource.indexOf('v-model="shotPickDialog"')
  const detailStart = appSource.indexOf('v-model="dieDialog"')
  const pickerSource = appSource.slice(pickerStart, detailStart)
  const detailSource = appSource.slice(detailStart)

  assert.match(pickerSource, /未测试\(人为\)/)
  assert.match(pickerSource, /设为未测试/)
  assert.match(pickerSource, /恢复已测试/)
  assert.match(pickerSource, /toggleDieManualUntested\(cell\.serial\)/)
  assert.doesNotMatch(detailSource, /@click="toggleDieManualUntested/)
})

test('frontend calls the persistent manual untested endpoint', () => {
  assert.match(apiSource, /setDieManualUntested/)
  assert.match(apiSource, /manual-untested/)
})

test('setting a die untested requires confirmation and explains statistics impact', () => {
  assert.match(appSource, /确定设为未测试吗？/)
  assert.match(appSource, /确定后，计算不良率时将不统计该 Die。/)
  assert.match(appSource, /confirmButtonText:\s*'确定'/)
  assert.match(appSource, /cancelButtonText:\s*'取消'/)
})
