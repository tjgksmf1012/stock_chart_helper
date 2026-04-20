import { useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, FilterX, Loader2, Search, SlidersHorizontal, Sparkles } from 'lucide-react'

import { DashboardCard } from '@/components/dashboard/DashboardCard'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { screenerApi } from '@/lib/api'
import { TIMEFRAME_OPTIONS } from '@/lib/timeframes'
import { fmtPct } from '@/lib/utils'
import type { DashboardItem, ScreenerRequest, Timeframe } from '@/types/api'

type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'
type IntradayPreset = 'all' | 'ready-now' | 'watch' | 'recheck' | 'cooling'
type QuickPresetId = 'daily-ready' | 'daily-fresh' | 'intraday-ready' | 'intraday-watch' | 'reentry-focus'

const DEFAULT_SCREENER_REQUEST: ScreenerRequest = {
  min_textbook_similarity: 0.25,
  min_p_up: 0.0,
  min_confidence: 0.2,
  min_sample_reliability: 0.1,
  min_data_quality: 0.3,
  min_trade_readiness_score: 0.25,
  min_entry_window_score: 0.15,
  min_freshness_score: 0.15,
  min_reentry_score: 0.1,
  min_reentry_compression_score: 0.1,
  min_reentry_volume_recovery_score: 0.1,
  min_reentry_trigger_hold_score: 0.1,
  min_reentry_wick_absorption_score: 0.1,
  min_reentry_failure_burden_score: 0.1,
  min_active_setup_score: 0.15,
  min_confluence_score: 0.0,
  min_historical_edge_score: 0.15,
  exclude_no_signal: true,
  sort_by: 'composite_score',
  limit: 20,
  timeframes: ['1d'],
}

const PATTERN_OPTIONS = [
  { value: 'double_bottom', label: '이중 바닥 (W)' },
  { value: 'double_top', label: '이중 천장 (M)' },
  { value: 'head_and_shoulders', label: '헤드 앤 숄더' },
  { value: 'inverse_head_and_shoulders', label: '역헤드 앤 숄더' },
  { value: 'ascending_triangle', label: '상승 삼각형' },
  { value: 'descending_triangle', label: '하락 삼각형' },
  { value: 'symmetric_triangle', label: '대칭 삼각형' },
  { value: 'rectangle', label: '박스권' },
]

const STATE_OPTIONS = [
  { value: 'forming', label: '형성 중' },
  { value: 'armed', label: '활성 임박' },
  { value: 'confirmed', label: '확인 완료' },
]

const MARKET_OPTIONS = [
  { value: 'KOSPI', label: 'KOSPI' },
  { value: 'KOSDAQ', label: 'KOSDAQ' },
]

const FETCH_STATUS_OPTIONS = [
  { value: 'live_ok', label: '실시간 수집 성공' },
  { value: 'live_augmented_by_store', label: '실시간 + 저장 보강' },
  { value: 'stored_fallback', label: '저장 분봉 대체' },
  { value: 'daily_ok', label: '일봉 수집 성공' },
]

const REENTRY_CASE_OPTIONS = [
  { value: 'box_reaccumulation', label: '박스 재축적형' },
  { value: 'pullback_relaunch', label: '눌림 후 재가속형' },
  { value: 'failed_breakout_recovery', label: '실패 돌파 복구형' },
  { value: 'range_reset', label: '재축적 준비형' },
  { value: 'primary_setup', label: '신규 셋업 우선형' },
  { value: 'avoid', label: '재진입 비선호' },
]

const SORT_OPTIONS: Array<{ value: NonNullable<ScreenerRequest['sort_by']>; label: string }> = [
  { value: 'composite_score', label: '종합 점수' },
  { value: 'trade_readiness_score', label: '거래 준비도' },
  { value: 'entry_window_score', label: '진입 구간' },
  { value: 'freshness_score', label: '패턴 신선도' },
  { value: 'reentry_score', label: '재진입 구조' },
  { value: 'reentry_compression_score', label: '박스 수축도' },
  { value: 'reentry_volume_recovery_score', label: '거래량 복원' },
  { value: 'reentry_trigger_hold_score', label: '기준선 유지력' },
  { value: 'reentry_wick_absorption_score', label: '꼬리 흡수력' },
  { value: 'reentry_failure_burden_score', label: '실패 부담 관리' },
  { value: 'active_setup_score', label: '활성 셋업' },
  { value: 'entry_score', label: '진입 적합도' },
  { value: 'sample_reliability', label: '표본 신뢰도' },
  { value: 'historical_edge_score', label: '백테스트 edge' },
  { value: 'confluence_score', label: '멀티 타임프레임 정렬' },
  { value: 'data_quality', label: '데이터 품질' },
  { value: 'p_up', label: '상승 확률' },
  { value: 'confidence', label: '신뢰도' },
  { value: 'textbook_similarity', label: '교과서 유사도' },
  { value: 'p_down', label: '하락 확률' },
]

const QUICK_PRESETS: Array<{
  id: QuickPresetId
  label: string
  description: string
  build: () => ScreenerRequest
}> = [
  {
    id: 'daily-ready',
    label: '일봉 실전형',
    description: '지금 당장 검토할 일봉 후보를 좁힙니다.',
    build: () => ({
      ...DEFAULT_SCREENER_REQUEST,
      timeframes: ['1d'],
      states: ['armed', 'confirmed'],
      min_trade_readiness_score: 0.45,
      min_entry_window_score: 0.35,
      min_freshness_score: 0.35,
      min_historical_edge_score: 0.2,
      sort_by: 'trade_readiness_score',
      limit: 20,
    }),
  },
  {
    id: 'daily-fresh',
    label: '일봉 신선도',
    description: '이미 끝난 패턴보다 아직 살아있는 일봉 구조를 봅니다.',
    build: () => ({
      ...DEFAULT_SCREENER_REQUEST,
      timeframes: ['1d', '1wk'],
      states: ['forming', 'armed'],
      min_freshness_score: 0.45,
      min_active_setup_score: 0.3,
      min_trade_readiness_score: 0.25,
      sort_by: 'freshness_score',
      limit: 24,
    }),
  },
  {
    id: 'intraday-ready',
    label: '분봉 즉시형',
    description: 'live/confirmed 쪽으로 바로 볼 분봉 후보를 찾습니다.',
    build: () => ({
      ...DEFAULT_SCREENER_REQUEST,
      timeframes: ['60m', '30m', '15m'],
      states: ['armed', 'confirmed'],
      min_trade_readiness_score: 0.45,
      min_entry_window_score: 0.4,
      min_data_quality: 0.45,
      min_historical_edge_score: 0.2,
      sort_by: 'entry_window_score',
      limit: 24,
    }),
  },
  {
    id: 'intraday-watch',
    label: '분봉 관찰형',
    description: 'forming/watch 중심으로 장중 지켜볼 후보를 넓게 봅니다.',
    build: () => ({
      ...DEFAULT_SCREENER_REQUEST,
      timeframes: ['60m', '30m', '15m'],
      states: ['forming', 'armed'],
      min_trade_readiness_score: 0.2,
      min_entry_window_score: 0.1,
      min_freshness_score: 0.25,
      min_data_quality: 0.35,
      sort_by: 'active_setup_score',
      limit: 30,
    }),
  },
  {
    id: 'reentry-focus',
    label: '재진입 집중',
    description: '재축적/재돌파 계열만 따로 보고 싶을 때 씁니다.',
    build: () => ({
      ...DEFAULT_SCREENER_REQUEST,
      timeframes: ['1d', '60m'],
      reentry_cases: ['box_reaccumulation', 'pullback_relaunch', 'failed_breakout_recovery'],
      min_reentry_score: 0.35,
      min_reentry_volume_recovery_score: 0.25,
      min_reentry_trigger_hold_score: 0.25,
      min_freshness_score: 0.25,
      sort_by: 'reentry_score',
      limit: 24,
    }),
  },
]

function exportToCsv(items: DashboardItem[]) {
  const headers = [
    '종목코드', '종목명', '시장', '타임프레임', '패턴', '상태',
    '상승확률(%)', '하락확률(%)', '교과서유사도(%)', '신뢰도(%)',
    '거래준비도(%)', '진입구간(%)', '패턴신선도(%)', '재진입구조(%)',
    '활성셋업(%)', '종합점수(%)', '백테스트edge(%)', '행동계획', '재진입유형',
  ]
  const rows = items.map(item => [
    item.symbol.code,
    item.symbol.name,
    item.symbol.market,
    item.timeframe,
    item.pattern_type ?? '',
    item.state ?? '',
    (item.p_up * 100).toFixed(1),
    (item.p_down * 100).toFixed(1),
    (item.textbook_similarity * 100).toFixed(1),
    (item.confidence * 100).toFixed(1),
    ((item.trade_readiness_score ?? 0) * 100).toFixed(1),
    ((item.entry_window_score ?? 0) * 100).toFixed(1),
    ((item.freshness_score ?? 0) * 100).toFixed(1),
    ((item.reentry_score ?? 0) * 100).toFixed(1),
    ((item.active_setup_score ?? 0) * 100).toFixed(1),
    (((item as unknown as Record<string, number>)['composite_score'] ?? item.entry_score) * 100).toFixed(1),
    ((item.historical_edge_score ?? 0) * 100).toFixed(1),
    item.action_plan_label ?? '',
    item.reentry_case_label ?? '',
  ])

  const csv = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `screener_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default function ScreenerPage() {
  const [req, setReq] = useState<ScreenerRequest>(DEFAULT_SCREENER_REQUEST)
  const [submitted, setSubmitted] = useState(false)
  const [intradayView, setIntradayView] = useState<IntradayView>('all')
  const [intradayPreset, setIntradayPreset] = useState<IntradayPreset>('all')
  const [activeQuickPreset, setActiveQuickPreset] = useState<QuickPresetId | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['screener', req],
    queryFn: () => screenerApi.run(req),
    enabled: submitted,
    staleTime: 30_000,
  })

  const intradayMode = (req.timeframes ?? []).some(value => ['60m', '30m', '15m', '1m'].includes(value))

  const filteredData = useMemo(() => {
    if (!data) return data
    if (!intradayMode) return data

    return data.filter(item => {
      const matchesView =
        intradayView === 'all'
          ? true
          : intradayView === 'live'
            ? item.live_intraday_candidate
            : !item.live_intraday_candidate && item.intraday_collection_mode === intradayView

      const matchesPreset =
        intradayPreset === 'all'
          ? true
          : intradayPreset === 'ready-now'
            ? item.live_intraday_candidate && !item.no_signal_flag && ['confirmed', 'trigger_ready', 'breakout_watch'].includes(item.setup_stage)
            : intradayPreset === 'watch'
              ? !item.no_signal_flag && ['late_base', 'early_trigger_watch', 'base_building'].includes(item.setup_stage)
              : intradayPreset === 'recheck'
                ? (item.freshness_score ?? 0) >= 0.35 && (item.data_quality ?? 0) >= 0.45
                : item.intraday_collection_mode === 'cooldown' || item.no_signal_flag

      return matchesView && matchesPreset
    })
  }, [data, intradayMode, intradayPreset, intradayView])

  const results = filteredData ?? data ?? []

  const stats = useMemo(() => {
    if (!filteredData?.length) return null

    const realItems = filteredData.filter(item => !isPlaceholderItem(item))
    const metricItems = realItems.length > 0 ? realItems : filteredData
    const placeholderCount = filteredData.length - realItems.length
    const kospi = filteredData.filter(item => item.symbol.market === 'KOSPI').length
    const kosdaq = filteredData.filter(item => item.symbol.market === 'KOSDAQ').length
    const avgReliability = metricItems.reduce((sum, item) => sum + item.sample_reliability, 0) / metricItems.length
    const avgReadiness = metricItems.reduce((sum, item) => sum + (item.trade_readiness_score ?? 0), 0) / metricItems.length
    const avgEntryWindow = metricItems.reduce((sum, item) => sum + (item.entry_window_score ?? 0), 0) / metricItems.length
    const avgFreshness = metricItems.reduce((sum, item) => sum + (item.freshness_score ?? 0), 0) / metricItems.length
    const avgReentry = metricItems.reduce((sum, item) => sum + (item.reentry_score ?? 0), 0) / metricItems.length
    const avgActiveSetup = metricItems.reduce((sum, item) => sum + (item.active_setup_score ?? 0), 0) / metricItems.length
    const avgRewardRisk = metricItems.reduce((sum, item) => sum + item.reward_risk_ratio, 0) / metricItems.length
    const liveCount = filteredData.filter(item => item.live_intraday_candidate).length
    const confirmedCount = metricItems.filter(item => item.state === 'confirmed').length
    const noSignalCount = filteredData.filter(item => item.no_signal_flag).length

    return {
      kospi,
      kosdaq,
      realCount: realItems.length,
      placeholderCount,
      isProvisionalOnly: realItems.length === 0 && placeholderCount > 0,
      avgReliability,
      avgReadiness,
      avgEntryWindow,
      avgFreshness,
      avgReentry,
      avgActiveSetup,
      avgRewardRisk,
      liveCount,
      confirmedCount,
      noSignalCount,
    }
  }, [filteredData])

  const activeFilterCount = useMemo(() => countActiveFilters(req), [req])
  const topCandidates = useMemo(() => results.slice(0, 3), [results])

  const run = () => {
    setSubmitted(true)
    refetch()
  }

  const relaxAndRun = () => {
    setReq(current => ({
      ...current,
      min_textbook_similarity: Math.min(current.min_textbook_similarity ?? 0.25, 0.2),
      min_confidence: Math.min(current.min_confidence ?? 0.2, 0.15),
      min_sample_reliability: Math.min(current.min_sample_reliability ?? 0.1, 0.05),
      min_data_quality: Math.min(current.min_data_quality ?? 0.3, 0.25),
      min_trade_readiness_score: Math.min(current.min_trade_readiness_score ?? 0.25, 0.2),
      min_entry_window_score: Math.min(current.min_entry_window_score ?? 0.15, 0.1),
      min_freshness_score: Math.min(current.min_freshness_score ?? 0.15, 0.1),
      min_reentry_score: Math.min(current.min_reentry_score ?? 0.1, 0.05),
      min_reentry_compression_score: Math.min(current.min_reentry_compression_score ?? 0.1, 0.05),
      min_reentry_volume_recovery_score: Math.min(current.min_reentry_volume_recovery_score ?? 0.1, 0.05),
      min_reentry_trigger_hold_score: Math.min(current.min_reentry_trigger_hold_score ?? 0.1, 0.05),
      min_reentry_wick_absorption_score: Math.min(current.min_reentry_wick_absorption_score ?? 0.1, 0.05),
      min_reentry_failure_burden_score: Math.min(current.min_reentry_failure_burden_score ?? 0.1, 0.05),
      min_active_setup_score: Math.min(current.min_active_setup_score ?? 0.15, 0.1),
      min_historical_edge_score: Math.min(current.min_historical_edge_score ?? 0.15, 0.1),
      exclude_no_signal: false,
      limit: Math.max(current.limit ?? 20, 30),
    }))
    setSubmitted(true)
    setActiveQuickPreset(null)
  }

  const resetFilters = () => {
    setReq(DEFAULT_SCREENER_REQUEST)
    setIntradayView('all')
    setIntradayPreset('all')
    setActiveQuickPreset(null)
  }

  const applyQuickPreset = (presetId: QuickPresetId) => {
    const preset = QUICK_PRESETS.find(item => item.id === presetId)
    if (!preset) return
    setReq(preset.build())
    setIntradayView('all')
    setIntradayPreset(presetId === 'intraday-ready' ? 'ready-now' : presetId === 'intraday-watch' ? 'watch' : 'all')
    setActiveQuickPreset(presetId)
    setSubmitted(true)
  }

  const toggleMultiValue = (field: 'pattern_types' | 'states' | 'markets' | 'fetch_statuses' | 'reentry_cases', value: string) => {
    setReq(current => {
      const selected = current[field]?.includes(value)
      return {
        ...current,
        [field]: selected ? current[field]?.filter(item => item !== value) : [...(current[field] ?? []), value],
      }
    })
    setActiveQuickPreset(null)
  }

  const toggleTimeframe = (value: Timeframe) => {
    setReq(current => {
      const selected = current.timeframes?.includes(value)
      return {
        ...current,
        timeframes: selected ? current.timeframes?.filter(item => item !== value) : [...(current.timeframes ?? []), value],
      }
    })
    setActiveQuickPreset(null)
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <SlidersHorizontal size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">스크리너</h1>
          <p className="text-xs text-muted-foreground">
            패턴, 상태, 시장, 타임프레임뿐 아니라 거래 준비도, 진입 구간, 패턴 신선도와 재진입 세부 구조까지 함께 걸러서 지금 실전에 가까운 후보를 찾습니다.
          </p>
        </div>
      </div>

      <Card className="space-y-4 border-primary/20 bg-primary/5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles size={15} className="text-primary" />
          빠른 시작 프리셋
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          처음부터 모든 슬라이더를 만지지 않아도 되도록, 자주 쓰는 실전 시나리오를 미리 묶어 두었습니다. 프리셋을 누른 뒤 바로 실행하거나, 그 상태에서 세부 조건만 조금 수정하면 됩니다.
        </p>
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-5">
          {QUICK_PRESETS.map(preset => (
            <button
              key={preset.id}
              onClick={() => applyQuickPreset(preset.id)}
              className={`rounded-xl border p-3 text-left transition-colors ${
                activeQuickPreset === preset.id
                  ? 'border-primary/40 bg-primary/10'
                  : 'border-border bg-background/60 hover:border-primary/30'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold">{preset.label}</div>
                {activeQuickPreset === preset.id && <Badge variant="bullish">활성</Badge>}
              </div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{preset.description}</p>
            </button>
          ))}
        </div>
      </Card>

      <Card className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">현재 필터 상태</div>
            <p className="mt-1 text-xs text-muted-foreground">
              선택된 타임프레임 {req.timeframes?.length ?? 0}개 · 활성 필터 {activeFilterCount}개 · 정렬 기준{' '}
              {SORT_OPTIONS.find(option => option.value === (req.sort_by ?? 'composite_score'))?.label}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={run}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <Search size={14} />
              스크리너 실행
            </button>
            <button
              onClick={resetFilters}
              className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              <FilterX size={14} />
              필터 초기화
            </button>
            {results.length > 0 && (
              <button
                onClick={() => exportToCsv(results)}
                className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
                title="검색 결과를 CSV로 내보내기"
              >
                <Download size={14} />
                CSV 내보내기
              </button>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Badge variant="muted">타임프레임 {req.timeframes?.map(timeframe => TIMEFRAME_OPTIONS.find(option => option.value === timeframe)?.label ?? timeframe).join(', ')}</Badge>
          <Badge variant="muted">정렬 {SORT_OPTIONS.find(option => option.value === (req.sort_by ?? 'composite_score'))?.label}</Badge>
          {(req.exclude_no_signal ?? true) && <Badge variant="warning">No Signal 제외</Badge>}
          {(req.min_trade_readiness_score ?? 0) >= 0.4 && <Badge variant="bullish">준비도 엄격</Badge>}
          {(req.min_freshness_score ?? 0) >= 0.4 && <Badge variant="neutral">신선도 엄격</Badge>}
          {(req.min_reentry_score ?? 0) >= 0.3 && <Badge variant="neutral">재진입 엄격</Badge>}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 rounded-lg border border-border bg-card p-4 md:grid-cols-2 lg:grid-cols-3">
        <FilterGroup label="타임프레임">
          <div className="flex flex-wrap gap-1.5">
            {TIMEFRAME_OPTIONS.map(option => {
              const selected = req.timeframes?.includes(option.value)
              return (
                <button
                  key={option.value}
                  onClick={() => toggleTimeframe(option.value)}
                  className={`rounded px-2 py-1 text-xs transition-colors ${
                    selected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <FilterGroup label="패턴 유형">
          <div className="flex flex-wrap gap-1.5">
            {PATTERN_OPTIONS.map(option => {
              const selected = req.pattern_types?.includes(option.value)
              return (
                <button
                  key={option.value}
                  onClick={() => toggleMultiValue('pattern_types', option.value)}
                  className={`rounded px-2 py-1 text-xs transition-colors ${
                    selected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <FilterGroup label="패턴 상태">
          <div className="flex flex-wrap gap-1.5">
            {STATE_OPTIONS.map(option => {
              const selected = req.states?.includes(option.value)
              return (
                <button
                  key={option.value}
                  onClick={() => toggleMultiValue('states', option.value)}
                  className={`rounded px-2 py-1 text-xs transition-colors ${
                    selected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <FilterGroup label="시장">
          <div className="flex flex-wrap gap-1.5">
            {MARKET_OPTIONS.map(option => {
              const selected = req.markets?.includes(option.value)
              return (
                <button
                  key={option.value}
                  onClick={() => toggleMultiValue('markets', option.value)}
                  className={`rounded px-2 py-1 text-xs transition-colors ${
                    selected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <FilterGroup label="데이터 상태">
          <div className="flex flex-wrap gap-1.5">
            {FETCH_STATUS_OPTIONS.map(option => {
              const selected = req.fetch_statuses?.includes(option.value)
              return (
                <button
                  key={option.value}
                  onClick={() => toggleMultiValue('fetch_statuses', option.value)}
                  className={`rounded px-2 py-1 text-xs transition-colors ${
                    selected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <FilterGroup label="재진입 유형">
          <div className="flex flex-wrap gap-1.5">
            {REENTRY_CASE_OPTIONS.map(option => {
              const selected = req.reentry_cases?.includes(option.value)
              return (
                <button
                  key={option.value}
                  onClick={() => toggleMultiValue('reentry_cases', option.value)}
                  className={`rounded px-2 py-1 text-xs transition-colors ${
                    selected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {option.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <SliderGroup label="최소 교과서 유사도" value={req.min_textbook_similarity ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_textbook_similarity: value })} />
        <SliderGroup label="최소 상승 확률" value={req.min_p_up ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_p_up: value })} />
        <SliderGroup label="최소 신뢰도" value={req.min_confidence ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_confidence: value })} />
        <SliderGroup label="최소 표본 신뢰도" value={req.min_sample_reliability ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_sample_reliability: value })} />
        <SliderGroup label="최소 데이터 품질" value={req.min_data_quality ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_data_quality: value })} />
        <SliderGroup label="최소 거래 준비도" value={req.min_trade_readiness_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_trade_readiness_score: value })} />
        <SliderGroup label="최소 진입 구간" value={req.min_entry_window_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_entry_window_score: value })} />
        <SliderGroup label="최소 패턴 신선도" value={req.min_freshness_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_freshness_score: value })} />
        <SliderGroup label="최소 재진입 구조" value={req.min_reentry_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_reentry_score: value })} />
        <SliderGroup label="최소 박스 수축도" value={req.min_reentry_compression_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_reentry_compression_score: value })} />
        <SliderGroup label="최소 거래량 복원" value={req.min_reentry_volume_recovery_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_reentry_volume_recovery_score: value })} />
        <SliderGroup label="최소 기준선 유지력" value={req.min_reentry_trigger_hold_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_reentry_trigger_hold_score: value })} />
        <SliderGroup label="최소 꼬리 흡수력" value={req.min_reentry_wick_absorption_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_reentry_wick_absorption_score: value })} />
        <SliderGroup label="최소 실패 부담 관리" value={req.min_reentry_failure_burden_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_reentry_failure_burden_score: value })} />
        <SliderGroup label="최소 활성 셋업" value={req.min_active_setup_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_active_setup_score: value })} />
        <SliderGroup label="최소 정렬 점수" value={req.min_confluence_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_confluence_score: value })} />
        <SliderGroup label="최소 백테스트 edge" value={req.min_historical_edge_score ?? 0} onChange={value => updateReq(setReq, setActiveQuickPreset, { min_historical_edge_score: value })} />

        <FilterGroup label="정렬 기준">
          <select
            value={req.sort_by ?? 'composite_score'}
            onChange={event => updateReq(setReq, setActiveQuickPreset, { sort_by: event.target.value as ScreenerRequest['sort_by'] })}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            {SORT_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterGroup>

        <FilterGroup label="결과 개수">
          <select
            value={req.limit ?? 20}
            onChange={event => updateReq(setReq, setActiveQuickPreset, { limit: Number(event.target.value) })}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            {[10, 20, 30, 50].map(value => (
              <option key={value} value={value}>
                {value}개
              </option>
            ))}
          </select>
        </FilterGroup>

        <FilterGroup label="No Signal 제외">
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={req.exclude_no_signal ?? true}
              onChange={event => updateReq(setReq, setActiveQuickPreset, { exclude_no_signal: event.target.checked })}
              className="accent-primary"
            />
            <span className="text-xs text-muted-foreground">No Signal 종목 제외</span>
          </label>
        </FilterGroup>
      </div>

      {isLoading && (
        <Card className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
          스크리너 분석을 실행하는 중입니다.
        </Card>
      )}

      {isError && !isLoading && (
        <Card>
          <QueryError message="스크리너 결과를 불러오지 못했습니다." onRetry={() => refetch()} />
        </Card>
      )}

      {!isLoading && !isError && submitted && data && results.length === 0 && (
        <Card className="space-y-2">
          <div className="text-sm font-semibold">조건에 맞는 종목이 없습니다.</div>
          <p className="text-xs text-muted-foreground">
            현재 필터가 꽤 엄격하거나, 선택한 타임프레임에서 실전형 후보가 아직 적을 수 있습니다. 최소 점수 조건을 조금 낮추거나 타임프레임을 넓혀 다시 확인해 보세요.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              onClick={relaxAndRun}
              className="rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs text-primary transition-colors hover:bg-primary/15"
            >
              조건 완화해서 다시 실행
            </button>
            <button
              onClick={() => {
                updateReq(setReq, setActiveQuickPreset, {
                  timeframes: ['1d', '1wk'],
                  limit: Math.max(req.limit ?? 20, 30),
                })
                setSubmitted(true)
              }}
              className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              일봉 + 주봉으로 넓혀보기
            </button>
          </div>
        </Card>
      )}

      {!isLoading && !isError && data && results.length > 0 && (
        <div className="space-y-4">
          <Card className="space-y-4 border-primary/20 bg-primary/5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles size={15} className="text-primary" />
              상위 후보 빠른 요약
            </div>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
              {topCandidates.map((item, index) => (
                <TopCandidateCard key={`${item.timeframe}-${item.symbol.code}`} item={item} rank={index + 1} />
              ))}
            </div>
          </Card>

          {intradayMode && (
            <>
              <div className="flex flex-wrap gap-2">
                {([
                  ['all', '전체'],
                  ['live', 'live'],
                  ['stored', 'stored'],
                  ['public', 'public'],
                  ['mixed', 'mixed'],
                  ['cooldown', 'cooldown'],
                ] as Array<[IntradayView, string]>).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setIntradayView(value)}
                    className={`rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                      intradayView === value
                        ? 'bg-primary text-primary-foreground'
                        : 'border border-border bg-card text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap gap-2">
                {([
                  ['all', '프리셋 전체'],
                  ['ready-now', '바로 볼 종목'],
                  ['watch', '관찰 후보'],
                  ['recheck', '재확인 필요'],
                  ['cooling', '관망 후보'],
                ] as Array<[IntradayPreset, string]>).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setIntradayPreset(value)}
                    className={`rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                      intradayPreset === value
                        ? 'bg-emerald-600 text-white'
                        : 'border border-border bg-card text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-7">
            <SummaryStat label="검색 결과" value={`${results.length}개`} />
            <SummaryStat label="시장 분포" value={`KOSPI ${stats?.kospi ?? 0} / KOSDAQ ${stats?.kosdaq ?? 0}`} />
            <SummaryStat label="실제 분석" value={`${stats?.realCount ?? 0}개`} />
            <SummaryStat label="임시 후보" value={`${stats?.placeholderCount ?? 0}개`} />
            <SummaryStat label="평균 표본 신뢰도" value={stats?.isProvisionalOnly ? '임시값' : `${((stats?.avgReliability ?? 0) * 100).toFixed(0)}%`} />
            <SummaryStat label="평균 거래 준비도" value={stats?.isProvisionalOnly ? '임시값' : `${((stats?.avgReadiness ?? 0) * 100).toFixed(0)}%`} />
            <SummaryStat label="평균 진입 구간" value={stats?.isProvisionalOnly ? '임시값' : `${((stats?.avgEntryWindow ?? 0) * 100).toFixed(0)}%`} />
            <SummaryStat label="평균 패턴 신선도" value={stats?.isProvisionalOnly ? '임시값' : `${((stats?.avgFreshness ?? 0) * 100).toFixed(0)}%`} />
            <SummaryStat label="평균 재진입 구조" value={stats?.isProvisionalOnly ? '임시값' : `${((stats?.avgReentry ?? 0) * 100).toFixed(0)}%`} />
          </div>

          {intradayMode && stats && (
            <>
              {stats.isProvisionalOnly && (
                <Card className="border-amber-500/20 bg-amber-500/5 text-amber-100">
                  <div className="text-sm font-semibold">빠른 예열 후보만 표시 중입니다</div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    지금 보이는 점수와 평균값은 임시값입니다. 백그라운드 분봉 스캔이 끝나면 실제 패턴, 준비도, 재진입 구조로 자동 교체됩니다.
                  </p>
                </Card>
              )}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <SummaryButton label="live 추적" value={`${stats.liveCount}개`} onClick={() => setIntradayView('live')} />
                <SummaryButton label="confirmed" value={`${stats.confirmedCount}개`} onClick={() => setIntradayPreset('ready-now')} />
                <SummaryButton label="No Signal" value={`${stats.noSignalCount}개`} onClick={() => setIntradayPreset('cooling')} />
                <SummaryButton label="평균 손익비" value={stats.isProvisionalOnly ? '임시값' : stats.avgRewardRisk.toFixed(2)} onClick={() => setIntradayPreset('ready-now')} />
              </div>

              <Card className="space-y-3">
                <div className="text-sm font-semibold">스크리너 컨텍스트</div>
                <p className="text-xs text-muted-foreground">{buildScreenerGuidance(results)}</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => {
                      setIntradayView('all')
                      setIntradayPreset('all')
                    }}
                    className="rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                  >
                    전체 보기
                  </button>
                  <button
                    onClick={() => setIntradayPreset('watch')}
                    className="rounded-md border border-violet-500/30 bg-violet-500/10 px-2.5 py-1.5 text-xs text-violet-100 transition-colors hover:bg-violet-500/15"
                  >
                    forming/watch
                  </button>
                  <button
                    onClick={() => setIntradayPreset('recheck')}
                    className="rounded-md border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-xs text-sky-100 transition-colors hover:bg-sky-500/15"
                  >
                    재확인 필요
                  </button>
                </div>
              </Card>
            </>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {results.map(item => (
              <DashboardCard
                key={`${item.timeframe}-${item.symbol.code}`}
                item={item}
                intradayPreset={intradayMode ? intradayPreset : undefined}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function updateReq(
  setReq: React.Dispatch<React.SetStateAction<ScreenerRequest>>,
  setActiveQuickPreset: React.Dispatch<React.SetStateAction<QuickPresetId | null>>,
  patch: Partial<ScreenerRequest>,
) {
  setReq(current => ({ ...current, ...patch }))
  setActiveQuickPreset(null)
}

function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-muted-foreground">{label}</div>
      {children}
    </div>
  )
}

function SliderGroup({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <FilterGroup label={label}>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={value}
        onChange={event => onChange(Number(event.target.value))}
        className="w-full accent-primary"
      />
      <span className="text-xs text-muted-foreground">{(value * 100).toFixed(0)}%</span>
    </FilterGroup>
  )
}

function SummaryButton({ label, value, onClick }: { label: string; value: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-primary/40 hover:bg-card/80"
    >
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </button>
  )
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </Card>
  )
}

function TopCandidateCard({ item, rank }: { item: DashboardItem; rank: number }) {
  return (
    <div className="rounded-xl border border-border bg-background/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-xs text-muted-foreground">상위 후보 #{rank}</div>
          <div className="mt-1 text-sm font-semibold">
            {item.symbol.name} <span className="font-mono text-xs text-muted-foreground">{item.symbol.code}</span>
          </div>
        </div>
        <Badge variant="muted">{item.timeframe_label}</Badge>
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
        <Badge variant={item.p_up >= 0.6 ? 'bullish' : 'neutral'}>상승 {fmtPct(item.p_up, 0)}</Badge>
        <Badge variant={item.trade_readiness_score >= 0.6 ? 'bullish' : 'neutral'}>준비 {fmtPct(item.trade_readiness_score ?? 0, 0)}</Badge>
        <Badge variant={item.entry_window_score >= 0.55 ? 'bullish' : 'warning'}>진입 {fmtPct(item.entry_window_score ?? 0, 0)}</Badge>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{item.action_plan_summary || item.reason_summary}</p>
      {item.next_trigger && (
        <div className="mt-2 text-xs text-primary">
          다음 트리거: {item.next_trigger}
        </div>
      )}
    </div>
  )
}

function buildScreenerGuidance(items: DashboardItem[]): string {
  if (items.length === 0) {
    return '현재 조건에 맞는 결과가 없습니다. 신선도, 준비도 조건을 조금 완화하거나 다른 타임프레임을 함께 보는 것이 좋습니다.'
  }

  const realItems = items.filter(item => !isPlaceholderItem(item))
  if (realItems.length === 0) {
    return '지금은 빠른 예열 후보만 먼저 보여주고 있습니다. 평균 점수보다는 후보 풀과 시장 분포만 가볍게 확인하고, 실제 분봉 스캔이 끝난 뒤 다시 판단하세요.'
  }

  const liveCount = realItems.filter(item => item.live_intraday_candidate).length
  const readyCount = realItems.filter(item => (item.trade_readiness_score ?? 0) >= 0.6).length
  const avgFreshness = realItems.reduce((sum, item) => sum + (item.freshness_score ?? 0), 0) / realItems.length
  const reentryCases = realItems
    .map(item => item.reentry_case_label)
    .filter(label => !!label && label !== '구조 없음')
  const dominantReentryCase =
    reentryCases.length > 0
      ? [...new Set(reentryCases)].sort(
          (left, right) => reentryCases.filter(value => value === right).length - reentryCases.filter(value => value === left).length,
        )[0]
      : ''

  if (liveCount >= Math.max(2, Math.round(realItems.length * 0.3))) {
    return `실시간 추적 후보가 충분합니다. live 후보부터 확인하고, 신선도와 진입 구간이 동시에 높으면서 재진입 구조까지 받쳐주는 종목을 우선 보세요${dominantReentryCase ? `. 현재는 ${dominantReentryCase} 비중이 높습니다.` : '.'}`
  }

  if (readyCount >= Math.max(2, Math.round(realItems.length * 0.25)) && avgFreshness >= 0.5) {
    return `거래 준비도와 패턴 신선도가 함께 받쳐주는 후보가 모여 있습니다. 상위 카드에서 리스크 기준, 재진입 구조, 다음 트리거를 먼저 확인해 보세요${dominantReentryCase ? `. 특히 ${dominantReentryCase}이 많이 보입니다.` : '.'}`
  }

  return `아직은 형성 중이거나 재확인이 필요한 후보가 많습니다. 무리한 진입보다 목표가 소진 여부, 신선도, 재축적 여부를 먼저 체크하는 편이 좋습니다${dominantReentryCase ? `. 현재 주된 유형은 ${dominantReentryCase}입니다.` : '.'}`
}

function countActiveFilters(req: ScreenerRequest): number {
  let count = 0
  if ((req.timeframes?.length ?? 0) !== (DEFAULT_SCREENER_REQUEST.timeframes?.length ?? 0) || req.timeframes?.some(value => !(DEFAULT_SCREENER_REQUEST.timeframes ?? []).includes(value))) count += 1
  if ((req.pattern_types?.length ?? 0) > 0) count += 1
  if ((req.states?.length ?? 0) > 0) count += 1
  if ((req.markets?.length ?? 0) > 0) count += 1
  if ((req.fetch_statuses?.length ?? 0) > 0) count += 1
  if ((req.reentry_cases?.length ?? 0) > 0) count += 1

  const numericKeys: Array<keyof ScreenerRequest> = [
    'min_textbook_similarity',
    'min_p_up',
    'min_confidence',
    'min_sample_reliability',
    'min_data_quality',
    'min_trade_readiness_score',
    'min_entry_window_score',
    'min_freshness_score',
    'min_reentry_score',
    'min_reentry_compression_score',
    'min_reentry_volume_recovery_score',
    'min_reentry_trigger_hold_score',
    'min_reentry_wick_absorption_score',
    'min_reentry_failure_burden_score',
    'min_active_setup_score',
    'min_confluence_score',
    'min_historical_edge_score',
    'limit',
  ]
  for (const key of numericKeys) {
    if ((req[key] as number | undefined) !== (DEFAULT_SCREENER_REQUEST[key] as number | undefined)) {
      count += 1
    }
  }

  if ((req.sort_by ?? DEFAULT_SCREENER_REQUEST.sort_by) !== DEFAULT_SCREENER_REQUEST.sort_by) count += 1
  if ((req.exclude_no_signal ?? DEFAULT_SCREENER_REQUEST.exclude_no_signal) !== DEFAULT_SCREENER_REQUEST.exclude_no_signal) count += 1

  return count
}

function isPlaceholderItem(item: DashboardItem): boolean {
  return item.fetch_status === 'placeholder_pending'
}
