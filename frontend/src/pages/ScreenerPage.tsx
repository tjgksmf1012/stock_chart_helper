import { useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, SlidersHorizontal } from 'lucide-react'

import { DashboardCard } from '@/components/dashboard/DashboardCard'
import { Card } from '@/components/ui/Card'
import { screenerApi } from '@/lib/api'
import { TIMEFRAME_OPTIONS } from '@/lib/timeframes'
import type { DashboardItem, ScreenerRequest, Timeframe } from '@/types/api'

type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'
type IntradayPreset = 'all' | 'ready-now' | 'watch' | 'recheck' | 'cooling'

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
  { value: 'armed', label: '완성 임박' },
  { value: 'confirmed', label: '확인 완료' },
]

const MARKET_OPTIONS = [
  { value: 'KOSPI', label: 'KOSPI' },
  { value: 'KOSDAQ', label: 'KOSDAQ' },
]

const FETCH_STATUS_OPTIONS = [
  { value: 'live_ok', label: '실시간 수집 성공' },
  { value: 'live_augmented_by_store', label: '실시간 + 저장 분봉' },
  { value: 'stored_fallback', label: '저장 분봉 대체' },
  { value: 'daily_ok', label: '일봉 수집 성공' },
]

const SORT_OPTIONS: Array<{ value: NonNullable<ScreenerRequest['sort_by']>; label: string }> = [
  { value: 'composite_score', label: '종합 점수' },
  { value: 'trade_readiness_score', label: '거래 준비도' },
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

export default function ScreenerPage() {
  const [req, setReq] = useState<ScreenerRequest>({
    min_textbook_similarity: 0.3,
    min_p_up: 0.0,
    min_confidence: 0.3,
    min_sample_reliability: 0.2,
    min_data_quality: 0.4,
    min_trade_readiness_score: 0.35,
    min_confluence_score: 0.0,
    min_historical_edge_score: 0.25,
    exclude_no_signal: true,
    sort_by: 'composite_score',
    limit: 20,
    timeframes: ['1d'],
  })
  const [submitted, setSubmitted] = useState(false)
  const [intradayView, setIntradayView] = useState<IntradayView>('all')
  const [intradayPreset, setIntradayPreset] = useState<IntradayPreset>('all')

  const { data, isLoading, refetch } = useQuery({
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
            ? item.live_intraday_candidate &&
              !item.no_signal_flag &&
              ['confirmed', 'trigger_ready', 'breakout_watch'].includes(item.setup_stage)
            : intradayPreset === 'watch'
              ? !item.no_signal_flag &&
                ['late_base', 'early_trigger_watch', 'base_building'].includes(item.setup_stage) &&
                item.formation_quality >= 0.5
              : intradayPreset === 'recheck'
                ? ['stored', 'public', 'mixed', 'budget'].includes(item.intraday_collection_mode) &&
                  item.data_quality >= 0.45
                : item.intraday_collection_mode === 'cooldown' || item.no_signal_flag

      return matchesView && matchesPreset
    })
  }, [data, intradayMode, intradayPreset, intradayView])

  const stats = useMemo(() => {
    if (!filteredData?.length) return null
    const kospi = filteredData.filter(item => item.symbol.market === 'KOSPI').length
    const kosdaq = filteredData.filter(item => item.symbol.market === 'KOSDAQ').length
    const avgReliability = filteredData.reduce((sum, item) => sum + item.sample_reliability, 0) / filteredData.length
    const avgReadiness = filteredData.reduce((sum, item) => sum + (item.trade_readiness_score ?? 0), 0) / filteredData.length
    const avgEdge = filteredData.reduce((sum, item) => sum + item.historical_edge_score, 0) / filteredData.length
    const avgRewardRisk = filteredData.reduce((sum, item) => sum + item.reward_risk_ratio, 0) / filteredData.length
    const liveCount = filteredData.filter(item => item.live_intraday_candidate).length
    const confirmedCount = filteredData.filter(item => item.state === 'confirmed').length
    const noSignalCount = filteredData.filter(item => item.no_signal_flag).length
    return { kospi, kosdaq, avgReliability, avgReadiness, avgEdge, avgRewardRisk, liveCount, confirmedCount, noSignalCount }
  }, [filteredData])

  const run = () => {
    setSubmitted(true)
    refetch()
  }

  const applyPreset = (preset: IntradayPreset) => {
    setIntradayPreset(preset)
  }

  const toggleMultiValue = (field: 'pattern_types' | 'states' | 'markets' | 'fetch_statuses', value: string) => {
    setReq(current => {
      const selected = current[field]?.includes(value)
      return {
        ...current,
        [field]: selected ? current[field]?.filter(item => item !== value) : [...(current[field] ?? []), value],
      }
    })
  }

  const toggleTimeframe = (value: Timeframe) => {
    setReq(current => {
      const selected = current.timeframes?.includes(value)
      return {
        ...current,
        timeframes: selected ? current.timeframes?.filter(item => item !== value) : [...(current.timeframes ?? []), value],
      }
    })
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <SlidersHorizontal size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">스크리너</h1>
          <p className="text-xs text-muted-foreground">
            패턴, 상태, 시장, 타임프레임뿐 아니라 표본 신뢰도와 데이터 상태까지 함께 걸러서 현재 스캔 결과를 좁혀 봅니다.
          </p>
        </div>
      </div>

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

        <SliderGroup
          label="최소 교과서 유사도"
          value={req.min_textbook_similarity ?? 0}
          onChange={value => setReq(current => ({ ...current, min_textbook_similarity: value }))}
        />

        <SliderGroup
          label="최소 상승 확률"
          value={req.min_p_up ?? 0}
          onChange={value => setReq(current => ({ ...current, min_p_up: value }))}
        />

        <SliderGroup
          label="최소 신뢰도"
          value={req.min_confidence ?? 0}
          onChange={value => setReq(current => ({ ...current, min_confidence: value }))}
        />

        <SliderGroup
          label="최소 표본 신뢰도"
          value={req.min_sample_reliability ?? 0}
          onChange={value => setReq(current => ({ ...current, min_sample_reliability: value }))}
        />

        <SliderGroup
          label="최소 데이터 품질"
          value={req.min_data_quality ?? 0}
          onChange={value => setReq(current => ({ ...current, min_data_quality: value }))}
        />

        <SliderGroup
          label="최소 거래 준비도"
          value={req.min_trade_readiness_score ?? 0}
          onChange={value => setReq(current => ({ ...current, min_trade_readiness_score: value }))}
        />

        <SliderGroup
          label="최소 합산 점수"
          value={req.min_confluence_score ?? 0}
          onChange={value => setReq(current => ({ ...current, min_confluence_score: value }))}
        />

        <SliderGroup
          label="최소 백테스트 edge"
          value={req.min_historical_edge_score ?? 0}
          onChange={value => setReq(current => ({ ...current, min_historical_edge_score: value }))}
        />

        <FilterGroup label="정렬 기준">
          <select
            value={req.sort_by ?? 'composite_score'}
            onChange={event => setReq(current => ({ ...current, sort_by: event.target.value as ScreenerRequest['sort_by'] }))}
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
            onChange={event => setReq(current => ({ ...current, limit: Number(event.target.value) }))}
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
              onChange={event => setReq(current => ({ ...current, exclude_no_signal: event.target.checked }))}
              className="accent-primary"
            />
            <span className="text-xs text-muted-foreground">No Signal 종목 제외</span>
          </label>
        </FilterGroup>
      </div>

      <button
        onClick={run}
        className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
      >
        <Search size={14} />
        스크리너 실행
      </button>

      {isLoading && <p className="text-xs text-muted-foreground">분석 중...</p>}

      {data && (
        <div className="space-y-4">
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
                  ['watch', '지켜볼 후보'],
                  ['recheck', '재확인 필요'],
                  ['cooling', '냉각/관망'],
                ] as Array<[IntradayPreset, string]>).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => applyPreset(value)}
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

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Card>
              <div className="text-xs text-muted-foreground">검색 결과</div>
              <div className="mt-1 text-lg font-semibold">{filteredData?.length ?? 0}개</div>
            </Card>
            <Card>
              <div className="text-xs text-muted-foreground">시장 분포</div>
              <div className="mt-1 text-sm font-medium">KOSPI {stats?.kospi ?? 0} / KOSDAQ {stats?.kosdaq ?? 0}</div>
            </Card>
            <Card>
              <div className="text-xs text-muted-foreground">평균 표본 신뢰도</div>
              <div className="mt-1 text-sm font-medium">{((stats?.avgReliability ?? 0) * 100).toFixed(0)}%</div>
            </Card>
            <Card>
              <div className="text-xs text-muted-foreground">평균 거래 준비도</div>
              <div className="mt-1 text-sm font-medium">{((stats?.avgReadiness ?? 0) * 100).toFixed(0)}%</div>
            </Card>
            <Card>
              <div className="text-xs text-muted-foreground">평균 백테스트 edge</div>
              <div className="mt-1 text-sm font-medium">{((stats?.avgEdge ?? 0) * 100).toFixed(0)}%</div>
            </Card>
          </div>

          {intradayMode && stats && (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <SummaryButton label="live 추적" value={`${stats.liveCount}개`} onClick={() => setIntradayView('live')} />
                <SummaryButton label="confirmed" value={`${stats.confirmedCount}개`} onClick={() => setIntradayPreset('ready-now')} />
                <SummaryButton label="No Signal" value={`${stats.noSignalCount}개`} onClick={() => setIntradayPreset('cooling')} />
                <SummaryButton label="평균 손익비" value={stats.avgRewardRisk.toFixed(2)} onClick={() => setIntradayPreset('ready-now')} />
              </div>

              <Card className="space-y-3">
                <div className="text-sm font-semibold">스크리너 컨텍스트</div>
                <p className="text-xs text-muted-foreground">{buildScreenerGuidance(filteredData ?? [])}</p>
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
            {(filteredData ?? data).map(item => (
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

function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-muted-foreground">{label}</div>
      {children}
    </div>
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

function buildScreenerGuidance(items: DashboardItem[]): string {
  if (items.length === 0) {
    return '현재 조건에 맞는 결과가 적습니다. 조건을 조금 완화하거나 다른 타임프레임도 함께 보는 편이 좋습니다.'
  }

  const liveCount = items.filter(item => item.live_intraday_candidate).length
  const confirmedCount = items.filter(item => item.state === 'confirmed').length
  const avgEdge = items.reduce((sum, item) => sum + item.historical_edge_score, 0) / items.length
  const avgRewardRisk = items.reduce((sum, item) => sum + item.reward_risk_ratio, 0) / items.length

  if (liveCount >= Math.max(2, Math.round(items.length * 0.35)) && confirmedCount >= Math.max(1, Math.round(items.length * 0.2))) {
    return '지금 스크리너 결과는 즉시 대응 후보가 제법 섞여 있습니다. live 후보와 confirmed 후보부터 우선 깊게 보세요.'
  }

  if (avgEdge >= 0.58 && avgRewardRisk >= 1.4) {
    return '평균 edge와 손익비는 무난합니다. 상위 결과 몇 개를 차트 상세로 내려가 확인하는 흐름이 좋습니다.'
  }

  return '확인 단계 후보가 더 많은 편입니다. 진입보다 재확인과 트리거 감시에 더 가까운 결과로 보는 편이 좋습니다.'
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
