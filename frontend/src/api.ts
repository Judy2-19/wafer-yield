import axios, { type AxiosRequestConfig } from 'axios'
import { buildApiCandidates } from './apiCandidates'

const CANDIDATES = buildApiCandidates(import.meta.env.VITE_API_BASE as string | undefined)

let activeBase = CANDIDATES[0] || 'http://127.0.0.1:8000/api'

const http = axios.create({
  baseURL: activeBase,
  timeout: 60000,
})

export function getApiBase() {
  return activeBase
}

/** 依次探测可用后端地址，解决代理/直连/localhost 差异 */
export async function ensureApiReady(): Promise<string> {
  const tried: string[] = []
  for (const base of CANDIDATES) {
    tried.push(base)
    try {
      const { data, status } = await axios.get(`${base.replace(/\/$/, '')}/health`, {
        timeout: 4000,
        validateStatus: () => true,
      })
      if (status === 200 && (data?.status === 'ok' || data?.status === 'OK')) {
        activeBase = base
        http.defaults.baseURL = base
        return base
      }
      tried[tried.length - 1] = `${base} (HTTP ${status})`
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      tried[tried.length - 1] = `${base} (${msg})`
    }
  }
  throw new Error(
    `后端连不上。已尝试: ${tried.join(' | ')}。请看后端黑窗口是否有 Application startup complete，浏览器直接打开 http://127.0.0.1:8000/api/health`,
  )
}

async function apiGet<T>(url: string, config?: AxiosRequestConfig) {
  const { data } = await http.get<T>(url, config)
  return data
}

async function apiPost<T>(url: string, body?: unknown, config?: AxiosRequestConfig) {
  const { data } = await http.post<T>(url, body, config)
  return data
}

async function apiPut<T>(url: string, body?: unknown, config?: AxiosRequestConfig) {
  const { data } = await http.put<T>(url, body, config)
  return data
}

export type SpecItem = {
  name: string
  display_name?: string
  condition?: string
  lsl: number | null
  lsl_4v?: number | null
  target?: number | null
  usl: number | null
  usl_4v?: number | null
  enabled: boolean
  unit?: string | null
  note?: string | null
  custom?: boolean
}

export type DiePayload = {
  id?: string
  wafer: string
  shot: string
  sn?: string
  serial?: string | null
  label?: string
  create_time?: string | null
  x: number | null
  y: number | null
  pass?: boolean
  manual_untested?: boolean
  tests: Record<string, { value: number | null; unit?: string | null }>
  param_rows?: Array<{
    key?: string
    item?: string
    name: string
    condition?: string
    unit?: string | null
    min?: number | string | null
    target?: number | null
    max?: number | string | null
    note?: string | null
    value: number | null
    lsl: number | null
    usl: number | null
    pass: boolean | null
    is_overall?: boolean
    expandable?: boolean
    db_hint?: string
    children?: Array<{
      item?: string
      name?: string
      value?: number | null
      unit?: string
      min?: number | null
      max?: number | null
      pass?: boolean
      note?: string
      key?: string
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
  }>
}

export type ShotSummary = {
  shot: string
  x: number | null
  y: number | null
  pass: boolean
  mixed?: boolean
  die_count: number
  pass_count: number
  fail_count: number
  coord_label?: string
  sn_x?: number | null
  sn_y?: number | null
  dies?: Array<{
    id?: string
    shot: string
    sn?: string
    serial?: string | null
    label?: string
    pass?: boolean
    manual_untested?: boolean
    create_time?: string | null
  }>
}

export type DieGridCell = {
  serial: string | null
  row: number
  col: number
  empty?: boolean
}

export type WaferInfo = {
  wafer: string
  create_time_min?: string | null
  create_time_max?: string | null
}

export type JudgeResult = {
  wafer: string
  dies: DiePayload[]
  shots: ShotSummary[]
  die_grid?: DieGridCell[]
  die_serials?: string[]
  map_grid?: { min_x: number; max_x: number; min_y: number; max_y: number }
  layout?: LayoutInfo | null
  stats: {
    total: number
    pass_count: number
    fail_count: number
    yield: number
    fail_rate_details: Array<{ name: string; fail_count: number; fail_rate: number }>
  }
  data_quality?: {
    valued_test_count?: number
    sample?: string[]
    fetch?: { valued_itemvalue?: number; eav_1311?: number; head_rows?: number }
    coord?: {
      layout_driven?: boolean
      matched_dies?: number
      unmatched_shots?: string[]
      unmatched_shot_count?: number
    }
  }
}

export type LayoutSummary = {
  layout_id?: string
  filename?: string
  shot_count: number
  site_count: number
  test_key_count: number
  shot_rows: number
  shot_cols: number
  die_rows: number
  die_cols: number
}

export type LayoutInfo = {
  layout_id?: string
  name?: string
  filename?: string
  summary: LayoutSummary
  map_grid?: { min_x: number; max_x: number; min_y: number; max_y: number }
  shots?: Array<{ custom: string; col: number; row: number; prober?: string }>
  die_grid?: DieGridCell[]
  die_serials?: string[]
  test_keys?: Array<{ row: number; col: number }>
}

export type LayoutTemplateSummary = {
  layout_id: string
  name: string
  filename?: string
  summary: LayoutSummary
  current?: boolean
}

export type LayoutViewSettings = {
  waferScale: number
  waferOffsetX: number
  waferOffsetY: number
}

export type TimeRange = { start?: string | null; end?: string | null }

export async function fetchWafers(range?: TimeRange) {
  const data = await apiGet<{ wafers: WaferInfo[] }>('/wafers', {
    params: {
      start: range?.start || undefined,
      end: range?.end || undefined,
    },
  })
  return data.wafers
}

export async function fetchCurrentLayout() {
  return apiGet<{ ok: boolean; layout: LayoutInfo | null; message?: string }>('/layout/current')
}

export async function uploadLayout(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<{ ok: boolean; layout: LayoutInfo }>('/layout/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function fetchLayoutTemplates() {
  const data = await apiGet<{ templates: LayoutTemplateSummary[] }>('/layout/templates')
  return data.templates
}

export async function selectLayoutTemplate(layoutId: string) {
  return apiPut<{ ok: boolean; layout: LayoutInfo }>(
    `/layout/templates/${encodeURIComponent(layoutId)}/select`,
  )
}

export async function renameLayoutTemplate(layoutId: string, name: string) {
  return apiPut<{ ok: boolean; layout: LayoutInfo }>(
    `/layout/templates/${encodeURIComponent(layoutId)}/rename`,
    { name },
  )
}

export async function deleteLayoutTemplate(layoutId: string) {
  const { data } = await http.delete<{ ok: boolean; layout: LayoutInfo | null }>(
    `/layout/templates/${encodeURIComponent(layoutId)}`,
  )
  return data
}

export async function fetchLayoutViewSettings(layoutId: string): Promise<LayoutViewSettings> {
  const data = await apiGet<{
    wafer_scale: number
    wafer_offset_x: number
    wafer_offset_y: number
  }>(`/layout/view-settings/${encodeURIComponent(layoutId)}`)
  return {
    waferScale: data.wafer_scale,
    waferOffsetX: data.wafer_offset_x,
    waferOffsetY: data.wafer_offset_y,
  }
}

export async function saveLayoutViewSettings(
  layoutId: string,
  settings: LayoutViewSettings,
): Promise<LayoutViewSettings> {
  const data = await apiPut<{
    wafer_scale: number
    wafer_offset_x: number
    wafer_offset_y: number
  }>(`/layout/view-settings/${encodeURIComponent(layoutId)}`, {
    wafer_scale: settings.waferScale,
    wafer_offset_x: settings.waferOffsetX,
    wafer_offset_y: settings.waferOffsetY,
  })
  return {
    waferScale: data.wafer_scale,
    waferOffsetX: data.wafer_offset_x,
    waferOffsetY: data.wafer_offset_y,
  }
}

export async function fetchItemNames(wafer?: string) {
  const data = await apiGet<{ items: Array<{ name: string; unit?: string | null }> }>('/item-names', {
    params: wafer ? { wafer } : {},
  })
  return data.items
}

export async function fetchTemplates() {
  const data = await apiGet<{
    templates: Array<{ id: string; name: string; specs: SpecItem[]; builtin?: boolean }>
  }>('/spec-templates')
  return data.templates
}

export async function judge(wafer: string, specs: SpecItem[], range?: TimeRange) {
  return apiPost<JudgeResult>('/judge', {
    wafer,
    specs,
    start: range?.start || null,
    end: range?.end || null,
  })
}

export async function setDieManualUntested(wafer: string, dieId: string, untested: boolean) {
  return apiPut<{ ok: boolean; manual_untested: boolean }>(
    `/dies/${encodeURIComponent(dieId)}/manual-untested`,
    { wafer, untested },
  )
}

export async function getDbConfig() {
  return apiGet<Record<string, unknown>>('/db/config')
}

export async function saveDbConfig(body: Record<string, unknown>) {
  return apiPost('/db/config', body)
}

export async function testDb(body: Record<string, unknown>) {
  return apiPost<{ ok: boolean; message: string }>('/db/test', body)
}

export async function saveTemplate(body: { id: string; name: string; specs: SpecItem[] }) {
  return apiPost<{ ok: boolean; id: string; name: string }>('/spec-templates', body)
}

export async function deleteTemplate(id: string) {
  const { data } = await http.delete(`/spec-templates/${id}`)
  return data
}

export async function saveJudge(wafer: string, payload: JudgeResult) {
  return apiPost('/judge/save', { wafer, payload })
}

export async function exportExcel(payload: JudgeResult) {
  const { data } = await http.post('/export/excel', payload, { responseType: 'blob' })
  return data as Blob
}

export async function forceMockMode() {
  return apiPost<{ ok: boolean; message?: string }>('/db/force-mock', {})
}
