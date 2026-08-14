import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const appSource = readFileSync(new URL('./App.vue', import.meta.url), 'utf8')
const apiSource = readFileSync(new URL('./api.ts', import.meta.url), 'utf8')

test('offers persistent Shot layout template selection and management', () => {
  assert.match(appSource, /v-model="layoutTemplateId"/)
  assert.match(appSource, /placeholder="选择 Map 模板"/)
  assert.match(appSource, />上传并保存 Map</)
  assert.match(appSource, /上传后自动保存为 Map 模板/)
  assert.match(appSource, /不同文件名会分别保存，同名文件重复上传会更新原模板/)
  assert.match(appSource, /当前共 \$\{layoutTemplates\.value\.length\} 个/)
  assert.match(appSource, />重命名</)
  assert.match(appSource, />删除模板</)
  assert.match(appSource, /删除后不可恢复，确定删除/)
  assert.match(appSource, /async function onLayoutTemplateChange/)
})

test('makes the Map template selector and the post-upload selection path explicit', () => {
  assert.match(appSource, /class="map-template-picker"/)
  assert.match(appSource, /class="workflow-select-label">选择 Map 模板<\/span>/)
  assert.doesNotMatch(appSource, /共 \{\{ layoutTemplates\.length \}\} 个/)
  assert.match(appSource, /no-data-text="暂无已保存的 Map 模板"/)
  assert.match(appSource, /以后从“选择 Map 模板”下拉框直接选择/)
})

test('provides layout template list select rename and delete APIs', () => {
  assert.match(apiSource, /export async function fetchLayoutTemplates/)
  assert.match(apiSource, /export async function selectLayoutTemplate/)
  assert.match(apiSource, /export async function renameLayoutTemplate/)
  assert.match(apiSource, /export async function deleteLayoutTemplate/)
})
