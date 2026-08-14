import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')

test('describes the judgment rule as a strict open interval', () => {
  assert.match(appSource, /全部启用参数满足 Min＜值＜Max 才为良品/)
  assert.doesNotMatch(appSource, /Min≤值≤Max/)
})
