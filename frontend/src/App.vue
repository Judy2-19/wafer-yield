<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import WaferMapView, { type WaferCoord } from './components/WaferMapView.vue'
import {
  deleteTemplate,
  ensureApiReady,
  exportExcel,
  fetchItemNames,
  fetchTemplates,
  fetchWafers,
  forceMockMode,
  getApiBase,
  getDbConfig,
  judge,
  saveDbConfig,
  saveJudge,
  saveTemplate,
  testDb,
  type DieGridCell,
  type DiePayload,
  type JudgeResult,
  type ShotSummary,
  type SpecItem,
  type WaferInfo,
} from './api'

type TemplateItem = { id: string; name: string; specs: SpecItem[]; builtin?: boolean }

const UI_STATE_KEY = 'wafer-yield-ui-state'

/** 深拷贝规格，避免 Vue Proxy 导致 structuredClone 失败，并避免模板间串改 */
function cloneSpecs(list: SpecItem[] | undefined | null): SpecItem[] {
  const plain = JSON.parse(JSON.stringify(list || [])) as SpecItem[]
  return plain.map((s) => ({
    ...s,
    lsl: s.lsl ?? null,
    lsl_4v: s.lsl_4v ?? null,
    usl: s.usl ?? null,
    usl_4v: s.usl_4v ?? (s.name === 'MPD Dark Current' ? 200 : null),
    target: s.target ?? null,
    custom: !!s.custom,
    enabled: s.enabled !== false,
  }))
}

function loadUiState(): { templateId?: string; wafer?: string } {
  try {
    return JSON.parse(localStorage.getItem(UI_STATE_KEY) || '{}')
  } catch {
    return {}
  }
}

function persistUiState() {
  localStorage.setItem(
    UI_STATE_KEY,
    JSON.stringify({
      templateId: templateId.value,
      wafer: wafer.value,
    }),
  )
}

function applyTemplateById(id: string, list?: TemplateItem[]) {
  const source = list || templates.value
  const tpl = source.find((x) => x.id === id) || source[0]
  if (!tpl) return
  templateId.value = tpl.id
  // 始终用独立副本，编辑只影响当前 specs，不写回其它模板内存
  specs.value = cloneSpecs(tpl.specs)
  persistUiState()
}

const wafers = ref<WaferInfo[]>([])
const wafer = ref('')
const timeRange = ref<[Date, Date] | null>(null)
const templates = ref<TemplateItem[]>([])
const templateId = ref('dr8-pic')
const specs = ref<SpecItem[]>([])
const result = ref<JudgeResult | null>(null)
const loading = ref(false)

function fmtTime(d: Date | null | undefined) {
  if (!d) return null
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function currentTimeRange() {
  if (!timeRange.value) return { start: null as string | null, end: null as string | null }
  return { start: fmtTime(timeRange.value[0]), end: fmtTime(timeRange.value[1]) }
}

const saveTplDialog = ref(false)
const saveTplName = ref('')
const saveTplMode = ref<'saveAs' | 'update'>('saveAs')

const dbDialog = ref(false)
const dbForm = ref({
  host: '127.0.0.1',
  port: 3306,
  database: 'mg_nano',
  user: 'root',
  password: '',
  use_mock: true,
})

const dieDialog = ref(false)
const selectedDie = ref<DiePayload | null>(null)
const shotPickDialog = ref(false)
const selectedShot = ref<ShotSummary | null>(null)
const childDialog = ref(false)
const childTitle = ref('')
const childRows = ref<
  Array<{
    item?: string
    name?: string
    value?: number | null
    unit?: string
    min?: number | null
    max?: number | null
    pass?: boolean
    note?: string
    is_group?: boolean
    condition?: string
    children?: Array<{
      item?: string
      name?: string
      value?: number | null
      unit?: string
      min?: number | null
      max?: number | null
      pass?: boolean
      note?: string
    }>
  }>
>([])

function openGroupItems(group: (typeof childRows.value)[number], parentLabel?: string) {
  const items = group.children || []
  if (!items.length) return
  childTitle.value = `${parentLabel || 'MPD Dark Current'} · ${group.item || group.name} — 全部实测`
  childRows.value = items
  childDialog.value = true
}

function formatLimitCell(
  row: { is_overall?: boolean; min?: number | string | null; max?: number | string | null; lsl?: number | null; usl?: number | null },
  kind: 'min' | 'max',
) {
  if (row.is_overall) return '—'
  const v = kind === 'min' ? row.min ?? row.lsl : row.max ?? row.usl
  if (typeof v === 'string') return v
  return formatLimit(v)
}

function isMpdSpec(row: { name?: string; key?: string }) {
  return row.name === 'MPD Dark Current' || row.key === 'MPD Dark Current'
}

const addDialog = ref(false)
const dbItems = ref<Array<{ name: string; unit?: string | null }>>([])
const selectedItemNames = ref<string[]>([])
const loadingItems = ref(false)

const existingSpecNames = computed(() => new Set(specs.value.map((s) => s.name)))
const availableDbItems = computed(() =>
  dbItems.value.filter((it) => !existingSpecNames.value.has(it.name)),
)
const currentTemplate = computed(() => templates.value.find((t) => t.id === templateId.value))
const isBuiltinTemplate = computed(() => !!currentTemplate.value?.builtin || templateId.value === 'dr8-pic')

const dieById = computed(() => {
  const map = new Map<string, DiePayload>()
  for (const d of result.value?.dies || []) {
    if (d.id) map.set(d.id, d)
  }
  return map
})

const shotByKey = computed(() => {
  const map = new Map<string, ShotSummary>()
  for (const s of result.value?.shots || []) {
    map.set(s.shot, s)
    if (s.x != null && s.y != null) map.set(`${s.x},${s.y}`, s)
  }
  return map
})

function shotMapColor(s: ShotSummary) {
  // 仅两种：全部 Die Pass → 绿；否则 → 红
  return s.die_count > 0 && s.pass ? '#2ecc71' : '#e74c3c'
}

const mapGrid = computed(() => {
  const g = result.value?.map_grid
  const shots = (result.value?.shots || []).filter((s) => s.x != null && s.y != null)
  if (shots.length) {
    const xs = shots.map((s) => s.x as number)
    const ys = shots.map((s) => s.y as number)
    // 按 SN 坐标自适应；略扩边，避免单点撑满圆片
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const padX = maxX === minX ? 2 : 0
    const padY = maxY === minY ? 2 : 0
    return {
      minX: minX - padX,
      maxX: maxX + padX,
      minY: minY - padY,
      maxY: maxY + padY,
    }
  }
  if (g) {
    return { minX: g.min_x, maxX: g.max_x, minY: g.min_y, maxY: g.max_y }
  }
  return { minX: 0, maxX: 9, minY: 0, maxY: 7 }
})

const coords = computed<WaferCoord[]>(() =>
  (result.value?.shots || [])
    .filter((s) => s.x != null && s.y != null)
    .map((s) => ({
      x: s.x as number,
      y: s.y as number,
      shot: s.shot,
      color: shotMapColor(s),
      info: [`${s.shot}`, s.coord_label || `(${s.x},${s.y})`],
    })),
)

const stats = computed(() => result.value?.stats)

const dieGrid = computed<DieGridCell[]>(() => result.value?.die_grid || [])

const selectedShotDieMap = computed(() => {
  const map = new Map<string, NonNullable<ShotSummary['dies']>[number]>()
  for (const d of selectedShot.value?.dies || []) {
    if (d.serial) map.set(d.serial, d)
  }
  return map
})

async function reloadWafers(keepSelection = true) {
  const prev = wafer.value
  const list = await fetchWafers(currentTimeRange())
  wafers.value = list
  const names = list.map((x) => x.wafer)
  if (keepSelection && prev && names.includes(prev)) {
    wafer.value = prev
  } else {
    wafer.value = names[0] || ''
  }
}

const apiStatus = ref('')

async function bootstrap() {
  try {
    const base = await ensureApiReady()
    apiStatus.value = `后端已连接: ${base}`

    const savedUi = loadUiState()
    let w: WaferInfo[] = []
    let cfg: Record<string, unknown> = {}
    try {
      ;[w, cfg] = await Promise.all([fetchWafers(), getDbConfig()])
    } catch {
      // 常见原因：误关 Mock / MySQL 不通 → 自动切回 Mock 再试
      await forceMockMode()
      ;[w, cfg] = await Promise.all([fetchWafers(), getDbConfig()])
      ElMessage.warning('数据库不可用，已自动切换为 Mock 样例数据')
    }
    const t = await fetchTemplates()
    wafers.value = w
    templates.value = t.map((tpl) => ({
      ...tpl,
      specs: cloneSpecs(tpl.specs),
    }))

    const names = w.map((x) => x.wafer)
    if (names.length) {
      wafer.value = savedUi.wafer && names.includes(savedUi.wafer) ? savedUi.wafer : names[0]
    }

    const preferId = savedUi.templateId || 'dr8-pic'
    applyTemplateById(preferId, templates.value)

    dbForm.value = {
      host: (cfg.host as string) ?? '127.0.0.1',
      port: (cfg.port as number) ?? 3306,
      database: (cfg.database as string) ?? 'mg_nano',
      user: (cfg.user as string) ?? 'root',
      password: '',
      use_mock: (cfg.use_mock as boolean) ?? true,
    }
    if (!names.length) {
      ElMessage.warning('后端已通，但无晶圆数据。请确认项目含 mock/eav_rows.json，或配置 MySQL。')
    }
    if (wafer.value) await runJudge()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    apiStatus.value = `后端未连接 (${getApiBase()})`
    ElMessage.error(msg)
  }
}

function onTemplateChange(id: string) {
  applyTemplateById(id)
  runJudge()
}

async function onWaferChange() {
  persistUiState()
  await runJudge()
}

async function onTimeRangeChange() {
  try {
    await reloadWafers(true)
    await runJudge()
  } catch (e: unknown) {
    ElMessage.error(`按时间筛选失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

async function openAddFromDb() {
  addDialog.value = true
  selectedItemNames.value = []
  loadingItems.value = true
  try {
    dbItems.value = await fetchItemNames(wafer.value || undefined)
  } catch (e: unknown) {
    ElMessage.error(`读取 ItemName 失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    loadingItems.value = false
  }
}

function confirmAddItems() {
  if (!selectedItemNames.value.length) {
    ElMessage.warning('请先选择要添加的 ItemName')
    return
  }
  const unitMap = new Map(dbItems.value.map((i) => [i.name, i.unit]))
  for (const name of selectedItemNames.value) {
    if (existingSpecNames.value.has(name)) continue
    specs.value.push({
      name,
      display_name: name,
      condition: '',
      lsl: null,
      target: null,
      usl: null,
      enabled: true,
      unit: unitMap.get(name) ?? null,
      note: '',
      custom: true,
    })
  }
  addDialog.value = false
  ElMessage.success(`已添加 ${selectedItemNames.value.length} 项，请设置 Min/Max 后点刷新`)
}

function removeSpec(index: number) {
  const row = specs.value[index]
  if (!row?.custom) {
    ElMessage.warning('标准规格项不可删除，可关闭「启用」')
    return
  }
  specs.value.splice(index, 1)
}

async function runJudge() {
  if (!wafer.value) return
  persistUiState()
  loading.value = true
  try {
    result.value = await judge(wafer.value, cloneSpecs(specs.value), currentTimeRange())
    const dq = (
      result.value as {
        data_quality?: {
          valued_test_count?: number
          sample?: string[]
          fetch?: { valued_itemvalue?: number; eav_1311?: number; head_rows?: number }
        }
      }
    )?.data_quality
    const fetchValued = dq?.fetch?.valued_itemvalue ?? 0
    const shownValued = dq?.valued_test_count ?? 0
    if (shownValued === 0 && fetchValued === 0) {
      ElMessage.warning(
        `Wafer「${wafer.value}」在 WaveLength=1311 下未读到 ItemValue。请改选 UMU/DR4 片号（不要选 32(4,7) 这类错位数据）。`,
      )
    } else if (shownValued === 0 && fetchValued > 0) {
      ElMessage.warning(
        `库中已读到 ${fetchValued} 条 ItemValue，但未能生成 Die/Note。请重新点「判定」或换一片 UMU/DR4。`,
      )
    }
  } catch (e: unknown) {
    ElMessage.error(`判定失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    loading.value = false
  }
}

const mpdExpandKeys = ref<string[]>(['MPD Dark Current'])

function onDetailExpand(_row: { key?: string }, expanded: Array<{ key?: string }>) {
  mpdExpandKeys.value = expanded.map((r) => r.key || '').filter(Boolean)
}

const viewportH = ref(typeof window !== 'undefined' ? window.innerHeight : 900)
const childTableHeight = computed(() => Math.max(240, Math.min(viewportH.value - 160, 560)))

/** 点击图谱 Shot → 选择 Die */
function openShot(coord: WaferCoord) {
  const shot =
    (coord.shot && shotByKey.value.get(coord.shot)) ||
    shotByKey.value.get(`${coord.x},${coord.y}`)
  if (!shot) {
    ElMessage.warning('未找到该 Shot 下的 Die 数据')
    return
  }
  selectedShot.value = shot
  shotPickDialog.value = true
}

/** 选择具体 Die → 芯片详情 */
function openChipDie(serial: string | null) {
  if (!serial || !selectedShot.value) return
  const brief = selectedShotDieMap.value.get(serial)
  if (!brief?.id) {
    ElMessage.info(`流水号 ${serial} 无数据`)
    return
  }
  const die = dieById.value.get(brief.id)
  if (!die) {
    ElMessage.warning('未找到该 Die 的判定详情')
    return
  }
  selectedDie.value = die
  mpdExpandKeys.value = ['MPD Dark Current']
  viewportH.value = window.innerHeight
  shotPickDialog.value = false
  dieDialog.value = true
}

function dieCellClass(serial: string | null) {
  if (!serial) return 'die-cell empty'
  const d = selectedShotDieMap.value.get(serial)
  if (!d) return 'die-cell missing'
  return d.pass ? 'die-cell pass' : 'die-cell fail'
}

/** 从 SN 中取出 4 位流水号 */
function extractSerial(sn?: string | null, serial?: string | null) {
  if (serial && /^\d{4}$/.test(serial)) return serial
  if (!sn) return null
  const m = String(sn).match(/SN\s*(\d{4})/i) || String(sn).match(/(\d{4})\s*$/)
  return m ? m[1] : null
}

/** 统一展示名：例 49SN0202（不使用库内原始 SN，避免乱码） */
function formatDieName(shot?: string | null, serial?: string | null, sn?: string | null) {
  const ser = extractSerial(sn, serial)
  if (!shot || !ser) return ser || shot || '—'
  return `${shot}SN${ser}`
}

function dieCellLabel(serial: string | null) {
  if (!serial || !selectedShot.value) return serial || ''
  // 有数据/无数据都走同一规则，绝不直接显示后端 label / 原始 SN
  return formatDieName(selectedShot.value.shot, serial)
}

const chipDieTitle = computed(() => {
  const d = selectedDie.value
  if (!d) return ''
  return formatDieName(d.shot, d.serial, d.sn)
})

function resultText(pass: boolean | null | undefined) {
  if (pass === true) return 'Pass'
  if (pass === false) return 'Fail'
  return '—'
}

/** Note 只展示实测，去掉可能残留的 Pass/Fail 字样 */
function noteOnly(text: string | null | undefined) {
  if (!text) return ''
  const cleaned = String(text)
    .replace(/[；;|,]?\s*(总体[=＝])?\s*(Pass|Fail|PASS|FAIL)\b/gi, '')
    .replace(/\b(1\.0V|4\.0V)\s*[=＝]\s*(Pass|Fail)\b/gi, '$1')
    .replace(/[；;]\s*$/g, '')
    .replace(/^\s*[；;]\s*/g, '')
    .trim()
  return cleaned
}

/** 详情 Note：优先 note 文案，其次数值 value，避免连库后空白 */
function formatDetailNote(row: {
  note?: string | null
  value?: number | string | null
  db_hint?: string | null
}) {
  const fromNote = noteOnly(row.note)
  if (fromNote && fromNote !== '—' && fromNote !== '-') return fromNote
  if (row.value != null && row.value !== '' && Number.isFinite(Number(row.value))) {
    return `实测 ${Number(row.value)}`
  }
  if (row.db_hint) return `无实测（期望库字段: ${row.db_hint}）`
  return '无实测'
}

function openSaveAsTemplate() {
  saveTplMode.value = 'saveAs'
  const base = currentTemplate.value?.name?.replace(/（默认）$/, '') || '客户标准'
  saveTplName.value = `${base}-副本`
  saveTplDialog.value = true
}

function openUpdateTemplate() {
  if (isBuiltinTemplate.value) {
    ElMessage.warning('默认模板不可覆盖，请使用「另存为新模板」')
    return
  }
  saveTplMode.value = 'update'
  saveTplName.value = currentTemplate.value?.name || ''
  saveTplDialog.value = true
}

function makeTemplateId(name: string) {
  const slug = name
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^\w\u4e00-\u9fff-]/g, '')
    .slice(0, 40)
  return `tpl-${slug || 'custom'}-${Date.now().toString(36)}`
}

async function confirmSaveTemplate() {
  const name = saveTplName.value.trim()
  if (!name) {
    ElMessage.warning('请填写模板名称，例如：客户A标准')
    return
  }
  // 只提交当前编辑副本的纯数据，绝不改动其它模板
  const payloadSpecs = cloneSpecs(specs.value)
  try {
    if (saveTplMode.value === 'saveAs') {
      const id = makeTemplateId(name)
      await saveTemplate({ id, name, specs: payloadSpecs })
      const list = await fetchTemplates()
      templates.value = list.map((tpl) => ({ ...tpl, specs: cloneSpecs(tpl.specs) }))
      applyTemplateById(id, templates.value)
      ElMessage.success(`已另存为「${name}」，默认及其它模板未改动`)
    } else {
      const id = templateId.value
      if (id === 'dr8-pic') {
        ElMessage.warning('默认模板不可覆盖，请另存为新模板')
        return
      }
      await saveTemplate({ id, name, specs: payloadSpecs })
      const list = await fetchTemplates()
      templates.value = list.map((tpl) => ({
        ...tpl,
        // 仅当前 id 用刚保存的内容；其它模板保持服务端原样
        specs: tpl.id === id ? cloneSpecs(payloadSpecs) : cloneSpecs(tpl.specs),
      }))
      applyTemplateById(id, templates.value)
      ElMessage.success(`已更新「${name}」，其它模板未改动`)
    }
    saveTplDialog.value = false
    persistUiState()
  } catch (e: unknown) {
    const msg =
      (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
      (e instanceof Error ? e.message : String(e))
    ElMessage.error(`保存失败: ${msg}`)
  }
}

async function onDeleteTemplate() {
  if (isBuiltinTemplate.value) {
    ElMessage.warning('默认模板不可删除')
    return
  }
  const name = currentTemplate.value?.name || templateId.value
  const deletingId = templateId.value
  try {
    await deleteTemplate(deletingId)
    const list = await fetchTemplates()
    templates.value = list.map((tpl) => ({ ...tpl, specs: cloneSpecs(tpl.specs) }))
    applyTemplateById('dr8-pic', templates.value)
    ElMessage.success(`已删除模板「${name}」，已切回默认标准`)
    await runJudge()
  } catch (e: unknown) {
    ElMessage.error(`删除失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

async function onSaveResult() {
  if (!result.value) return
  await saveJudge(result.value.wafer, result.value)
  ElMessage.success('判定结果已保存到本地')
}

async function onExport() {
  if (!result.value) return
  const blob = await exportExcel(result.value)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${result.value.wafer}_judge.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}

async function onTestDb() {
  const res = await testDb(dbForm.value)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.error(res.message)
}

async function onSaveDb() {
  await saveDbConfig(dbForm.value)
  ElMessage.success('数据库配置已保存')
  dbDialog.value = false
  await reloadWafers(true)
  await runJudge()
}

function passLabel(v: boolean | null | undefined) {
  if (v === true) return 'Pass'
  if (v === false) return 'Fail'
  return '-'
}

function formatLimit(v: number | null | undefined) {
  if (v === null || v === undefined) return '—'
  return Number(v).toString()
}

function dieRowClass({ row }: { row: { key?: string; name?: string; is_overall?: boolean } }) {
  if (row.key === 'MPD Dark Current') return 'mpd-row'
  return row.is_overall || row.name === '总体评价' ? 'overall-row' : ''
}

/** 按视口计算，保证三栏同屏无滚动 */
const mapSize = ref(320)
const specsTableHeight = ref(360)
const failTableHeight = ref(180)

function updateLayout() {
  const w = window.innerWidth
  const h = window.innerHeight
  const pagePad = 16
  const headerH = 52
  const gap = 10
  const panelPad = 20
  const panelHead = 36
  const availableH = h - pagePad - headerH - gap
  const colW = (w - pagePad - gap * 2) / 3

  specsTableHeight.value = Math.max(220, availableH - panelPad - panelHead)
  // 统计区：标题 + 4 卡片 + 小标题
  failTableHeight.value = Math.max(120, availableH - panelPad - panelHead - 96 - 28)
  const mapByW = Math.floor(colW - panelPad - 8)
  const mapByH = availableH - panelPad - panelHead - 22
  mapSize.value = Math.max(200, Math.min(mapByW, mapByH))
}

function onWinResize() {
  updateLayout()
  viewportH.value = window.innerHeight
}

onMounted(() => {
  updateLayout()
  viewportH.value = window.innerHeight
  window.addEventListener('resize', onWinResize)
  bootstrap()
})
onUnmounted(() => {
  window.removeEventListener('resize', onWinResize)
})
</script>

<template>
  <div class="page">
    <header class="top">
      <div class="top-title">
        <h1>判定规则配置</h1>
        <span class="logic">全部启用参数满足 Min≤值≤Max 才为良品</span>
      </div>
      <div class="top-actions">
        <el-date-picker
          v-model="timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="CreateTime 起"
          end-placeholder="CreateTime 止"
          format="YYYY-MM-DD HH:mm"
          style="width: 340px"
          clearable
          @change="onTimeRangeChange"
        />
        <el-select
          v-model="wafer"
          style="width: 160px"
          placeholder="Wafer"
          filterable
          @change="onWaferChange"
        >
          <el-option
            v-for="w in wafers"
            :key="w.wafer"
            :label="w.wafer"
            :value="w.wafer"
          />
        </el-select>
        <el-select v-model="templateId" style="width: 180px" placeholder="客户标准" @change="onTemplateChange">
          <el-option
            v-for="t in templates"
            :key="t.id"
            :label="t.builtin ? `[默认] ${t.name}` : t.name"
            :value="t.id"
          />
        </el-select>
        <el-button type="primary" @click="dbDialog = true">数据连接</el-button>
        <el-button type="success" :loading="loading" @click="runJudge">确认 / 刷新</el-button>
        <el-button size="small" @click="bootstrap">重连后端</el-button>
      </div>
      <div v-if="apiStatus" class="api-status">{{ apiStatus }}</div>
    </header>

    <main class="grid">
      <section class="panel">
        <div class="panel-head">
          <h2>参数配置</h2>
          <div class="panel-actions">
            <el-button size="small" @click="openAddFromDb">添加</el-button>
            <el-button size="small" type="primary" @click="openSaveAsTemplate">另存</el-button>
            <el-button size="small" :disabled="isBuiltinTemplate" @click="openUpdateTemplate">更新</el-button>
            <el-button size="small" type="danger" plain :disabled="isBuiltinTemplate" @click="onDeleteTemplate">
              删除
            </el-button>
          </div>
        </div>
        <el-table :data="specs" :height="specsTableHeight" size="small" class="dark-table grow-table">
          <el-table-column label="启用" width="48">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="Item" min-width="100">
            <template #default="{ row }">
              <span class="item-name">{{ row.display_name || row.name }}</span>
              <el-tag v-if="row.custom" size="small" type="warning" class="tag-custom">自定义</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Min" width="110">
            <template #default="{ row }">
              <div v-if="isMpdSpec(row)" class="mpd-limits">
                <span class="mpd-vtag">1V</span>
                <el-input-number v-model="row.lsl" :controls="false" size="small" class="mpd-num" placeholder="—" />
                <span class="mpd-vtag v4">4V</span>
                <el-input-number v-model="row.lsl_4v" :controls="false" size="small" class="mpd-num" placeholder="—" />
              </div>
              <el-input-number v-else v-model="row.lsl" :controls="false" size="small" class="num" />
            </template>
          </el-table-column>
          <el-table-column label="Max" width="110">
            <template #default="{ row }">
              <div v-if="isMpdSpec(row)" class="mpd-limits">
                <span class="mpd-vtag">1V</span>
                <el-input-number v-model="row.usl" :controls="false" size="small" class="mpd-num" />
                <span class="mpd-vtag v4">4V</span>
                <el-input-number v-model="row.usl_4v" :controls="false" size="small" class="mpd-num" />
              </div>
              <el-input-number v-else v-model="row.usl" :controls="false" size="small" class="num" />
            </template>
          </el-table-column>
          <el-table-column label="" width="36">
            <template #default="{ $index, row }">
              <el-button
                v-if="row.custom"
                link
                type="danger"
                size="small"
                @click="removeSpec($index)"
              >
                删
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel map-panel">
        <div class="panel-head">
          <h2>晶圆图谱</h2>
          <div class="legend">
            <span><i class="dot pass" />Pass</span>
            <span><i class="dot fail" />Fail</span>
          </div>
        </div>
          <div class="map-wrap">
            <WaferMapView
              v-if="coords.length"
              :coords="coords"
              :fixed-grid="mapGrid"
              :size="mapSize"
              notch="top"
              background-color="#3a7ca5"
              @die-click="openShot"
            />
            <div v-else class="empty">
              暂无数据。请点右上角「数据连接」→ 打开「Mock 模式」→「保存并加载」。
              若要用真库，关闭 Mock 并填好 MySQL 后测试连接。
            </div>
          </div>
          <p class="hint">点击 Shot → 选择 Die → 查看芯片详情</p>
        </section>

      <section class="panel stats-panel">
        <div class="panel-head">
          <h2>统计结果</h2>
          <div class="footer-actions inline">
            <el-button size="small" @click="onSaveResult" :disabled="!result">保存</el-button>
            <el-button size="small" type="primary" @click="onExport" :disabled="!result">导出</el-button>
          </div>
        </div>
        <div class="stats" v-if="stats">
          <div><label>Total Dies</label><strong>{{ stats.total }}</strong></div>
          <div><label>Pass Dies</label><strong class="pass-text">{{ stats.pass_count }}</strong></div>
          <div><label>Fail Dies</label><strong class="fail-text">{{ stats.fail_count }}</strong></div>
          <div><label>Yield</label><strong>{{ stats.yield }}%</strong></div>
        </div>
        <div v-else class="stats stats-empty">
          <div><label>Total Dies</label><strong>—</strong></div>
          <div><label>Pass Dies</label><strong>—</strong></div>
          <div><label>Fail Dies</label><strong>—</strong></div>
          <div><label>Yield</label><strong>—</strong></div>
        </div>
        <h3>不良率详情（按 Die）</h3>
        <el-table
          :data="stats?.fail_rate_details || []"
          size="small"
          :height="failTableHeight"
          class="dark-table grow-table"
        >
          <el-table-column prop="name" label="参数" min-width="90" show-overflow-tooltip />
          <el-table-column prop="fail_count" label="不良" width="56" />
          <el-table-column label="不良率" width="64">
            <template #default="{ row }">{{ row.fail_rate }}%</template>
          </el-table-column>
        </el-table>
      </section>
    </main>

    <el-dialog
      v-model="shotPickDialog"
      :title="selectedShot ? `选择 Die · Shot ${selectedShot.shot}# ${selectedShot.coord_label || ''}` : '选择 Die'"
      width="720px"
      align-center
      destroy-on-close
    >
      <p class="die-pick-tip">
        布局 3×6（0203 空缺）。名称如 49SN0202。Shot 仅当全部 Die Pass 才算 Pass。
        <span v-if="selectedShot">
          共 {{ selectedShot.die_count }} 颗 · Pass {{ selectedShot.pass_count }} · Fail
          {{ selectedShot.fail_count }} · Shot
          {{ selectedShot.pass ? 'Pass' : 'Fail' }}
        </span>
      </p>
      <div class="die-grid">
        <button
          v-for="cell in dieGrid"
          :key="`${cell.row}-${cell.col}`"
          type="button"
          :class="dieCellClass(cell.serial)"
          :disabled="cell.empty || !cell.serial || !selectedShotDieMap.get(cell.serial)"
          :title="cell.serial ? dieCellLabel(cell.serial) : ''"
          @click="openChipDie(cell.serial)"
        >
          <template v-if="cell.empty">—</template>
          <template v-else>
            <strong class="die-full-label">{{ dieCellLabel(cell.serial) }}</strong>
            <small v-if="selectedShotDieMap.get(cell.serial!)">
              {{ selectedShotDieMap.get(cell.serial!)?.pass ? 'Pass' : 'Fail' }}
            </small>
            <small v-else class="miss">无数据</small>
          </template>
        </button>
      </div>
    </el-dialog>

    <el-dialog
      v-model="dieDialog"
      :title="`芯片详情 Die · ${chipDieTitle}`"
      width="96vw"
      top="2vh"
      class="die-dialog"
      align-center
      destroy-on-close
    >
      <div class="die-dialog-body">
        <p v-if="selectedDie" class="die-meta">
          Die {{ chipDieTitle }} ·
          Shot {{ selectedDie.shot }}# ·
          坐标 ({{ selectedDie.x }}, {{ selectedDie.y }}) ·
          流水号 {{ extractSerial(selectedDie.sn, selectedDie.serial) || '—' }}
          <template v-if="selectedDie.create_time"> · CreateTime {{ selectedDie.create_time }}</template>
          ·
          总体评价
          <el-tag :type="selectedDie.pass ? 'success' : 'danger'" size="small">
            {{ selectedDie.pass ? 'Pass' : 'Fail' }}
          </el-tag>
          <span class="die-tip">（全部 Item 均为 Pass 才为 Pass）</span>
        </p>
        <el-table
          :data="selectedDie?.param_rows || []"
          size="small"
          :row-class-name="dieRowClass"
          class="detail-table"
          row-key="key"
          :expand-row-keys="mpdExpandKeys"
          @expand-change="onDetailExpand"
        >
          <el-table-column type="expand" width="24">
            <template #default="{ row }">
              <div v-if="row.key === 'MPD Dark Current' && row.children?.length" class="mpd-under">
                <div v-for="g in row.children" :key="g.key || g.item" class="mpd-under-row">
                  <button type="button" class="item-link" @click="openGroupItems(g, row.item)">
                    {{ g.item || g.name }}
                  </button>
                  <span class="cond" v-html="g.condition || ''"></span>
                  <span class="mpd-range">
                    Min {{ formatLimit(g.min) }} · Max {{ formatLimit(g.max) }}
                    <small>{{ g.unit || 'nA' }}</small>
                  </span>
                  <span class="note-text">{{ noteOnly(g.note) }}</span>
                  <span :class="g.pass ? 'note-pass' : 'note-fail'">{{ resultText(g.pass) }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Item" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.item || row.name }}</template>
          </el-table-column>
          <el-table-column label="Condition" min-width="160">
            <template #default="{ row }">
              <span class="cond" v-html="row.condition || ''"></span>
            </template>
          </el-table-column>
          <el-table-column label="Unit" width="56">
            <template #default="{ row }">{{ row.unit || '—' }}</template>
          </el-table-column>
          <el-table-column label="Min" min-width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ formatLimitCell(row, 'min') }}</template>
          </el-table-column>
          <el-table-column label="Target" width="60">
            <template #default="{ row }">
              {{ row.is_overall || isMpdSpec(row) ? '—' : formatLimit(row.target) }}
            </template>
          </el-table-column>
          <el-table-column label="Max" min-width="110" show-overflow-tooltip>
            <template #default="{ row }">{{ formatLimitCell(row, 'max') }}</template>
          </el-table-column>
          <el-table-column label="Note" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="note-text">{{ formatDetailNote(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结果" width="64" align="center" fixed="right">
            <template #default="{ row }">
              <span :class="row.pass ? 'note-pass' : 'note-fail'">{{ resultText(row.pass) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-dialog>

    <el-dialog
      v-model="childDialog"
      :title="childTitle"
      width="min(720px, 96vw)"
      top="4vh"
      append-to-body
      class="child-dialog"
    >
      <el-table :data="childRows" size="small" :height="childTableHeight" class="child-table">
        <el-table-column label="ItemName" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.item || row.name }}</template>
        </el-table-column>
        <el-table-column label="Note / 实测" min-width="120">
          <template #default="{ row }">
            <span class="note-text">{{ formatDetailNote(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Unit" width="56">
          <template #default="{ row }">{{ row.unit || 'nA' }}</template>
        </el-table-column>
        <el-table-column label="Min" width="56">
          <template #default="{ row }">{{ formatLimit(row.min) }}</template>
        </el-table-column>
        <el-table-column label="Max" width="56">
          <template #default="{ row }">{{ formatLimit(row.max) }}</template>
        </el-table-column>
        <el-table-column label="结果" width="64" align="center">
          <template #default="{ row }">
            <span :class="row.pass ? 'note-pass' : 'note-fail'">{{ resultText(row.pass) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog
      v-model="saveTplDialog"
      :title="saveTplMode === 'saveAs' ? '另存为新客户标准' : '更新当前模板'"
      width="480px"
    >
      <p class="add-tip">
        <template v-if="saveTplMode === 'saveAs'">
          将基于当前参数配置（含 Min/Max、启用项、自定义 Item）新建一份模板。
          <b>默认「DR8-PIC 客户标准」不会被改动</b>，下次可直接从顶部下拉打开新模板。
        </template>
        <template v-else>
          用当前参数配置覆盖模板「{{ currentTemplate?.name }}」。
        </template>
      </p>
      <el-form label-width="90px">
        <el-form-item label="模板名称">
          <el-input
            v-model="saveTplName"
            placeholder="例如：客户A标准、DR8放宽版"
            maxlength="40"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveTplDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmSaveTemplate">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="addDialog" title="从数据库添加 ItemName" width="520px">
      <p class="add-tip">
        读取当前数据源中已有的 <code>d.ItemName</code>，勾选后加入参数配置并设置 Min/Max。
      </p>
      <el-select
        v-model="selectedItemNames"
        multiple
        filterable
        collapse-tags
        collapse-tags-tooltip
        placeholder="选择 ItemName"
        style="width: 100%"
        :loading="loadingItems"
      >
        <el-option
          v-for="it in availableDbItems"
          :key="it.name"
          :label="it.unit ? `${it.name} (${it.unit})` : it.name"
          :value="it.name"
        />
      </el-select>
      <p v-if="!loadingItems && !availableDbItems.length" class="add-empty">
        没有可新增的 ItemName（可能都已在配置中）
      </p>
      <template #footer>
        <el-button @click="addDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmAddItems">添加</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dbDialog" title="设备数据库连接" width="480px">
      <el-form label-width="100px">
        <el-form-item label="Mock 模式">
          <el-switch v-model="dbForm.use_mock" />
        </el-form-item>
        <el-form-item label="主机">
          <el-input v-model="dbForm.host" :disabled="dbForm.use_mock" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="dbForm.port" :disabled="dbForm.use_mock" />
        </el-form-item>
        <el-form-item label="数据库">
          <el-input v-model="dbForm.database" :disabled="dbForm.use_mock" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="dbForm.user" :disabled="dbForm.use_mock" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="dbForm.password"
            type="password"
            show-password
            :disabled="dbForm.use_mock"
            placeholder="留空则保留原密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="onTestDb">测试连接</el-button>
        <el-button type="primary" @click="onSaveDb">保存并加载</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page {
  width: 100vw;
  height: 100vh;
  max-width: 100vw;
  max-height: 100vh;
  margin: 0;
  padding: 8px 10px;
  overflow: hidden;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  flex-shrink: 0;
  min-height: 40px;
}

.top-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

.logic {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.top-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  justify-content: flex-end;
  align-items: center;
  flex-shrink: 0;
}

.api-status {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  color: #9ecbff;
  opacity: 0.9;
}

.grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr) minmax(0, 0.95fr);
  gap: 10px;
  width: 100%;
  align-items: stretch;
}

.panel {
  background: linear-gradient(180deg, var(--panel) 0%, #152032 100%);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px 10px;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.22);
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-shrink: 0;
}

.panel-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  justify-content: flex-end;
}

.tag-custom {
  margin-left: 6px;
}

.add-tip {
  margin: 0 0 12px;
  color: #606266;
  font-size: 13px;
}

.add-empty {
  margin: 12px 0 0;
  color: #909399;
  font-size: 13px;
}

h2 {
  margin: 0;
  font-size: 14px;
  white-space: nowrap;
}

h3 {
  margin: 6px 0 4px;
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
  flex-shrink: 0;
}

.legend {
  display: flex;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
}

.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 4px;
}

.dot.pass {
  background: var(--pass);
}
.dot.fail {
  background: var(--fail);
}

.map-panel .map-wrap {
  flex: 1;
  min-height: 0;
}

.map-wrap {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  overflow: hidden;
  cursor: pointer;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 8px;
  padding: 4px;
}

.hint {
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 11px;
  text-align: center;
  flex-shrink: 0;
}

.empty {
  color: var(--muted);
  font-size: 13px;
  text-align: center;
  padding: 12px;
}

.stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-bottom: 2px;
  flex-shrink: 0;
}

.stats div {
  background: var(--panel-2);
  border-radius: 6px;
  padding: 6px 8px;
}

.stats label {
  display: block;
  color: var(--muted);
  font-size: 11px;
}

.stats strong {
  font-size: 18px;
  line-height: 1.2;
}

.grow-table {
  flex: 1;
  min-height: 0;
}

.pass-text {
  color: var(--pass);
}

.fail-text {
  color: var(--fail);
}

.footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.footer-actions.inline {
  margin-top: 0;
}

.num {
  width: 72px !important;
}
.item-name {
  word-break: break-word;
}

:deep(.dark-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: #1e2a3d;
  --el-table-row-hover-bg-color: #24344a;
  --el-table-text-color: var(--text);
  --el-table-header-text-color: var(--muted);
  --el-table-border-color: var(--line);
}

.die-pick-tip {
  margin: 0 0 10px;
  color: #606266;
  font-size: 13px;
}
.die-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.die-cell {
  min-height: 72px;
  padding: 6px 4px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: #f5f7fa;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font: inherit;
  color: #303133;
}
.die-cell strong,
.die-full-label {
  font-size: 11px;
  font-weight: 600;
  line-height: 1.25;
  word-break: break-all;
  text-align: center;
}
.die-cell small {
  font-size: 11px;
}
.die-cell.pass {
  background: #e8f8ef;
  border-color: #95d5b2;
}
.die-cell.fail {
  background: #fdecea;
  border-color: #f5a8a0;
}
.die-cell.missing,
.die-cell.empty {
  background: #f0f2f5;
  color: #909399;
  cursor: not-allowed;
}
.die-cell.missing .miss {
  color: #c0c4cc;
}
.die-cell:not(:disabled):hover {
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.35);
}
.die-meta {
  margin: 0 0 8px;
  flex-shrink: 0;
  font-size: 13px;
}

.die-tip {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.die-dialog-body {
  display: flex;
  flex-direction: column;
  max-height: calc(96vh - 72px);
  overflow: hidden;
}

.note-text {
  color: #303133;
  font-variant-numeric: tabular-nums;
}

.cond :deep(sub) {
  font-size: 0.75em;
}

.item-link {
  border: none;
  background: none;
  padding: 0;
  color: #1d4f91;
  font: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.item-link:hover {
  color: #0b3a6e;
}
/* 固定两列：标签列宽固定，输入框列上下对齐且不被标签挤压 */
.mpd-limits {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  column-gap: 6px;
  row-gap: 4px;
  align-items: center;
  width: 100%;
}
.mpd-vtag {
  width: 28px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  font-size: 11px;
  font-weight: 600;
  color: #dce9f8;
  background: #2a405c;
  border-radius: 4px;
  user-select: none;
}
.mpd-vtag.v4 {
  color: #f3e2c8;
  background: #4a3a28;
}
.mpd-num {
  width: 100% !important;
  max-width: none !important;
}
.mpd-num :deep(.el-input__wrapper) {
  padding-left: 4px;
  padding-right: 4px;
}
.mpd-num :deep(.el-input__inner) {
  text-align: right;
  padding: 0 2px;
}
.mpd-under {
  padding: 4px 8px 6px 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: linear-gradient(180deg, #f5f8fc 0%, #eef3f9 100%);
  border-left: 3px solid #9db7d4;
}
.mpd-under-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1.1fr) 48px;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  padding: 4px 8px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}
.mpd-range {
  color: #334155;
  font-variant-numeric: tabular-nums;
}
.mpd-range small {
  margin-left: 4px;
  color: #64748b;
}
:deep(.detail-table tr:not(.mpd-row) .el-table__expand-icon) {
  visibility: hidden;
  pointer-events: none;
}
.note-pass {
  color: #67c23a;
}

.note-fail {
  color: #f56c6c;
}

:deep(.overall-row) {
  font-weight: 700;
  background: #f0f9eb !important;
}

:deep(.detail-table .cell) {
  line-height: 1.35;
}

:deep(.dark-table .el-table__body),
:deep(.dark-table .el-table__header) {
  width: 100% !important;
}

@media (max-width: 1100px) {
  .logic {
    display: none;
  }
  .top-actions :deep(.el-select) {
    width: 130px !important;
  }
}
</style>

<style>
/* el-dialog 传送到 body，需非 scoped */
.die-dialog.el-dialog {
  margin-top: 2vh !important;
  max-height: 96vh;
  display: flex;
  flex-direction: column;
}
.die-dialog .el-dialog__header {
  padding: 10px 16px 6px;
  flex-shrink: 0;
}
.die-dialog .el-dialog__body {
  padding: 4px 16px 12px;
  overflow: hidden;
  flex: 1;
  min-height: 0;
}
.die-dialog .detail-table {
  --el-table-row-hover-bg-color: #f5f7fa;
}
.die-dialog .detail-table .el-table__cell {
  padding: 3px 0 !important;
}
.child-dialog.el-dialog {
  margin-top: 4vh !important;
  max-height: 92vh;
}
.child-dialog .el-dialog__body {
  padding: 6px 12px 12px;
}
</style>
