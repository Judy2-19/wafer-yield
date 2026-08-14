import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')
const runJudgeStart = appSource.indexOf('async function runJudge()')
const runJudgeEnd = appSource.indexOf('\n}', runJudgeStart)
const runJudgeSource = appSource.slice(runJudgeStart, runJudgeEnd)

test('requires at least one enabled parameter before requesting a judgment', () => {
  assert.match(runJudgeSource, /specs\.value\.some\(\(spec\) => spec\.enabled !== false\)/)
  assert.match(runJudgeSource, /ElMessage\.warning\('请至少启用一项判定参数'\)/)
  assert.ok(
    runJudgeSource.indexOf('请至少启用一项判定参数') < runJudgeSource.indexOf('await judge('),
    'enabled-parameter validation must happen before the API request',
  )
})
