import type { DashboardItem } from '@/types/api'

export type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'
export type IntradayPreset = 'all' | 'ready-now' | 'watch' | 'recheck' | 'cooling'

export const INTRADAY_VIEW_OPTIONS: Array<[IntradayView, string]> = [
  ['all', '전체'],
  ['live', 'Live'],
  ['stored', '저장'],
  ['public', '공개'],
  ['mixed', '혼합'],
  ['cooldown', '쿨다운'],
]

export const INTRADAY_PRESET_OPTIONS: Array<[IntradayPreset, string]> = [
  ['all', '전체'],
  ['ready-now', '지금 볼 후보'],
  ['watch', '지켜볼 후보'],
  ['recheck', '재확인 필요'],
  ['cooling', '관망'],
]

function matchesIntradayView(item: DashboardItem, view: IntradayView): boolean {
  if (view === 'all') return true
  if (view === 'live') return item.live_intraday_candidate
  return !item.live_intraday_candidate && item.intraday_collection_mode === view
}

function matchesIntradayPreset(item: DashboardItem, preset: IntradayPreset): boolean {
  if (preset === 'all') return true
  if (preset === 'ready-now') {
    return (
      item.live_intraday_candidate &&
      !item.no_signal_flag &&
      ['confirmed', 'trigger_ready', 'breakout_watch'].includes(item.setup_stage)
    )
  }
  if (preset === 'watch') {
    return (
      !item.no_signal_flag &&
      ['late_base', 'early_trigger_watch', 'base_building'].includes(item.setup_stage) &&
      item.formation_quality >= 0.5
    )
  }
  if (preset === 'recheck') {
    return ['stored', 'public', 'mixed', 'budget'].includes(item.intraday_collection_mode) && item.data_quality >= 0.45
  }
  return item.intraday_collection_mode === 'cooldown' || item.no_signal_flag
}

/** intradayMode가 아니면(일/주/월봉) 필터를 적용하지 않고 그대로 반환한다. */
export function filterIntradayItems<T extends DashboardItem>(
  items: T[],
  intradayMode: boolean,
  view: IntradayView,
  preset: IntradayPreset,
): T[] {
  if (!intradayMode) return items
  return items.filter(item => matchesIntradayView(item, view) && matchesIntradayPreset(item, preset))
}
