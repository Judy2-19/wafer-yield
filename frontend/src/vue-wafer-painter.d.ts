declare module 'vue-wafer-painter' {
  import type { DefineComponent } from 'vue'

  export interface Coords {
    info: string[]
    x: number
    y: number
    dut: number
    color: string
  }

  export const VWafermap: DefineComponent<
    {
      coords?: Coords[]
      width?: number
      height?: number
      notch?: 'top' | 'bottom' | 'left' | 'right' | 'none'
      backgroundColor?: string
      showTooltip?: boolean
      showDieInfo?: boolean
      showGrid?: boolean
      showBackground?: boolean
      showFocus?: boolean
      showAxisValues?: boolean
    },
    {},
    unknown,
    {},
    {},
    {},
    {},
    {
      onDie: (event: MouseEvent, dieInfo: Coords) => void
    }
  >
}
