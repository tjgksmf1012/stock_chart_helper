import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink, Layers3 } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { symbolsApi } from '@/lib/api'
import { timeframeLabel } from '@/lib/timeframes'
import { fmtPct, PATTERN_NAMES, STATE_LABELS } from '@/lib/utils'
import type { ReferenceCaseItem, Timeframe } from '@/types/api'

const CLOUD_POSITION_LABELS: Record<string, string> = {
  above_cloud: '구름 위',
  cloud_top_test: '구름 상단 테스트',
  inside_cloud: '구름 안',
  cloud_bottom_test: '구름 하단 테스트',
  below_cloud: '구름 아래',
  unknown: '구름 해석 보류',
}

const PRIOR_HIGH_LABELS: Record<string, string> = {
  all_highs_cleared: '직전·이전 고점 정리',
  recent_high_cleared_old_high_pending: '직전 고점만 정리',
  recent_high_test: '직전 고점 테스트',
  prior_high_below: '이전 고점 미정리',
  unknown: '전고점 해석 보류',
}

const CLOUD_THICKNESS_LABELS: Record<string, string> = {
  thick: '두꺼운 구름',
  normal: '보통 구름',
  thin: '얇은 구름',
  unknown: '두께 해석 보류',
}

export default function ReferenceChartsPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const symbol = searchParams.get('symbol')
  const pattern = searchParams.get('pattern')
  const timeframe = ((searchParams.get('timeframe') as Timeframe | null) ?? '1d')

  const referenceQ = useQuery({
    queryKey: ['reference-cases', symbol, timeframe],
    queryFn: () => symbolsApi.getReferenceCases(symbol!, timeframe, 8),
    enabled: Boolean(symbol),
    staleTime: 300_000,
  })

  const items = referenceQ.data?.items ?? []
  const focusSummary = useMemo(() => {
    const cloud = referenceQ.data?.ichimoku.cloud_position ?? 'unknown'
    const priorHigh = referenceQ.data?.ichimoku.prior_high_structure ?? 'unknown'
    return {
      cloud: CLOUD_POSITION_LABELS[cloud] ?? cloud,
      priorHigh: PRIOR_HIGH_LABELS[priorHigh] ?? priorHigh,
    }
  }, [referenceQ.data])

  return (
    <div className="space-y-6">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_340px]">
        <Card className="space-y-4 border-primary/20 bg-[linear-gradient(180deg,rgba(37,99,235,0.1),rgba(15,23,42,0.18))]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[11px] font-medium text-primary">
                <Layers3 size={12} />
                과거 유사 차트 비교
              </div>
              <div>
                <h1 className="text-2xl font-bold">실제 과거 사례 보드</h1>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
                  같은 패턴, 같은 상태, 같은 타임프레임 안에서 구름대 위치와 전고점 구조까지 비슷한 과거 사례를
                  자동으로 추려 보여줍니다. 지금 차트를 볼 때 “전에 이런 자리가 어떻게 흘렀는지”를 함께 확인하는
                  보드예요.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => nav(symbol ? `/chart/${symbol}` : '/chart')}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                <ArrowLeft size={13} />
                현재 차트로
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {symbol && <Badge variant="default">{symbol}</Badge>}
            <Badge variant="muted">{timeframeLabel(timeframe)}</Badge>
            {pattern && <Badge variant="neutral">{PATTERN_NAMES[pattern] ?? pattern}</Badge>}
            {referenceQ.data?.state && <Badge variant="bullish">{STATE_LABELS[referenceQ.data.state] ?? referenceQ.data.state}</Badge>}
          </div>
        </Card>

        <Card className="space-y-3">
          <div className="text-sm font-semibold">지금 포인트</div>
          <ChecklistItem title="구름 위치" body={focusSummary.cloud} />
          <ChecklistItem
            title="구름 두께"
            body={`${CLOUD_THICKNESS_LABELS[referenceQ.data?.ichimoku.cloud_thickness_level ?? 'unknown'] ?? '두께 해석 보류'} · 거리 ${fmtPct(referenceQ.data?.ichimoku.cloud_distance_pct ?? 0, 1)}`}
          />
          <ChecklistItem title="전고점 구조" body={focusSummary.priorHigh} />
          <ChecklistItem
            title="일목 해석"
            body={referenceQ.data?.ichimoku.summary || '일목 해석이 준비되면 여기서 바로 비교할 수 있습니다.'}
          />
        </Card>
      </section>

      {referenceQ.data && (
        <section className="grid gap-3 md:grid-cols-4">
          <MetricCard label="비교 표본" value={`${referenceQ.data.sample_count}건`} />
          <MetricCard label="성공률" value={fmtPct(referenceQ.data.success_rate, 0)} />
          <MetricCard label="부분 포함 성공률" value={fmtPct(referenceQ.data.partial_success_rate, 0)} />
          <MetricCard label="평균 결과" value={fmtPct(referenceQ.data.avg_outcome_return_pct, 1)} />
        </section>
      )}

      {referenceQ.isError && (
        <Card>
          <QueryError message="과거 유사 사례를 불러오지 못했습니다." onRetry={() => referenceQ.refetch()} />
        </Card>
      )}

      {!referenceQ.isLoading && !referenceQ.isError && items.length === 0 && (
        <Card className="space-y-2">
          <div className="text-sm font-semibold">아직 충분한 매칭 사례가 없습니다.</div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            현재 종목의 패턴과 상태에 정확히 맞는 과거 사례가 아직 적습니다. 타임프레임을 바꾸거나 패턴이 한 단계 더
            진행된 뒤 다시 보면 사례가 더 잘 모일 수 있어요.
          </p>
        </Card>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {items.map(item => (
          <ReferenceCaseCard key={item.key} item={item} />
        ))}
      </div>
    </div>
  )
}

function ReferenceCaseCard({ item }: { item: ReferenceCaseItem }) {
  return (
    <Card className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold">{item.symbol_name}</div>
            <div className="font-mono text-xs text-muted-foreground">{item.symbol_code}</div>
            <Badge variant="muted">{item.timeframe_label}</Badge>
            <Badge variant={item.match_grade === 'A' ? 'bullish' : item.match_grade === 'B' ? 'neutral' : 'muted'}>
              매칭 {item.match_grade}
            </Badge>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}</span>
            <span>{STATE_LABELS[item.state] ?? item.state}</span>
            <span>유사도 {fmtPct(item.similarity_score, 0)}</span>
          </div>
        </div>
        <a
          href={item.chart_path}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          차트 열기
          <ExternalLink size={12} />
        </a>
      </div>

      <SparklineCard sparkline={item.sparkline} />

      <div className="grid gap-2 sm:grid-cols-2">
        <MiniTag title="구름대" body={CLOUD_POSITION_LABELS[item.cloud_position] ?? item.cloud_position} />
        <MiniTag title="구름 두께" body={CLOUD_THICKNESS_LABELS[item.cloud_thickness_level] ?? item.cloud_thickness_level} />
        <MiniTag title="전고점" body={PRIOR_HIGH_LABELS[item.prior_high_structure] ?? item.prior_high_structure} />
        <MiniTag title="결과 수익" body={fmtPct(item.outcome_return_pct, 1)} />
      </div>

      <div className="rounded-lg border border-border bg-background/55 p-3 text-sm leading-relaxed text-muted-foreground">
        {item.setup_summary}
      </div>

      <div className="rounded-lg border border-primary/15 bg-primary/5 p-3 text-sm leading-relaxed text-muted-foreground">
        <div className="text-xs font-medium text-primary">{item.outcome_label}</div>
        <div className="mt-1">{item.outcome_summary}</div>
      </div>

      <div className="flex flex-wrap gap-2">
        {item.matched_features.map(feature => (
          <Badge key={feature} variant="neutral">
            {feature}
          </Badge>
        ))}
      </div>

      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span>신호일 {item.signal_date}</span>
        {item.resolution_date && <span>결과일 {item.resolution_date}</span>}
        {item.bars_to_resolution && <span>{item.bars_to_resolution}봉 만에 결론</span>}
        <span>최대 유리 {fmtPct(item.max_favorable_pct, 1)}</span>
        <span>최대 불리 {fmtPct(item.max_adverse_pct, 1)}</span>
        <span>{item.ichimoku_summary}</span>
      </div>
    </Card>
  )
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card className="space-y-1">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold text-foreground">{value}</div>
    </Card>
  )
}

function SparklineCard({ sparkline }: { sparkline: number[] }) {
  const points = useMemo(() => {
    if (!sparkline.length) return ''
    const min = Math.min(...sparkline)
    const max = Math.max(...sparkline)
    const span = Math.max(max - min, 0.0001)
    return sparkline
      .map((value, index) => {
        const x = (index / Math.max(sparkline.length - 1, 1)) * 100
        const y = 88 - ((value - min) / span) * 68
        return `${x},${y}`
      })
      .join(' ')
  }, [sparkline])

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background/70 p-3">
      <svg viewBox="0 0 100 100" className="h-44 w-full">
        <path d="M 0 62 C 20 56, 38 52, 100 44 L 100 72 C 64 76, 28 78, 0 80 Z" fill="rgba(52,211,153,0.08)" />
        <line x1="0" y1="54" x2="100" y2="54" stroke="#334155" strokeDasharray="3 2" />
        {points && (
          <polyline
            fill="none"
            stroke="#60a5fa"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={points}
          />
        )}
      </svg>
    </div>
  )
}

function MiniTag({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className="mt-1 text-sm font-medium text-foreground">{body}</div>
    </div>
  )
}

function ChecklistItem({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-sm font-medium text-foreground">{title}</div>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}
