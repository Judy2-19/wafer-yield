import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')

test('separates system identity from the ordered query workflow', () => {
  assert.match(appSource, /class="top-summary"/)
  assert.match(appSource, /class="workflow-bar"/)
  assert.match(appSource, /<b>01<\/b>\s*筛选/)
  assert.match(appSource, /<b>02<\/b>\s*数据/)
  assert.match(appSource, />拉取数据</)
  assert.match(appSource, /<b>03<\/b>\s*执行/)
  assert.match(appSource, /\.top\s*\{[^}]*flex-direction:\s*column/s)
})

test('places connection settings beside system status and bottom-aligns all workflow steps', () => {
  assert.match(
    appSource,
    /class="system-status">[\s\S]*?class="data-config-button status-config-button"[\s\S]*?class="api-status"/,
  )
  assert.equal((appSource.match(/@click="dbDialog = true"/g) || []).length, 1)
  assert.match(appSource, /\.filter-flow,\s*\.data-flow\s*\{[^}]*align-items:\s*flex-end/s)
  assert.match(
    appSource,
    /\.action-flow\s*\{[^}]*align-items:\s*flex-end[^}]*align-self:\s*flex-end/s,
  )
})

test('keeps the wafer and parameter template selectors wide enough to read', () => {
  assert.match(appSource, /\.wafer-filter\s*\{[^}]*width:\s*170px\s*!important/s)
  assert.match(appSource, /\.template-filter\s*\{[^}]*width:\s*230px\s*!important/s)
  assert.match(appSource, /\.filter-flow\s+\.el-select\s*\{[^}]*flex-shrink:\s*0/s)
})

test('labels the wafer parameter and Map selectors consistently', () => {
  assert.match(appSource, /class="workflow-select-label">选择 Wafer<\/span>[\s\S]*?class="wafer-filter"/)
  assert.match(appSource, /class="workflow-select-label">选择参数模板<\/span>[\s\S]*?class="template-filter"/)
  assert.match(appSource, /class="workflow-select-label">选择 Map 模板<\/span>[\s\S]*?class="layout-template-filter"/)
  assert.match(appSource, /\.workflow-select-label\s*\{[^}]*font-size:\s*10px[^}]*font-weight:\s*700/s)
  assert.doesNotMatch(appSource, /共 \{\{ layoutTemplates\.length \}\} 个/)
})

test('gives the wafer map a visibly larger center column and sizes it from that column', () => {
  assert.match(
    appSource,
    /grid-template-columns:\s*minmax\(0,\s*0\.94fr\)\s+minmax\(0,\s*1\.18fr\)\s+minmax\(0,\s*0\.88fr\)/,
  )
  assert.match(appSource, /const centerColumnShare = 1\.18 \/ \(0\.94 \+ 1\.18 \+ 0\.88\)/)
  assert.match(appSource, /querySelector<HTMLElement>\('\.top'\)\?\.offsetHeight/)
  assert.match(appSource, /const stacked = w < 1600/)
  assert.match(appSource, /@media \(max-width: 1599px\)/)
  assert.match(appSource, /\.workflow-bar\s*\{[^}]*flex-wrap:\s*wrap/s)
  assert.match(appSource, /<i class="dot missing" \/>未测试/)
})

test('enlarges typography only inside the configuration and statistics panels', () => {
  assert.match(appSource, /<section class="panel config-panel">/)
  assert.match(appSource, /\.config-panel h2,\s*\.stats-panel h2\s*\{[^}]*font-size:\s*16px/s)
  assert.match(appSource, /\.config-panel :deep\(\.el-table \.cell\),\s*\.stats-panel :deep\(\.el-table \.cell\)\s*\{[^}]*font-size:\s*14px/s)
  assert.match(appSource, /\.stats-panel \.stats label\s*\{[^}]*font-size:\s*13px/s)
  assert.match(appSource, /\.stats-panel \.stats strong\s*\{[^}]*font-size:\s*24px/s)
  assert.doesNotMatch(appSource, /\.map-panel[^}]*font-size:\s*(?:14|16|24)px/s)
})
