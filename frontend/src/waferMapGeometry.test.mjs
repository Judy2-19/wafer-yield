import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildWaferCells,
  compactShotLabel,
  computeWaferGeometry,
  hitTestCell,
  mergeLayoutShots,
  shotIntersectsWafer,
  shotRect,
} from './waferMapGeometry.ts'

const grid = { minX: 0, maxX: 1, minY: 0, maxY: 0 }
const dieGrid = [
  { serial: '0101', row: 0, col: 0 },
  { serial: '0102', row: 0, col: 1 },
  { serial: null, row: 1, col: 0, empty: true },
  { serial: '0202', row: 1, col: 1 },
]

test('compacts three-digit shot labels without changing two-digit labels', () => {
  assert.equal(compactShotLabel('103'), 'A3')
  assert.equal(compactShotLabel('51'), '51')
})

test('moves the wafer boundary independently in shot units', () => {
  const geometry = computeWaferGeometry({
    size: 400,
    grid,
    dieGrid,
    settings: { waferScale: 1, waferOffsetX: 1, waferOffsetY: 1 },
  })

  assert.equal(geometry.cx - geometry.gridCx, geometry.shotWidth)
  assert.equal(geometry.cy - geometry.gridCy, -geometry.shotHeight)
})

test('centers arbitrary shot grids and preserves a single-row die template', () => {
  const geometry = computeWaferGeometry({
    size: 500,
    grid: { minX: 3, maxX: 5, minY: 7, maxY: 7 },
    dieGrid: [
      { serial: '0101', row: 4, col: 2 },
      { serial: '0102', row: 4, col: 3 },
    ],
    settings: { waferScale: 1, waferOffsetX: 0, waferOffsetY: 0 },
  })
  const left = shotRect({ shot: '41', x: 3, y: 7, pass: true }, geometry)
  const right = shotRect({ shot: '61', x: 5, y: 7, pass: true }, geometry)

  assert.equal(geometry.dieRows, 1)
  assert.equal(left.centerX + right.centerX, geometry.gridCx * 2)
  assert.equal(left.centerY, geometry.gridCy)
})

test('balances wafer whitespace for a 10 by 7 shot layout with 3 by 6 dies', () => {
  const geometry = computeWaferGeometry({
    size: 500,
    grid: { minX: 0, maxX: 9, minY: 0, maxY: 6 },
    dieGrid: Array.from({ length: 6 }, (_, row) =>
      Array.from({ length: 3 }, (_, col) => ({ serial: `${row}-${col}`, row, col })),
    ).flat(),
    settings: { waferScale: 1, waferOffsetX: 0, waferOffsetY: 0 },
  })
  const layoutWidth = geometry.shotCols * geometry.shotWidth
  const layoutHeight = geometry.shotRows * geometry.shotHeight
  const horizontalWhitespace = geometry.radius - layoutWidth / 2
  const verticalWhitespace = geometry.radius - layoutHeight / 2

  assert.ok(Math.abs(layoutWidth - layoutHeight) < 0.001)
  assert.ok(Math.abs(horizontalWhitespace - verticalWhitespace) < 0.001)
  assert.ok(Math.abs(geometry.dieWidth / geometry.dieHeight - 1.4) < 0.001)
})

test('builds pass fail missing and non-clickable test-key cells from real shot data', () => {
  const geometry = computeWaferGeometry({
    size: 400,
    grid,
    dieGrid,
    settings: { waferScale: 1, waferOffsetX: 0, waferOffsetY: 0 },
  })
  const cells = buildWaferCells({
    geometry,
    dieGrid,
    shots: [
      {
        shot: '51',
        x: 0,
        y: 0,
        pass: false,
        dies: [
          { serial: '0101', pass: true },
          { serial: '0102', pass: false },
        ],
      },
    ],
  })

  assert.equal(cells.find((cell) => cell.serial === '0101')?.status, 'pass')
  assert.equal(cells.find((cell) => cell.serial === '0102')?.status, 'fail')
  const missing = cells.find((cell) => cell.serial === '0202')
  assert.equal(missing?.status, 'missing')
  assert.equal(missing?.color, '#cbd5e1')
  const testKey = cells.find((cell) => cell.status === 'test-key')
  assert.equal(testKey?.color, '#ffd600')
  assert.equal(testKey?.clickable, false)
})

test('distinguishes a manually untested die from a genuinely missing die and keeps it clickable', () => {
  const geometry = computeWaferGeometry({
    size: 400,
    grid,
    dieGrid,
    settings: { waferScale: 1, waferOffsetX: 0, waferOffsetY: 0 },
  })
  const cells = buildWaferCells({
    geometry,
    dieGrid,
    shots: [
      {
        shot: '51',
        x: 0,
        y: 0,
        pass: true,
        dies: [{ serial: '0101', pass: false, manual_untested: true }],
      },
    ],
  })

  const excluded = cells.find((cell) => cell.serial === '0101')
  assert.equal(excluded?.status, 'manual-untested')
  assert.equal(excluded?.color, '#94a3b8')
  assert.equal(excluded?.clickable, true)
})

test('hit testing returns the owning shot and ignores test keys', () => {
  const geometry = computeWaferGeometry({
    size: 400,
    grid,
    dieGrid,
    settings: { waferScale: 1.5, waferOffsetX: 0, waferOffsetY: 0 },
  })
  const cells = buildWaferCells({
    geometry,
    dieGrid,
    shots: [{ shot: '51', x: 0, y: 0, pass: true, dies: [] }],
  })
  const normal = cells.find((cell) => cell.serial === '0101')
  const testKey = cells.find((cell) => cell.status === 'test-key')

  assert.equal(hitTestCell(cells, normal.x + normal.width / 2, normal.y + normal.height / 2)?.shot, '51')
  assert.equal(hitTestCell(cells, testKey.x + testKey.width / 2, testKey.y + testKey.height / 2), null)
})

test('keeps labels for edge shots that intersect the wafer boundary', () => {
  const geometry = computeWaferGeometry({
    size: 400,
    grid: { minX: 0, maxX: 2, minY: 0, maxY: 0 },
    dieGrid: [{ serial: '0101', row: 0, col: 0 }],
    settings: { waferScale: 0.5, waferOffsetX: 0, waferOffsetY: 0 },
  })
  const edge = {
    x: geometry.cx + geometry.radius - 4,
    y: geometry.cy - 20,
    width: 40,
    height: 40,
    centerX: geometry.cx + geometry.radius + 16,
    centerY: geometry.cy,
  }

  assert.equal(shotIntersectsWafer(edge, geometry), true)
})

test('keeps layout-defined shots with no judged data as gray cells', () => {
  const merged = mergeLayoutShots(
    [
      { shot: '51', x: 0, y: 0, pass: true, dies: [{ serial: '0101', pass: true }] },
    ],
    [
      { custom: '51', col: 0, row: 0 },
      { custom: '61', col: 1, row: 0 },
    ],
  )

  assert.equal(merged.length, 2)
  assert.deepEqual(merged.find((shot) => shot.shot === '61')?.dies, [])
  assert.equal(merged.find((shot) => shot.shot === '61')?.x, 1)
})
