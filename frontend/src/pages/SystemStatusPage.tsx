import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useState } from 'react'
import { Activity, Clock3, Database, DatabaseZap, KeyRound, RefreshCw, ServerCog, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { StatRow } from '@/components/ui/StatRow'
import { systemApi } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'
import type { IntradayWarmupResponse, Timeframe } from '@/types/api'

const INTRADAY_TIMEFRAMES = ['15m', '30m', '60m']

export default function SystemStatusPage() {
  const [manualSymbols, setManualSymbols] = useState('')
  const [candidateLimit, setCandidateLimit] = useState(20)
  const [sourceTimeframe, setSourceTimeframe] = useState<Timeframe>('1d')
  const queryClient = useQueryClient()

  const statusQ = useQuery({
    queryKey: ['system', 'status'],
    queryFn: systemApi.status,
    staleTime: 15_000,
    refetchInterval: 30_000,
  })

  const manualWarmup = useMutation({
    mutationFn: (allowLive: boolean) =>
      systemApi.warmupIntraday({
        symbols: parseSymbols(manualSymbols),
        timeframes: INTRADAY_TIMEFRAMES,
        allow_live: allowLive,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['system', 'status'] }),
  })

  const candidateWarmup = useMutation({
    mutationFn: (allowLive: boolean) =>
      systemApi.warmupCandidates({
        source_timeframe: sourceTimeframe,
        limit: candidateLimit,
        timeframes: INTRADAY_TIMEFRAMES,
        allow_live: allowLive,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['system', 'status'] }),
  })

  const data = statusQ.data
  const latestWarmup = candidateWarmup.data ?? manualWarmup.data
  const isWarming = manualWarmup.isPending || candidateWarmup.isPending

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold">운영 상태</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            KIS 토큰, 캐시 백엔드, 분봉 저장 현황, 후보 분봉 예열을 한 화면에서 관리합니다.
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
              label="분봉 저장"
              value={`${data.intraday_store.symbol_count}종목`}
              tone={data.intraday_store.symbol_count > 0 ? 'bullish' : 'muted'}
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
              </div>
            </Card>
          </div>

          <Card className="space-y-4 border-primary/20 bg-primary/5">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <DatabaseZap size={15} className="text-primary" />
              분봉 캐시 예열
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              대시보드 상위 후보나 직접 입력한 종목의 15분, 30분, 60분 데이터를 미리 저장합니다.
              기본은 저장/공개 데이터 우선이고, 장중 최신성이 꼭 필요할 때만 KIS 포함 버튼을 사용하세요.
            </p>

            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              <div className="rounded-lg border border-border bg-background/60 p-3">
                <div className="mb-2 text-xs font-semibold">대시보드 후보 예열</div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={sourceTimeframe}
                    onChange={event => setSourceTimeframe(event.target.value as Timeframe)}
                    className="rounded-md border border-border bg-card px-2 py-1.5 text-xs"
                  >
                    <option value="1d">일봉 후보</option>
                    <option value="1wk">주봉 후보</option>
                    <option value="60m">60분 후보</option>
                  </select>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={candidateLimit}
                    onChange={event => setCandidateLimit(Number(event.target.value))}
                    className="w-20 rounded-md border border-border bg-card px-2 py-1.5 text-xs"
                  />
                  <button
                    onClick={() => candidateWarmup.mutate(false)}
                    disabled={isWarming}
                    className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-60"
                  >
                    저장/공개 예열
                  </button>
                  <button
                    onClick={() => candidateWarmup.mutate(true)}
                    disabled={isWarming}
                    className="rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs text-primary hover:bg-primary/15 disabled:opacity-60"
                  >
                    KIS 포함 예열
                  </button>
                </div>
              </div>

              <div className="rounded-lg border border-border bg-background/60 p-3">
                <div className="mb-2 text-xs font-semibold">직접 종목 예열</div>
                <textarea
                  value={manualSymbols}
                  onChange={event => setManualSymbols(event.target.value)}
                  placeholder="예: 005930, 000660, 035420"
                  className="min-h-16 w-full rounded-md border border-border bg-card px-2 py-1.5 text-xs outline-none focus:border-primary/60"
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    onClick={() => manualWarmup.mutate(false)}
                    disabled={isWarming || parseSymbols(manualSymbols).length === 0}
                    className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-60"
                  >
                    저장/공개 예열
                  </button>
                  <button
                    onClick={() => manualWarmup.mutate(true)}
                    disabled={isWarming || parseSymbols(manualSymbols).length === 0}
                    className="rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs text-primary hover:bg-primary/15 disabled:opacity-60"
                  >
                    KIS 포함 예열
                  </button>
                </div>
              </div>
            </div>

            {isWarming && <p className="text-xs text-muted-foreground">분봉 데이터를 예열하는 중입니다. 종목 수가 많으면 조금 걸릴 수 있습니다.</p>}
            {latestWarmup && <WarmupResultSummary result={latestWarmup} />}
            {(manualWarmup.isError || candidateWarmup.isError) && (
              <p className="text-xs text-red-300">분봉 예열 중 오류가 발생했습니다. 종목 코드와 백엔드 로그를 확인해 주세요.</p>
            )}
          </Card>

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

          <Card>
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
          </Card>
        </>
      )}
    </div>
  )
}

function WarmupResultSummary({ result }: { result: IntradayWarmupResponse }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={result.failure_count > 0 ? 'warning' : 'bullish'}>
          성공 {result.success_count}/{result.total_requests}
        </Badge>
        <Badge variant={result.allow_live ? 'bullish' : 'muted'}>
          {result.allow_live ? 'KIS 포함' : '저장/공개 우선'}
        </Badge>
        <span className="text-muted-foreground">{result.symbols.length}종목 / {result.timeframes.join(', ')}</span>
      </div>
      <div className="mt-2 grid grid-cols-1 gap-1.5 md:grid-cols-2 xl:grid-cols-3">
        {result.results.slice(0, 9).map(item => (
          <div key={`${item.symbol}-${item.timeframe}`} className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-2 py-1.5 text-xs">
            <span>{item.symbol} {item.timeframe}</span>
            <span className={item.ok ? 'text-emerald-300' : 'text-red-300'}>{item.ok ? `${item.bars}봉` : '실패'}</span>
          </div>
        ))}
      </div>
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

function parseSymbols(value: string): string[] {
  return value
    .split(/[\s,]+/)
    .map(item => item.trim())
    .filter(Boolean)
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds <= 0) return '만료됨'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours <= 0) return `${minutes}분`
  return `${hours}시간 ${minutes}분`
}
