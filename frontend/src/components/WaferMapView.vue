<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { DieGridCell, ShotSummary } from '../api'
import {
  buildWaferCells,
  compactShotLabel,
  computeWaferGeometry,
  hitTestCell,
  shotIntersectsWafer,
  shotRect,
  type WaferCell,
  type WaferViewSettings,
} from '../waferMapGeometry'

const props = withDefaults(
  defineProps<{
    shots: ShotSummary[]
    dieGrid: DieGridCell[]
    size?: number
    fixedGrid: { minX: number; maxX: number; minY: number; maxY: number }
    settings: WaferViewSettings
  }>(),
  { size: 520 },
)

const emit = defineEmits<{
  shotClick: [shot: string]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const hover = ref<WaferCell | null>(null)
const pointer = ref({ x: 0, y: 0 })

const geometry = computed(() =>
  computeWaferGeometry({
    size: props.size,
    grid: props.fixedGrid,
    dieGrid: props.dieGrid,
    settings: props.settings,
  }),
)

const cells = computed(() =>
  buildWaferCells({
    geometry: geometry.value,
    dieGrid: props.dieGrid,
    shots: props.shots,
  }),
)

const showDieLabels = computed(() => geometry.value.dieWidth >= 28 && geometry.value.dieHeight >= 18)

function insideWafer(x: number, y: number) {
  const g = geometry.value
  return Math.hypot(x - g.cx, y - g.cy) <= g.radius
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const g = geometry.value
  const dpr = window.devicePixelRatio || 1
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  canvas.width = Math.round(props.size * dpr)
  canvas.height = Math.round(props.size * dpr)
  canvas.style.width = `${props.size}px`
  canvas.style.height = `${props.size}px`
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, props.size, props.size)

  ctx.beginPath()
  ctx.arc(g.cx, g.cy, g.radius, 0, Math.PI * 2)
  ctx.fillStyle = '#f7f8fa'
  ctx.fill()

  ctx.save()
  ctx.beginPath()
  ctx.arc(g.cx, g.cy, g.radius - 1, 0, Math.PI * 2)
  ctx.clip()

  for (const cell of cells.value) {
    const inset = 0.7
    ctx.fillStyle = cell.color
    ctx.fillRect(cell.x + inset, cell.y + inset, cell.width - inset * 2, cell.height - inset * 2)
    ctx.strokeStyle = cell.status === 'test-key' ? '#7b7410' : '#7b858e'
    ctx.lineWidth = 0.65
    ctx.strokeRect(cell.x + inset, cell.y + inset, cell.width - inset * 2, cell.height - inset * 2)

    if (showDieLabels.value && cell.serial && cell.status !== 'test-key') {
      ctx.fillStyle = '#17212a'
      ctx.font = `${Math.max(6, Math.min(9, g.dieWidth * 0.22))}px Segoe UI, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(cell.serial, cell.x + cell.width / 2, cell.y + cell.height / 2)
    }
  }

  for (const shot of props.shots) {
    if (shot.x == null || shot.y == null) continue
    const rect = shotRect(shot, g)
    ctx.strokeStyle = '#1597d4'
    ctx.lineWidth = 1.6
    ctx.strokeRect(rect.x + 0.8, rect.y + 0.8, rect.width - 1.6, rect.height - 1.6)
  }
  ctx.restore()

  ctx.beginPath()
  ctx.arc(g.cx, g.cy, g.radius, 0, Math.PI * 2)
  ctx.strokeStyle = '#ff0000'
  ctx.lineWidth = 3.5
  ctx.stroke()

  for (const shot of props.shots) {
    if (shot.x == null || shot.y == null) continue
    const rect = shotRect(shot, g)
    if (!shotIntersectsWafer(rect, g)) continue
    const label = compactShotLabel(shot.shot)
    const fs = Math.max(9, Math.min(16, g.shotWidth * 0.3))
    ctx.font = `700 ${fs}px Segoe UI, Microsoft YaHei, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.lineWidth = 3
    ctx.strokeStyle = 'rgba(255,255,255,.9)'
    ctx.strokeText(label, rect.centerX, rect.centerY)
    ctx.fillStyle = '#111'
    ctx.fillText(label, rect.centerX, rect.centerY)
  }

  if (hover.value) {
    const cell = hover.value
    ctx.strokeStyle = '#ffe566'
    ctx.lineWidth = 2.5
    ctx.strokeRect(cell.x + 1, cell.y + 1, cell.width - 2, cell.height - 2)
  }
}

function eventToLocal(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const rect = canvas.getBoundingClientRect()
  return {
    x: ((e.clientX - rect.left) * props.size) / rect.width,
    y: ((e.clientY - rect.top) * props.size) / rect.height,
  }
}

function findCell(e: MouseEvent) {
  const local = eventToLocal(e)
  pointer.value = local
  if (!insideWafer(local.x, local.y)) return null
  return hitTestCell(cells.value, local.x, local.y)
}

function onMove(e: MouseEvent) {
  const cell = findCell(e)
  if (cell !== hover.value) {
    hover.value = cell
    draw()
  }
}

function onLeave() {
  hover.value = null
  draw()
}

function onClick(e: MouseEvent) {
  const cell = findCell(e)
  if (cell) emit('shotClick', cell.shot)
}

const tooltipText = computed(() => {
  const cell = hover.value
  if (!cell) return ''
  const status =
    cell.status === 'pass'
      ? 'Pass'
      : cell.status === 'fail'
        ? 'Fail'
        : cell.status === 'manual-untested'
          ? '未测试(人为)'
          : '无数据'
  return `Shot ${cell.shot} · SN${cell.serial || '—'} · ${status}`
})

watch([cells, geometry], draw, { deep: true })
onMounted(() => {
  draw()
  window.addEventListener('resize', draw)
})
onUnmounted(() => window.removeEventListener('resize', draw))
</script>

<template>
  <div class="wafer-map-stage" :style="{ width: `${size}px`, height: `${size}px` }">
    <canvas
      ref="canvasRef"
      class="wafer-canvas"
      @mousemove="onMove"
      @mouseleave="onLeave"
      @click="onClick"
    />
    <div
      v-if="tooltipText"
      class="wafer-tooltip"
      :style="{
        left: `${Math.min(size - 150, Math.max(4, pointer.x + 10))}px`,
        top: `${Math.min(size - 38, Math.max(4, pointer.y - 34))}px`,
      }"
    >
      {{ tooltipText }}
    </div>
  </div>
</template>

<style scoped>
.wafer-map-stage {
  position: relative;
  flex: 0 0 auto;
}

.wafer-canvas {
  display: block;
  cursor: pointer;
  user-select: none;
}

.wafer-tooltip {
  position: absolute;
  z-index: 2;
  max-width: 190px;
  padding: 6px 9px;
  border-radius: 6px;
  background: rgba(20, 33, 43, 0.94);
  color: #fff;
  font-size: 11px;
  line-height: 1.25;
  pointer-events: none;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
}
</style>
