import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from '@/lib/api'
import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { RefreshCw } from 'lucide-react'

export default function DashboardPage() {
  const opts = { staleTime: 30_000, refetchInterval: 60_000 }

  const longQ = useQuery({ queryKey: ['dashboard', 'long'], queryFn: () => dashboardApi.longHigh(), ...opts })
  const shortQ = useQuery({ queryKey: ['dashboard', 'short'], queryFn: () => dashboardApi.shortHigh(), ...opts })
  const simQ = useQuery({ queryKey: ['dashboard', 'sim'], queryFn: () => dashboardApi.highSimilarity(), ...opts })
  const armedQ = useQuery({ queryKey: ['dashboard', 'armed'], queryFn: () => dashboardApi.armed(), ...opts })
  const noSigQ = useQuery({ queryKey: ['dashboard', 'nosig'], queryFn: () => dashboardApi.noSignal(), ...opts })

  const isRefreshing = longQ.isFetching || shortQ.isFetching

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">대시보드</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            교과서 패턴 × 확률 기반 종목 스크리닝
          </p>
        </div>
        <button
          onClick={() => {
            longQ.refetch(); shortQ.refetch()
            simQ.refetch(); armedQ.refetch(); noSigQ.refetch()
          }}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      <DashboardSection
        title="상승 확률 상위"
        subtitle="진입 적합도 × 상승 확률이 높은 종목"
        data={longQ.data}
        isLoading={longQ.isLoading}
      />

      <DashboardSection
        title="패턴 완성 임박"
        subtitle="교과서 유사도 ≥ 50% & 상태 : 형성 중 / 확인 직전"
        data={armedQ.data}
        isLoading={armedQ.isLoading}
      />

      <DashboardSection
        title="교과서 유사도 상위"
        subtitle="현재 차트가 교과서 패턴과 가장 많이 닮은 종목"
        data={simQ.data}
        isLoading={simQ.isLoading}
      />

      <DashboardSection
        title="하락 확률 상위"
        subtitle="패턴 상 하락 반전 가능성이 높은 종목"
        data={shortQ.data}
        isLoading={shortQ.isLoading}
      />

      <DashboardSection
        title="No Signal / 관망"
        subtitle="신뢰도 부족 또는 패턴 미감지 — 진입 보류 권장"
        data={noSigQ.data}
        isLoading={noSigQ.isLoading}
      />
    </div>
  )
}
