import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Activity, Clock3, Database, KeyRound, RefreshCw, ServerCog, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { StatRow } from '@/components/ui/StatRow'
import { systemApi } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'

export default function SystemStatusPage() {
  const statusQ = useQuery({
    queryKey: ['system', 'status'],
    queryFn: systemApi.status,
    staleTime: 15_000,
    refetchInterval: 30_000,
  })

  const data = statusQ.data

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold">운영 상태</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            KIS 토큰, 캐시 백엔드, 데이터 수집 방식을 한 화면에서 확인합니다. 실전 사용 전에 여기서 데이터 신뢰도를 먼저 확인하면 좋습니다.
          </p>
        </div>
        <button
          onClick={() => statusQ.refetch()}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <RefreshCw size={13} className={statusQ.isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {statusQ.isLoading && (
        <Card className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          운영 상태를 불러오는 중입니다.
        </Card>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
            <StatusSummary
              icon={<KeyRound size={15} />}
              label="KIS 설정"
              value={data.kis.configured ? '설정됨' : '미설정'}
              tone={data.kis.configured ? 'bullish' : 'warning'}
            />
            <StatusSummary
              icon={<ShieldCheck size={15} />}
              label="토큰 캐시"
              value={data.kis.token_cached ? '재사용 가능' : '없음'}
              tone={data.kis.token_cached ? 'bullish' : 'warning'}
            />
            <StatusSummary
              icon={<Database size={15} />}
              label="캐시 백엔드"
              value={data.cache.backend}
              tone={data.cache.redis_available ? 'bullish' : 'muted'}
            />
            <StatusSummary
              icon={<Activity size={15} />}
              label="스케줄러"
              value={data.scheduler_enabled ? '활성' : '비활성'}
              tone={data.scheduler_enabled ? 'bullish' : 'warning'}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <KeyRound size={15} className="text-primary" />
                  KIS API 상태
                </CardTitle>
              </CardHeader>
              <div className="space-y-2">
                <StatRow label="환경" value={data.kis.environment} />
                <StatRow label="토큰 캐시" value={data.kis.token_cached ? '있음' : '없음'} />
                <StatRow label="토큰 만료 시각" value={data.kis.token_expires_at ? fmtDateTime(data.kis.token_expires_at) : '-'} />
                <StatRow label="토큰 남은 시간" value={formatDuration(data.kis.token_expires_in_seconds)} />
                <StatRow label="Base URL" value={data.kis.resolved_base_url ?? '-'} />
                <StatRow label="동시 요청 제한" value={`${data.kis.max_concurrent_requests}개`} />
                <StatRow label="요청 간격" value={`${data.kis.request_spacing_ms}ms`} />
                <StatRow label="토큰 캐시 파일" value={data.kis.token_cache_path} />
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ServerCog size={15} className="text-primary" />
                  캐시/데이터 운영
                </CardTitle>
              </CardHeader>
              <div className="space-y-2">
                <StatRow label="캐시 방식" value={data.cache.backend} />
                <StatRow label="Redis 연결" value={data.cache.redis_available ? '정상' : '메모리 fallback'} />
                <StatRow label="메모리 fallback 항목" value={`${data.cache.memory_fallback_entries}개`} />
                <StatRow label="분봉 저장 종목" value={`${data.intraday_store.symbol_count}개`} />
                <StatRow label="분봉 저장 봉 수" value={`${data.intraday_store.total_rows.toLocaleString('ko-KR')}개`} />
                <StatRow label="분봉 최신 수집" value={data.intraday_store.latest_fetched_at ? fmtDateTime(data.intraday_store.latest_fetched_at) : '-'} />
                <StatRow label="생성 시각" value={fmtDateTime(data.generated_at)} />
                {data.intraday_store.timeframes.length > 0 && (
                  <div className="rounded-lg border border-border bg-background/60 p-3">
                    <div className="mb-2 text-xs font-medium text-muted-foreground">타임프레임별 저장 현황</div>
                    <div className="space-y-1.5">
                      {data.intraday_store.timeframes.map(item => (
                        <div key={item.timeframe} className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                          <span>{item.timeframe}</span>
                          <span>{item.symbols}종목 / {item.rows.toLocaleString('ko-KR')}봉</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="rounded-lg border border-border bg-background/60 p-3">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    <Clock3 size={12} />
                    데이터 메모
                  </div>
                  <div className="space-y-1.5">
                    {data.data_notes.map((note, index) => (
                      <p key={`${note}-${index}`} className="text-xs leading-relaxed text-muted-foreground">
                        {index + 1}. {note}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          </div>

          <Card className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <ShieldCheck size={15} className="text-primary" />
              운영 가이드
            </div>
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
              {data.kis.guidance.map((item, index) => (
                <div key={`${item}-${index}`} className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
                  {item}
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

function StatusSummary({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode
  label: string
  value: string
  tone: 'bullish' | 'warning' | 'muted'
}) {
  return (
    <Card className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {icon}
          {label}
        </div>
        <Badge variant={tone}>{value}</Badge>
      </div>
    </Card>
  )
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds <= 0) return '만료됨'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours <= 0) return `${minutes}분`
  return `${hours}시간 ${minutes}분`
}
