import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'
import { Activity, Clock3, Database, DatabaseZap, KeyRound, RefreshCw, ServerCog, ShieldAlert, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { StatRow } from '@/components/ui/StatRow'
import { systemApi } from '@/lib/api'
import { fmtDateTime } from '@/lib/utils'
import type { IntradayWarmupJobStatus, RuntimeStatusResponse, Timeframe } from '@/types/api'

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

  const warmupStatusQ = useQuery({
    queryKey: ['system', 'intraday-warmup-status'],
    queryFn: systemApi.warmupStatus,
    staleTime: 2_000,
    refetchInterval: query => (query.state.data?.is_running ? 2_000 : 15_000),
  })

  const refreshAll = () => {
    statusQ.refetch()
    warmupStatusQ.refetch()
  }

  const manualWarmup = useMutation({
    mutationFn: (allowLive: boolean) =>
      systemApi.warmupIntradayBackground({
        symbols: parseSymbols(manualSymbols),
        timeframes: INTRADAY_TIMEFRAMES,
        allow_live: allowLive,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['system', 'intraday-warmup-status'] })
    },
  })

  const candidateWarmup = useMutation({
    mutationFn: (allowLive: boolean) =>
      systemApi.warmupCandidatesBackground({
        source_timeframe: sourceTimeframe,
        limit: candidateLimit,
        timeframes: INTRADAY_TIMEFRAMES,
        allow_live: allowLive,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['system', 'intraday-warmup-status'] })
    },
  })

  const data = statusQ.data
  const warmupStatus = warmupStatusQ.data
  const isWarming = manualWarmup.isPending || candidateWarmup.isPending || Boolean(warmupStatus?.is_running)
  const readiness = useMemo(() => (data ? buildReadiness(data) : null), [data])
  const parsedSymbols = parseSymbols(manualSymbols)

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold">운영 상태</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            KIS 연결, 토큰 준비, 캐시 방식, 분봉 저장소, 자동 예열 상태를 한 번에 보고 지금 이 앱이 실전용으로 얼마나 준비됐는지
            빠르게 판단합니다.
          </p>
        </div>
        <button
          onClick={refreshAll}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <RefreshCw size={13} className={statusQ.isFetching || warmupStatusQ.isFetching ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {statusQ.isLoading && (
        <Card className="flex items-center gap-2 text-sm text-muted-foreground">
          <RefreshCw size={14} className="animate-spin" />
          운영 상태를 불러오는 중입니다.
        </Card>
      )}

      {statusQ.isError && !statusQ.isLoading && (
        <Card>
          <QueryError message="운영 상태를 불러오지 못했습니다." onRetry={refreshAll} />
        </Card>
      )}

      {data && readiness && (
        <>
          <Card className={`space-y-4 ${readiness.bannerClass}`}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  {readiness.level === 'ready' ? <ShieldCheck size={16} /> : <ShieldAlert size={16} />}
                  실전 준비도
                </div>
                <div className="mt-1 text-lg font-bold">{readiness.title}</div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{readiness.summary}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant={readiness.level === 'ready' ? 'bullish' : readiness.level === 'usable' ? 'neutral' : 'warning'}>
                  충족 {readiness.okCount}/{readiness.items.length}
                </Badge>
                <Badge variant="muted">기준 시각 {fmtDateTime(data.generated_at)}</Badge>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {readiness.items.map(item => (
                <div key={item.label} className="rounded-lg border border-border bg-background/60 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold">{item.label}</div>
                    <Badge variant={item.ok ? 'bullish' : 'warning'}>{item.ok ? '준비됨' : '보완 필요'}</Badge>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.detail}</p>
                </div>
              ))}
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
            <StatusSummary
              icon={<KeyRound size={15} />}
              label="KIS 설정"
              value={data.kis.configured ? '연결됨' : '미설정'}
              tone={data.kis.configured ? 'bullish' : 'warning'}
            />
            <StatusSummary
              icon={<ShieldCheck size={15} />}
              label="토큰 캐시"
              value={data.kis.token_cached ? '사용 가능' : '없음'}
              tone={data.kis.token_cached ? 'bullish' : 'warning'}
            />
            <StatusSummary
              icon={<Database size={15} />}
              label="분봉 저장 종목"
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
                <StatRow label="Resolved Base URL" value={data.kis.resolved_base_url ?? '-'} />
                <StatRow label="동시 요청 제한" value={`${data.kis.max_concurrent_requests}개`} />
                <StatRow label="요청 간격" value={`${data.kis.request_spacing_ms}ms`} />
                <StatRow label="토큰 캐시 파일" value={data.kis.token_cache_path} />
              </div>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ServerCog size={15} className="text-primary" />
                  캐시와 데이터 운영
                </CardTitle>
              </CardHeader>
              <div className="space-y-2">
                <StatRow label="캐시 방식" value={data.cache.backend} />
                <StatRow label="Redis 연결" value={data.cache.redis_available ? '정상' : '메모리 fallback'} />
                <StatRow label="메모리 fallback 항목" value={`${data.cache.memory_fallback_entries}개`} />
                <StatRow label="분봉 저장 종목" value={`${data.intraday_store.symbol_count}개`} />
                <StatRow label="분봉 저장 바 수" value={`${data.intraday_store.total_rows.toLocaleString('ko-KR')}개`} />
                <StatRow
                  label="분봉 최신 수집"
                  value={data.intraday_store.latest_fetched_at ? fmtDateTime(data.intraday_store.latest_fetched_at) : '-'}
                />
                <StatRow label="생성 시각" value={fmtDateTime(data.generated_at)} />
                {data.intraday_store.timeframes.length > 0 && (
                  <div className="rounded-lg border border-border bg-background/60 p-3">
                    <div className="mb-2 text-xs font-medium text-muted-foreground">타임프레임별 저장 현황</div>
                    <div className="space-y-1.5">
                      {data.intraday_store.timeframes.map(item => (
                        <div key={item.timeframe} className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                          <span>{item.timeframe}</span>
                          <span>
                            {item.symbols}종목 / {item.rows.toLocaleString('ko-KR')}개
                          </span>
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
              대시보드 상위 후보나 직접 입력한 종목의 15분, 30분, 60분 데이터를 미리 채웁니다. 기본은 저장소와 공개 데이터를 우선
              써서 호출을 아끼고, 최신성이 꼭 중요할 때만 KIS 포함 예열을 돌리는 흐름이 안전합니다.
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
                    저장 우선 예열
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
                    disabled={isWarming || parsedSymbols.length === 0}
                    className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-60"
                  >
                    저장 우선 예열
                  </button>
                  <button
                    onClick={() => manualWarmup.mutate(true)}
                    disabled={isWarming || parsedSymbols.length === 0}
                    className="rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs text-primary hover:bg-primary/15 disabled:opacity-60"
                  >
                    KIS 포함 예열
                  </button>
                </div>
              </div>
            </div>

            {warmupStatus && warmupStatus.status !== 'idle' && <WarmupJobStatusCard status={warmupStatus} />}
            {(manualWarmup.isError || candidateWarmup.isError) && (
              <p className="text-xs text-red-300">
                분봉 예열 중 오류가 발생했습니다. 종목 코드가 맞는지 확인하고, 필요하면 백엔드 로그도 함께 확인해 주세요.
              </p>
            )}
          </Card>

          {data.scheduled_warmups.length > 0 && (
            <Card className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Clock3 size={15} className="text-primary" />
                자동 예열 스케줄
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                평소에는 상위 후보군을 다시 뽑아 분봉 캐시를 자동으로 채웁니다. 기본은 저장 우선 방식이고, 필요할 때만 수동으로 KIS
                포함 예열을 추가로 돌리면 됩니다.
              </p>
              <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
                {data.scheduled_warmups.map(plan => (
                  <div key={plan.id} className="rounded-lg border border-border bg-background/60 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold text-foreground">{plan.label}</div>
                        <div className="mt-1 text-[11px] text-muted-foreground">{plan.schedule}</div>
                      </div>
                      <Badge variant={plan.allow_live ? 'bullish' : 'muted'}>{plan.allow_live ? 'KIS 포함' : '저장 우선'}</Badge>
                    </div>
                    <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                      <div>
                        후보 기준: {plan.source_timeframe} 상위 {plan.limit}개
                      </div>
                      <div>예열 분봉: {plan.timeframes.join(', ')}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

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

function WarmupJobStatusCard({ status }: { status: IntradayWarmupJobStatus }) {
  const progress = status.total_requests > 0 ? status.completed_count / status.total_requests : 0

  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={status.is_running ? 'neutral' : status.failure_count > 0 ? 'warning' : 'bullish'}>
          {warmupJobLabel(status.status)}
        </Badge>
        <Badge variant={status.failure_count > 0 ? 'warning' : 'bullish'}>
          성공 {status.success_count}/{status.total_requests}
        </Badge>
        <Badge variant={status.allow_live ? 'bullish' : 'muted'}>{status.allow_live ? 'KIS 포함' : '저장 우선'}</Badge>
        <span className="text-muted-foreground">
          {status.symbols.length}종목 / {status.timeframes.join(', ')}
        </span>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-background">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>

      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>
          {status.completed_count}/{status.total_requests} 완료
        </span>
        <span>{Math.round(progress * 100)}%</span>
      </div>

      {status.last_error && <p className="mt-2 text-xs text-red-300">{status.last_error}</p>}

      <div className="mt-2 grid grid-cols-1 gap-1.5 md:grid-cols-2 xl:grid-cols-3">
        {status.results.slice(-9).map(item => (
          <div
            key={`${item.symbol}-${item.timeframe}`}
            className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-2 py-1.5 text-xs"
          >
            <span>
              {item.symbol} {item.timeframe}
            </span>
            <span className={item.ok ? 'text-emerald-300' : 'text-red-300'}>{item.ok ? `${item.bars}개` : '실패'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function warmupJobLabel(status: string): string {
  if (status === 'running') return '진행 중'
  if (status === 'queued') return '대기 중'
  if (status === 'ready') return '완료'
  if (status === 'error') return '오류'
  return '대기'
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
  if (seconds <= 0) return '만료'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours <= 0) return `${minutes}분`
  return `${hours}시간 ${minutes}분`
}

function buildReadiness(data: RuntimeStatusResponse) {
  const items = [
    {
      label: 'KIS 연결',
      ok: data.kis.configured,
      detail: data.kis.configured
        ? '실시간 분봉을 위해 필요한 KIS 자격 증명이 연결되어 있습니다.'
        : 'KIS가 비어 있어 분봉은 공개 데이터나 저장소 fallback 의존도가 높습니다.',
    },
    {
      label: '토큰 준비',
      ok: data.kis.token_cached,
      detail: data.kis.token_cached
        ? `현재 토큰이 캐시되어 있고 만료 예정 시각은 ${data.kis.token_expires_at ? fmtDateTime(data.kis.token_expires_at) : '확인 불가'}입니다.`
        : '실시간 요청 전에 토큰 발급이 먼저 필요합니다.',
    },
    {
      label: '분봉 저장소',
      ok: data.intraday_store.symbol_count > 0 && data.intraday_store.total_rows > 0,
      detail:
        data.intraday_store.symbol_count > 0
          ? `${data.intraday_store.symbol_count}종목, ${data.intraday_store.total_rows.toLocaleString('ko-KR')}개 바가 저장되어 있어 첫 응답이 한결 안정적입니다.`
          : '아직 저장된 분봉 데이터가 거의 없어 초기 진입 시 지연이 생길 수 있습니다.',
    },
    {
      label: '캐시 안정성',
      ok: data.cache.redis_available,
      detail: data.cache.redis_available
        ? 'Redis가 연결되어 있어 재시작 이후에도 캐시 안정성이 높습니다.'
        : '지금은 메모리 fallback 중심이라 재시작이나 재배포 후 캐시가 다시 비워질 수 있습니다.',
    },
    {
      label: '자동 예열',
      ok: data.scheduler_enabled && data.scheduled_warmups.length > 0,
      detail: data.scheduler_enabled
        ? `${data.scheduled_warmups.length}개의 자동 예열 스케줄이 켜져 있어 분봉 후보군을 꾸준히 채웁니다.`
        : '자동 예열이 꺼져 있어 장중 후보군이 천천히 채워질 수 있습니다.',
    },
  ]

  const okCount = items.filter(item => item.ok).length
  const level = okCount >= 4 ? 'ready' : okCount >= 2 ? 'usable' : 'limited'

  return {
    items,
    okCount,
    level,
    title:
      level === 'ready'
        ? '실전 이용 준비가 대부분 완료되어 있습니다'
        : level === 'usable'
          ? '이용 가능하지만 아직 보완할 부분이 있습니다'
          : '테스트용에 가깝고 실전 이용 전 보완이 필요합니다',
    summary:
      level === 'ready'
        ? 'KIS, 토큰, 저장 분봉, 자동 예열이 대부분 준비되어 있어 분봉 응답과 안정성이 이전보다 훨씬 낫습니다.'
        : level === 'usable'
          ? '기본 사용은 가능하지만 저장 분봉이나 Redis 같은 운영 기반이 부족하면 장중 체감 품질이 흔들릴 수 있습니다.'
          : '실행은 가능하지만 분봉 정확도와 안정성을 기대하기에는 아직 부족합니다. 운영 기반부터 먼저 채우는 편이 좋습니다.',
    bannerClass:
      level === 'ready'
        ? 'border-emerald-500/20 bg-emerald-500/5'
        : level === 'usable'
          ? 'border-amber-500/20 bg-amber-500/5'
          : 'border-red-500/20 bg-red-500/5',
  }
}
