import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')

test('pulls current data every 30 seconds without resetting the edited standard', () => {
  assert.match(appSource, /const AUTO_REFRESH_MS = 30_000/)
  assert.match(appSource, /autoRefreshTimer = window\.setInterval\(\(\) => \{\s*void pullLatestData\(true\)/s)
  assert.match(appSource, /window\.clearInterval\(autoRefreshTimer\)/)
  assert.match(appSource, /@click="pullLatestData\(false\)"[^>]*>拉取数据</)
})

test('shows a second-precision last update time in the map footer', () => {
  assert.match(appSource, /const lastUpdatedAt = ref<Date \| null>\(null\)/)
  assert.match(appSource, /lastUpdatedText = computed\(\(\) => \(lastUpdatedAt\.value \? fmtTime\(lastUpdatedAt\.value\) : '—'\)\)/)
  assert.match(appSource, /result\.value = await judge[\s\S]*markDataUpdated\(\)/)
  assert.match(appSource, /class="map-footer"/)
  assert.match(appSource, /最近更新：\{\{ lastUpdatedText \}\}/)
})
