import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { screenerApi } from '@/lib/api'
import { DashboardCard } from '@/components/dashboard/DashboardCard'
import { SlidersHorizontal, Search } from 'lucide-react'
import type { ScreenerRequest } from '@/types/api'

const PATTERN_OPTIONS = [
  { value: 'double_bottom', label: '이중바닥 (W)' },
  { value: 'double_top', label: '이중천장 (M)' },
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

export default function ScreenerPage() {
  const [req, setReq] = useState<ScreenerRequest>({
    min_textbook_similarity: 0.3,
    min_p_up: 0.0,
    min_confidence: 0.0,
    exclude_no_signal: true,
    limit: 20,
  })
  const [submitted, setSubmitted] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['screener', req],
    queryFn: () => screenerApi.run(req),
    enabled: submitted,
    staleTime: 30_000,
  })

  const run = () => { setSubmitted(true); refetch() }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <SlidersHorizontal size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">스크리너</h1>
          <p className="text-xs text-muted-foreground">조건 설정 후 시장 전체를 필터링</p>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 bg-card rounded-lg border border-border p-4">
        <FilterGroup label="패턴 유형">
          <div className="flex flex-wrap gap-1.5">
            {PATTERN_OPTIONS.map(o => {
              const sel = req.pattern_types?.includes(o.value)
              return (
                <button
                  key={o.value}
                  onClick={() => setReq(r => ({
                    ...r,
                    pattern_types: sel
                      ? r.pattern_types?.filter(v => v !== o.value)
                      : [...(r.pattern_types ?? []), o.value],
                  }))}
                  className={`px-2 py-1 text-xs rounded transition-colors ${sel ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'}`}
                >
                  {o.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <FilterGroup label="패턴 상태">
          <div className="flex flex-wrap gap-1.5">
            {STATE_OPTIONS.map(o => {
              const sel = req.states?.includes(o.value)
              return (
                <button
                  key={o.value}
                  onClick={() => setReq(r => ({
                    ...r,
                    states: sel
                      ? r.states?.filter(v => v !== o.value)
                      : [...(r.states ?? []), o.value],
                  }))}
                  className={`px-2 py-1 text-xs rounded transition-colors ${sel ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:text-foreground'}`}
                >
                  {o.label}
                </button>
              )
            })}
          </div>
        </FilterGroup>

        <FilterGroup label="교과서 유사도 이상">
          <input
            type="range" min="0" max="1" step="0.05"
            value={req.min_textbook_similarity ?? 0}
            onChange={e => setReq(r => ({ ...r, min_textbook_similarity: +e.target.value }))}
            className="w-full accent-primary"
          />
          <span className="text-xs text-muted-foreground">{((req.min_textbook_similarity ?? 0) * 100).toFixed(0)}%</span>
        </FilterGroup>

        <FilterGroup label="상승 확률 이상">
          <input
            type="range" min="0" max="1" step="0.05"
            value={req.min_p_up ?? 0}
            onChange={e => setReq(r => ({ ...r, min_p_up: +e.target.value }))}
            className="w-full accent-primary"
          />
          <span className="text-xs text-muted-foreground">{((req.min_p_up ?? 0) * 100).toFixed(0)}%</span>
        </FilterGroup>

        <FilterGroup label="No Signal 제외">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={req.exclude_no_signal ?? true}
              onChange={e => setReq(r => ({ ...r, exclude_no_signal: e.target.checked }))}
              className="accent-primary"
            />
            <span className="text-xs text-muted-foreground">No Signal 종목 제외</span>
          </label>
        </FilterGroup>
      </div>

      <button
        onClick={run}
        className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors"
      >
        <Search size={14} />
        스크리닝 실행
      </button>

      {isLoading && <p className="text-xs text-muted-foreground">분석 중...</p>}

      {data && (
        <div>
          <p className="text-xs text-muted-foreground mb-3">{data.length}개 종목 검색됨</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
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
