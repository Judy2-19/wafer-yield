<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

export type WaferCoord = {
  x: number
  y: number
  color: string
  info?: string[]
  shot?: string
}

const props = withDefaults(
  defineProps<{
    coords: WaferCoord[]
    size?: number
    notch?: 'top' | 'none'
    backgroundColor?: string
    /** 可选：外部指定坐标范围；默认按数据里出现的 Shot 坐标自适应 */
    fixedGrid?: { minX: number; maxX: number; minY: number; maxY: number } | null
  }>(),
  {
    size: 520,
    notch: 'top',
    backgroundColor: '#3a7ca5',
    fixedGrid: null,
  },
)

const emit = defineEmits<{
  dieHover: [die: WaferCoord | null]
  dieClick: [die: WaferCoord]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const hover = ref<WaferCoord | null>(null)

const bounds = computed(() => {
  if (props.fixedGrid) {
    const { minX, maxX, minY, maxY } = props.fixedGrid
    return {
      minX,
      maxX,
      minY,
      maxY,
      cols: Math.max(1, maxX - minX + 1),
      rows: Math.max(1, maxY - minY + 1),
    }
  }
  const xs = props.coords.map((c) => c.x)
  const ys = props.coords.map((c) => c.y)
  if (!xs.length) return { minX: 0, maxX: 0, minY: 0, maxY: 0, cols: 1, rows: 1 }
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  return {
    minX,
    maxX,
    minY,
    maxY,
    cols: maxX - minX + 1,
    rows: maxY - minY + 1,
  }
})

/** 晶圆内接正方形网格的几何（与绘制、命中共用同一套公式） */
function geometry(cssSize: number) {
  const dpr = window.devicePixelRatio || 1
  const pad = cssSize * 0.08
  const mapSize = cssSize - pad * 2
  const { cols, rows, minX, minY } = bounds.value
  const cell = Math.min(mapSize / cols, mapSize / rows)
  const gridW = cell * cols
  const gridH = cell * rows
  const originX = (cssSize - gridW) / 2
  const originY = (cssSize - gridH) / 2
  return { dpr, pad, cell, originX, originY, minX, minY, cols, rows, cssSize }
}

function dieRect(die: WaferCoord, g: ReturnType<typeof geometry>) {
  const col = die.x - g.minX
  const row = die.y - g.minY
  return {
    x: g.originX + col * g.cell,
    y: g.originY + row * g.cell,
    w: g.cell,
    h: g.cell,
  }
}

function findDieAt(cssX: number, cssY: number): WaferCoord | null {
  const g = geometry(props.size)
  const col = Math.floor((cssX - g.originX) / g.cell)
  const row = Math.floor((cssY - g.originY) / g.cell)
  if (col < 0 || row < 0 || col >= g.cols || row >= g.rows) return null
  const x = g.minX + col
  const y = g.minY + row
  return props.coords.find((c) => c.x === x && c.y === y) ?? null
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const g = geometry(props.size)
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  canvas.width = Math.round(g.cssSize * g.dpr)
  canvas.height = Math.round(g.cssSize * g.dpr)
  canvas.style.width = `${g.cssSize}px`
  canvas.style.height = `${g.cssSize}px`
  ctx.setTransform(g.dpr, 0, 0, g.dpr, 0, 0)
  ctx.clearRect(0, 0, g.cssSize, g.cssSize)

  const cx = g.cssSize / 2
  const cy = g.cssSize / 2
  const r = g.cssSize / 2 - 2

  // 晶圆圆盘
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fillStyle = props.backgroundColor
  ctx.fill()
  ctx.strokeStyle = 'rgba(255,255,255,0.35)'
  ctx.lineWidth = 1.5
  ctx.stroke()

  // notch
  if (props.notch === 'top') {
    ctx.beginPath()
    ctx.arc(cx, 6, 10, 0, Math.PI * 2)
    ctx.fillStyle = '#f3a6b8'
    ctx.fill()
  }

  // 圆形裁切晶粒
  ctx.save()
  ctx.beginPath()
  ctx.arc(cx, cy, r - 1, 0, Math.PI * 2)
  ctx.clip()

  for (const die of props.coords) {
    const rect = dieRect(die, g)
    const inset = 1.5
    ctx.fillStyle = die.color
    ctx.fillRect(rect.x + inset, rect.y + inset, rect.w - inset * 2, rect.h - inset * 2)

    ctx.strokeStyle = 'rgba(0,0,0,0.28)'
    ctx.lineWidth = 1
    ctx.strokeRect(rect.x + inset + 0.5, rect.y + inset + 0.5, rect.w - inset * 2 - 1, rect.h - inset * 2 - 1)

    const lines = (die.info || []).filter(Boolean).slice(0, 2)
    if (lines.length && g.cell >= 22) {
      ctx.fillStyle = '#111'
      const fs = Math.max(8, Math.min(11, g.cell * (lines.length > 1 ? 0.22 : 0.28)))
      ctx.font = `600 ${fs}px Segoe UI, Microsoft YaHei, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      const cxText = rect.x + rect.w / 2
      const cyText = rect.y + rect.h / 2
      if (lines.length === 1) {
        ctx.fillText(lines[0], cxText, cyText)
      } else {
        ctx.fillText(lines[0], cxText, cyText - fs * 0.65)
        ctx.font = `500 ${Math.max(7, fs - 1)}px Segoe UI, Microsoft YaHei, sans-serif`
        ctx.fillText(lines[1], cxText, cyText + fs * 0.7)
      }
    }
  }

  // 选中/悬停框：与晶粒同几何，描边落在格子边框上
  if (hover.value) {
    const rect = dieRect(hover.value, g)
    const inset = 1.5
    ctx.strokeStyle = '#ffe566'
    ctx.lineWidth = 2.5
    ctx.strokeRect(rect.x + inset, rect.y + inset, rect.w - inset * 2, rect.h - inset * 2)
    ctx.strokeStyle = '#1a1a1a'
    ctx.lineWidth = 1
    ctx.strokeRect(rect.x + inset + 1.5, rect.y + inset + 1.5, rect.w - inset * 2 - 3, rect.h - inset * 2 - 3)
  }

  ctx.restore()
}

function eventToLocal(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const rect = canvas.getBoundingClientRect()
  const scaleX = props.size / rect.width
  const scaleY = props.size / rect.height
  return {
    x: (e.clientX - rect.left) * scaleX,
    y: (e.clientY - rect.top) * scaleY,
  }
}

function onMove(e: MouseEvent) {
  const { x, y } = eventToLocal(e)
  const die = findDieAt(x, y)
  const changed = (die?.x ?? null) !== (hover.value?.x ?? null) || (die?.y ?? null) !== (hover.value?.y ?? null)
  if (changed) {
    hover.value = die
    emit('dieHover', die)
    draw()
  }
}

function onLeave() {
  hover.value = null
  emit('dieHover', null)
  draw()
}

function onClick(e: MouseEvent) {
  const { x, y } = eventToLocal(e)
  const die = findDieAt(x, y)
  if (die) emit('dieClick', die)
}

watch(() => props.coords, draw, { deep: true })
watch(() => props.size, draw)

onMounted(() => {
  draw()
  window.addEventListener('resize', draw)
})
onUnmounted(() => window.removeEventListener('resize', draw))
</script>

<template>
  <canvas
    ref="canvasRef"
    class="wafer-canvas"
    @mousemove="onMove"
    @mouseleave="onLeave"
    @click="onClick"
  />
</template>

<style scoped>
.wafer-canvas {
  display: block;
  cursor: pointer;
  border-radius: 8px;
  user-select: none;
}
</style>
