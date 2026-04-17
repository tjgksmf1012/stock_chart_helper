import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, SlidersHorizontal } from 'lucide-react'

import { DashboardCard } from '@/components/dashboard/DashboardCard'
import { Card } from '@/components/ui/Card'
import { screenerApi } from '@/lib/api'
import type { ScreenerRequest } from '@/types/api'

const PATTERN_OPTIONS = [
  { value: 'double_bottom', label: '이중 바닥 (W)' },
  { value: 'double_top', label: '이중 천장 (M)' },
  { value: 'head_and_shoulders', label: '헤드앤숄더' },
  { value: 'inverse_head_and_shoulders', label: '역헤드앤숄더' },
  { value: 'ascending_triangle', label: '상승 삼각형' },
  { value: 'descending_triangle', label: '하락 삼각형' },
  { value: 'symmetric_triangle', label: '대칭 삼각형' },
  { value: 'rectangle', label: '박스권' },
]

const STATE_OPTIONS = [
  { value: 'forming', label: '형성 중' },
  { value: 'armed', label: '확인 직전' },
  { value: 'confirmed', label: '확인 완료' },
]

const MARKET_OPTIONS = [
  { value: 'KOSPI', label: 'KOSPI' },
  { value: 'KOSDAQ', label: 'KOSDAQ' },
]

const SORT_OPTIONS = [
  { value: 'entry_score', label: '진입 적합도' },
  { value: 'p_up', label: '상승 확률' },
  { value: 'textbook_similarity', label: '교과서 유사도' },
  { value: 'confidence', label: '신뢰도' },
  { value: 'p_down', label: '하락 확률' },
]

const PRESETS: Array<{ label: string; description: string; patch: Partial<ScreenerRequest> }> = [
  {
    label: '돌파 후보',
    description: '확인 직전 패턴 위주로 빠르게 보기',
    patch: { states: ['armed'], min_textbook_similarity: 0.55, min_p_up: 0.5, min_confidence: 0.35, sort_by: 'entry_score' },
  },
  {
    label: '상승 강세',
    description: '상승 확률이 높은 종목만 보기',
    patch: { min_p_up: 0.65, min_textbook_similarity: 0.4, min_confidence: 0.35, sort_by: 'p_up' },
  },
  {
    label: '교과서형',
    description: '유사도가 높은 예쁜 패턴 보기',
    patch: { min_textbook_similarity: 0.7, min_p_up: 0.0, min_confidence: 0.25, sort_by: 'textbook_similarity' },
  },
]

export default function ScreenerPage() {
  const [req, setReq] = useState<ScreenerRequest>({
    min_textbook_similarity: 0.3,
    min_p_up: 0.0,
    min_confidence: 0.0,
    exclude_no_signal: true,
    sort_by: 'entry_score',
    limit: 20,
  })
  const [submitted, setSubmitted] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['screener', req],
    queryFn: () => screenerApi.run(req),
    enabled: submitted,
    staleTime: 30_000,
  })

  const stats = useMemo(() => {
    if (!data?.length) return null
    const kospi = data.filter(item => item.symbol.market === 'KOSPI').length
    const kosdaq = data.filter(item => item.symbol.market === 'KOSDAQ').length
    const noSignal = data.filter(item => item.no_signal_flag).length
    return { kospi, kosdaq, noSignal }
  }, [data])

  const run = () => {
    setSubmitted(true)
    refetch()
  }

  const toggleMultiValue = (field: 'pattern_types' | 'states' | 'markets', value: string) => {
    setReq(current => {
      const selected = current[field]?.includes(value)
      return {
        ...current,
        [field]: selected
          ? current[field]?.filter(item => item !== value)
          : [...(current[field] ?? []), value],
      }
    })
  }

  const applyPreset = (patch: Partial<ScreenerRequest>) => {
    setReq(current => ({ ...current, ...patch }))
    setSubmitted(true)
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <SlidersHorizontal size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">스크리너</h1>
          <p className="text-xs text-muted-foreground">패턴, 상태, 시장, 확률 조건으로 현재 스캔 결과를 필터링합니다.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {PRESETS.map(preset => (
          <Card key={preset.label} className="space-y-3">
            <div>
              <div className="text-sm font-semibold">{preset.label}</div>
              <p className="mt-1 text-xs text-muted-foreground">{preset.description}</p>
            </div>
            <button
              onClick={() => applyPreset(preset.patch)}
              className="rounded-md bg-primary/15 px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-primary/25"
            >
              프리셋 적용
            </button>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 rounded-lg border border-border bg-card p-4 md:grid-cols-2 lg:grid-cols-3">
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

        <FilterGroup label="최소 교과서 유사도">
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={req.min_textbook_similarity ?? 0}
            onChange={event => setReq(current => ({ ...current, min_textbook_similarity: Number(event.target.value) }))}
            className="w-full accent-primary"
          />
          <span className="text-xs text-muted-foreground">{((req.min_textbook_similarity ?? 0) * 100).toFixed(0)}%</span>
        </FilterGroup>

        <FilterGroup label="최소 상승 확률">
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={req.min_p_up ?? 0}
            onChange={event => setReq(current => ({ ...current, min_p_up: Number(event.target.value) }))}
            className="w-full accent-primary"
          />
          <span className="text-xs text-muted-foreground">{((req.min_p_up ?? 0) * 100).toFixed(0)}%</span>
        </FilterGroup>

        <FilterGroup label="최소 신뢰도">
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={req.min_confidence ?? 0}
            onChange={event => setReq(current => ({ ...current, min_confidence: Number(event.target.value) }))}
            className="w-full accent-primary"
          />
          <span className="text-xs text-muted-foreground">{((req.min_confidence ?? 0) * 100).toFixed(0)}%</span>
        </FilterGroup>

        <FilterGroup label="정렬 기준">
          <select
            value={req.sort_by ?? 'entry_score'}
            onChange={event => setReq(current => ({ ...current, sort_by: event.target.value as ScreenerRequest['sort_by'] }))}
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            {SORT_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
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
              <option key={value} value={value}>{value}개</option>
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
        스크리닝 실행
      </button>

      {isLoading && <p className="text-xs text-muted-foreground">분석 중...</p>}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Card>
              <div className="text-xs text-muted-foreground">검색 결과</div>
              <div className="mt-1 text-lg font-semibold">{data.length}개</div>
            </Card>
            <Card>
              <div className="text-xs text-muted-foreground">시장 분포</div>
              <div className="mt-1 text-sm font-medium">KOSPI {stats?.kospi ?? 0} / KOSDAQ {stats?.kosdaq ?? 0}</div>
            </Card>
            <Card>
              <div className="text-xs text-muted-foreground">No Signal 포함 수</div>
              <div className="mt-1 text-sm font-medium">{stats?.noSignal ?? 0}개</div>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.map(item => <DashboardCard key={item.symbol.code} item={item} />)}
          </div>
        </div>
      )}
    </div>
  )
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-muted-foreground">{label}</div>
      {children}
    </div>
  )
}
