import type { Timeframe } from '@/types/api'

export const TIMEFRAME_OPTIONS: Array<{ value: Timeframe; label: string; group: 'swing' | 'scalp' }> = [
  { value: '1mo', label: '월봉', group: 'swing' },
  { value: '1wk', label: '주봉', group: 'swing' },
  { value: '1d', label: '일봉', group: 'swing' },
  { value: '60m', label: '60분', group: 'scalp' },
  { value: '30m', label: '30분', group: 'scalp' },
  { value: '15m', label: '15분', group: 'scalp' },
  { value: '1m', label: '1분', group: 'scalp' },
]

export const DEFAULT_TIMEFRAME: Timeframe = '1d'

export function getChartLookbackDays(timeframe: Timeframe): number {
  switch (timeframe) {
    case '1mo':
      return 3650
    case '1wk':
      return 1825
    case '1d':
      return 365
    case '60m':
      return 120
    case '30m':
      return 60
    case '15m':
      return 30
    case '1m':
      return 7
    default:
      return 365
  }
}

export function timeframeLabel(timeframe: Timeframe | string | null | undefined): string {
  if (!timeframe) return '-'
  return TIMEFRAME_OPTIONS.find(option => option.value === timeframe)?.label ?? timeframe
}
