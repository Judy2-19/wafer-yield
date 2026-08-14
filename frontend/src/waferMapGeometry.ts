export type WaferViewSettings = {
  waferScale: number
  waferOffsetX: number
  waferOffsetY: number
}

export type WaferGrid = { minX: number; maxX: number; minY: number; maxY: number }

export type WaferDieGridCell = {
  serial: string | null
  row: number
  col: number
  empty?: boolean
}

export type WaferShot = {
  shot: string
  x: number | null
  y: number | null
  pass: boolean
  dies?: Array<{ serial?: string | null; pass?: boolean; manual_untested?: boolean }>
}

export type LayoutShot = { custom: string; col: number; row: number }

export type WaferGeometry = {
  size: number
  shotWidth: number
  shotHeight: number
  dieWidth: number
  dieHeight: number
  gridCx: number
  gridCy: number
  cx: number
  cy: number
  radius: number
  minX: number
  minY: number
  dieMinRow: number
  dieMinCol: number
  dieRows: number
  dieCols: number
  shotRows: number
  shotCols: number
}

export type WaferCellStatus = 'pass' | 'fail' | 'missing' | 'manual-untested' | 'test-key'

export type WaferCell = {
  shot: string
  serial: string | null
  x: number
  y: number
  width: number
  height: number
  status: WaferCellStatus
  color: string
  clickable: boolean
}

const COLORS: Record<WaferCellStatus, string> = {
  pass: '#00c853',
  fail: '#ff3d3d',
  missing: '#cbd5e1',
  'manual-untested': '#94a3b8',
  'test-key': '#ffd600',
}

export function compactShotLabel(value: string): string {
  const n = Number(value)
  if (!Number.isInteger(n) || n < 100) return String(value)
  const tens = Math.floor(n / 10)
  const ones = n % 10
  return tens < 36 ? `${tens.toString(36).toUpperCase()}${ones}` : String(value)
}

export function mergeLayoutShots(shots: WaferShot[], layoutShots: LayoutShot[]): WaferShot[] {
  const judgedByShot = new Map(shots.map((shot) => [shot.shot, shot]))
  const merged = layoutShots.map((layoutShot) => {
    const judged = judgedByShot.get(String(layoutShot.custom))
    return judged || {
      shot: String(layoutShot.custom),
      x: layoutShot.col,
      y: layoutShot.row,
      pass: false,
      dies: [],
    }
  })
  const layoutKeys = new Set(layoutShots.map((shot) => String(shot.custom)))
  merged.push(...shots.filter((shot) => !layoutKeys.has(shot.shot)))
  return merged
}

export function computeWaferGeometry(input: {
  size: number
  grid: WaferGrid
  dieGrid: WaferDieGridCell[]
  settings: WaferViewSettings
}): WaferGeometry {
  const { size, grid, dieGrid, settings } = input
  const dieMinRow = dieGrid.length ? Math.min(...dieGrid.map((cell) => cell.row)) : 0
  const dieMinCol = dieGrid.length ? Math.min(...dieGrid.map((cell) => cell.col)) : 0
  const dieMaxRow = dieGrid.length ? Math.max(...dieGrid.map((cell) => cell.row)) : 0
  const dieMaxCol = dieGrid.length ? Math.max(...dieGrid.map((cell) => cell.col)) : 0
  const dieRows = dieMaxRow - dieMinRow + 1
  const dieCols = dieMaxCol - dieMinCol + 1
  const shotCols = Math.max(1, grid.maxX - grid.minX + 1)
  const shotRows = Math.max(1, grid.maxY - grid.minY + 1)
  const pad = size * 0.06
  const maxShotWidth = (size - pad * 2) / shotCols
  const maxShotHeight = (size - pad * 2) / shotRows
  const dieWidth = maxShotWidth / dieCols
  const dieHeight = maxShotHeight / dieRows
  const shotWidth = dieWidth * dieCols
  const shotHeight = dieHeight * dieRows
  const gridCx = size / 2
  const gridCy = size / 2
  const automaticRadius = Math.min(shotCols * shotWidth, shotRows * shotHeight) / 2 + Math.hypot(shotWidth, shotHeight) * 0.32
  const radius = automaticRadius * settings.waferScale
  return {
    size,
    shotWidth,
    shotHeight,
    dieWidth,
    dieHeight,
    gridCx,
    gridCy,
    cx: gridCx + settings.waferOffsetX * shotWidth,
    cy: gridCy - settings.waferOffsetY * shotHeight,
    radius,
    minX: grid.minX,
    minY: grid.minY,
    dieMinRow,
    dieMinCol,
    dieRows,
    dieCols,
    shotRows,
    shotCols,
  }
}

export function shotRect(shot: WaferShot, geometry: WaferGeometry) {
  const col = (shot.x ?? geometry.minX) - geometry.minX
  const row = (shot.y ?? geometry.minY) - geometry.minY
  const centerX = geometry.gridCx + (col - (geometry.shotCols - 1) / 2) * geometry.shotWidth
  const centerY = geometry.gridCy + (row - (geometry.shotRows - 1) / 2) * geometry.shotHeight
  return {
    x: centerX - geometry.shotWidth / 2,
    y: centerY - geometry.shotHeight / 2,
    width: geometry.shotWidth,
    height: geometry.shotHeight,
    centerX,
    centerY,
  }
}

export function shotIntersectsWafer(
  rect: ReturnType<typeof shotRect>,
  geometry: WaferGeometry,
): boolean {
  const nearestX = Math.max(rect.x, Math.min(geometry.cx, rect.x + rect.width))
  const nearestY = Math.max(rect.y, Math.min(geometry.cy, rect.y + rect.height))
  return Math.hypot(nearestX - geometry.cx, nearestY - geometry.cy) <= geometry.radius
}

export function buildWaferCells(input: {
  geometry: WaferGeometry
  dieGrid: WaferDieGridCell[]
  shots: WaferShot[]
}): WaferCell[] {
  const { geometry, dieGrid, shots } = input
  const cells: WaferCell[] = []
  for (const shot of shots) {
    if (shot.x == null || shot.y == null) continue
    const rect = shotRect(shot, geometry)
    const dieBySerial = new Map((shot.dies || []).filter((die) => die.serial).map((die) => [die.serial as string, die]))
    for (const cell of dieGrid) {
      const testKey = !!cell.empty || !cell.serial
      const die = cell.serial ? dieBySerial.get(cell.serial) : undefined
      const status: WaferCellStatus = testKey
        ? 'test-key'
        : !die
          ? 'missing'
          : die.manual_untested
            ? 'manual-untested'
            : die.pass
              ? 'pass'
              : 'fail'
      cells.push({
        shot: shot.shot,
        serial: cell.serial,
        x: rect.x + (cell.col - geometry.dieMinCol) * geometry.dieWidth,
        y: rect.y + (cell.row - geometry.dieMinRow) * geometry.dieHeight,
        width: geometry.dieWidth,
        height: geometry.dieHeight,
        status,
        color: COLORS[status],
        clickable: !testKey,
      })
    }
  }
  return cells
}

export function hitTestCell(cells: WaferCell[], x: number, y: number): WaferCell | null {
  return cells.find((cell) => cell.clickable && x >= cell.x && x <= cell.x + cell.width && y >= cell.y && y <= cell.y + cell.height) ?? null
}
