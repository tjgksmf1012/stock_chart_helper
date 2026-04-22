import type { Timeframe } from '@/types/api'

export const DEFAULT_TIMEFRAME: Timeframe = '1d'
export const DISPLAY_TIMEFRAME_VALUES: Timeframe[] = ['1mo', '1wk', '1d']

export const TIMEFRAME_OPTIONS: Array<{ value: Timeframe; label: string; bucket: 'swing' | 'intraday' }> = [
  { value: '1mo', label: '월봉', bucket: 'swing' },
  { value: '1wk', label: '주봉', bucket: 'swing' },
  { value: '1d', label: '일봉', bucket: 'swing' },
]

const ALL_TIMEFRAME_OPTIONS: Array<{ value: Timeframe; label: string; bucket: 'swing' | 'intraday' }> = [
  ...TIMEFRAME_OPTIONS,
  { value: '60m', label: '60분', bucket: 'intraday' },
  { value: '30m', label: '30분', bucket: 'intraday' },
  { value: '15m', label: '15분', bucket: 'intraday' },
  { value: '1m', label: '1분', bucket: 'intraday' },
]

export function normalizeDisplayTimeframe(timeframe: Timeframe | null | undefined): Timeframe {
  if (!timeframe) return DEFAULT_TIMEFRAME
  return DISPLAY_TIMEFRAME_VALUES.includes(timeframe) ? timeframe : DEFAULT_TIMEFRAME
}

export function timeframeLabel(timeframe: Timeframe): string {
  return ALL_TIMEFRAME_OPTIONS.find(option => option.value === timeframe)?.label ?? timeframe
}

export function getChartLookbackDays(timeframe: Timeframe): number {
  switch (timeframe) {
    case '1mo':
      return 3650
    case '1wk':
      return 1825
    case '1d':
      return 730
    case '60m':
      return 365
    case '30m':
      return 120
    case '15m':
      return 90
    case '1m':
      return 14
    default:
      return 365
  }
}

export function getContextTimeframes(timeframe: Timeframe): Timeframe[] {
  switch (timeframe) {
    case '1mo':
      return ['1wk', '1d']
    case '1wk':
      return ['1mo', '1d']
    case '1d':
      return ['1wk', '1mo']
    default:
      return []
  }
}
