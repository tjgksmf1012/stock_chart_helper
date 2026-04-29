import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  Clock3,
  Database,
  DatabaseZap,
  History,
  KeyRound,
  RefreshCw,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { StatRow } from '@/components/ui/StatRow'
import { systemApi } from '@/lib/api'
import { fmtDateTime, fmtPct } from '@/lib/utils'
import type {
  IntradayWarmupJobStatus,
  KisPrimeStatus,
  RuntimeStatusResponse,
  ScanHistoryRunSummary,
  ScanQualityActionPlan,
  ScanQualityBucket,
  ScanQualityFalsePositive,
  ScanQualityGroup,
  ScanQualityReportResponse,
  Timeframe,
} from '@/types/api'

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

  const scanHistoryQ = useQuery({
    queryKey: ['system', 'scan-history', sourceTimeframe],
    queryFn: () => systemApi.scanHistory({ timeframe: sourceTimeframe, limit: 8 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const scanQualityQ = useQuery({
    queryKey: ['system', 'scan-quality-report', sourceTimeframe],
    queryFn: () => systemApi.scanQualityReport({ timeframe: sourceTimeframe, lookback_days: 180, forward_bars: 20 }),
    staleTime: 60_000,
    refetchInterval: 120_000,
  })

  const refreshAll = () => {
    statusQ.refetch()
    warmupStatusQ.refetch()
    scanHistoryQ.refetch()
    scanQualityQ.refetch()
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
      queryClient.invalidateQueries({ queryKey: ['system', 'scan-history'] })
      queryClient.invalidateQueries({ queryKey: ['system', 'scan-quality-report'] })
    },
  })

  const kisPrime = useMutation({
    mutationFn: () => systemApi.primeKis({ timeframe: '1m' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system', 'status'] })
    },
  })

  const data = statusQ.data
  const warmupStatus = warmupStatusQ.data
  const history = scanHistoryQ.data ?? []
  const quality = scanQualityQ.data
  const isWarming = manualWarmup.isPending || candidateWarmup.isPending || Boolean(warmupStatus?.is_running)
  const readiness = useMemo(() => (data ? buildReadiness(data) : null), [data])
  const parsedSymbols = parseSymbols(manualSymbols)
  const lastPrime = data?.kis.last_prime

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold">운영 상태</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            KIS 연결, 토큰 준비 여부, 캐시 상태, 분봉 저장소, 자동 예열 상태와 최근 스캔 품질을 한 화면에서 확인합니다.
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
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <button
                  onClick={() => kisPrime.mutate()}
                  disabled={kisPrime.isPending}
                  className="rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs text-primary hover:bg-primary/15 disabled:opacity-60"
                >
                  {kisPrime.isPending ? 'KIS 프라임 중' : '토큰 발급 + 첫 분봉 확인'}
                </button>
                {lastPrime?.finished_at && (
                  <Badge variant={lastPrime.ok ? 'bullish' : 'warning'}>
                    최근 프라임 {fmtDateTime(lastPrime.finished_at)}
                  </Badge>
                )}
              </div>
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
              {lastPrime && <KisPrimeCard status={lastPrime} />}
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ServerCog size={15} className="text-primary" />
                  캐시와 데이터 저장
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
              대시보드 상위 후보나 직접 입력한 종목의 15분, 30분, 60분 데이터를 미리 채워 둡니다. 기본은 예산 우선 모드이고,
              정말 필요한 경우에만 KIS를 포함해 예열하도록 나눠 두었습니다.
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
                    저장소 우선 예열
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
                    저장소 우선 예열
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
                분봉 예열 중 오류가 발생했습니다. 종목 코드가 맞는지 확인하고, 필요하면 백엔드 로그도 같이 확인해 주세요.
              </p>
            )}
          </Card>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <History size={15} className="text-primary" />
                  최근 스캔 이력
                </div>
                <Badge variant="muted">{sourceTimeframe}</Badge>
              </div>
              {scanHistoryQ.isError ? (
                <QueryError compact message="스캔 이력을 불러오지 못했습니다." onRetry={() => scanHistoryQ.refetch()} />
              ) : history.length === 0 ? (
                <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
                  아직 저장된 스캔 이력이 없습니다. 다음 스캔부터 자동으로 쌓입니다.
                </div>
              ) : (
                <div className="space-y-2">
                  {history.map(run => (
                    <ScanHistoryCard key={run.id} run={run} />
                  ))}
                </div>
              )}
            </Card>

            <Card className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <BarChart3 size={15} className="text-primary" />
                  신호 품질 검증
                </div>
                <Badge variant="muted">최근 180일 / 20봉 기준</Badge>
              </div>
              {scanQualityQ.isError ? (
                <QueryError compact message="신호 품질 리포트를 불러오지 못했습니다." onRetry={() => scanQualityQ.refetch()} />
              ) : quality ? (
                <ScanQualitySection report={quality} />
              ) : (
                <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
                  리포트를 계산하는 중입니다.
                </div>
              )}
            </Card>
          </div>

          {data.scheduled_warmups.length > 0 && (
            <Card className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Clock3 size={15} className="text-primary" />
                자동 예열 스케줄
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                장중에 상위 후보군을 다시 골라 분봉 캐시를 자동으로 채웁니다. 기본은 저장소 우선 방식이고, 필요한 경우만 KIS 포함 예열을 사용합니다.
              </p>
              <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
                {data.scheduled_warmups.map(plan => (
                  <div key={plan.id} className="rounded-lg border border-border bg-background/60 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold text-foreground">{plan.label}</div>
                        <div className="mt-1 text-[11px] text-muted-foreground">{plan.schedule}</div>
                      </div>
                      <Badge variant={plan.allow_live ? 'bullish' : 'muted'}>{plan.allow_live ? 'KIS 포함' : '저장소 우선'}</Badge>
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

          {(data.scheduled_daily_scans ?? []).length > 0 && (
            <Card className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Clock3 size={15} className="text-primary" />
                자동 일봉 스캔 스케줄
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                장마감 후 확정 일봉 스캔이 scan-history에 저장되어 다음날 후보, 품질 리포트, 신호 검증의 기준 데이터가 됩니다.
              </p>
              <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                {(data.scheduled_daily_scans ?? []).map(plan => (
                  <div key={plan.id} className="rounded-lg border border-border bg-background/60 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold text-foreground">{plan.label}</div>
                        <div className="mt-1 text-[11px] text-muted-foreground">{plan.purpose}</div>
                      </div>
                      <Badge variant={plan.id === 'close_scan' ? 'bullish' : 'muted'}>{plan.schedule}</Badge>
                    </div>
                    <div className="mt-3 text-xs text-muted-foreground">기준 타임프레임: {plan.timeframe}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {(data.storage_roles ?? []).length > 0 && (
            <Card className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Database size={15} className="text-primary" />
                저장소 역할 분리
              </div>
              <p className="text-xs leading-relaxed text-muted-foreground">
                Redis는 빠르게 다시 만들 수 있는 캐시, Neon은 오래 남겨야 하는 운용 기록, 로컬 SQLite는 분봉 체감 속도용 저장소로 분리해서 봅니다.
              </p>
              <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
                {(data.storage_roles ?? []).map(role => (
                  <div key={role.name} className="rounded-lg border border-border bg-background/60 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold text-foreground">{role.name}</div>
                        <div className="mt-1 text-[11px] text-muted-foreground">{role.role}</div>
                      </div>
                      <Badge variant={role.backend === 'postgresql' ? 'bullish' : 'muted'}>{role.backend}</Badge>
                    </div>
                    <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{role.persistence}</p>
                    <div className="mt-3 flex flex-wrap gap-1">
                      {role.examples.map(example => (
                        <span key={example} className="rounded-md border border-border bg-card/70 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                          {example}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

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

function ScanHistoryCard({ run }: { run: ScanHistoryRunSummary }) {
  const statusTone = run.status === 'ready' ? 'bullish' : run.status === 'error' ? 'warning' : 'neutral'

  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={statusTone}>{scanRunStatusLabel(run.status)}</Badge>
        <Badge variant="muted">{run.timeframe_label}</Badge>
        {run.candidate_source && <Badge variant="muted">{run.candidate_source}</Badge>}
        {run.reference_date && <Badge variant="muted">기준일 {run.reference_date}</Badge>}
      </div>
      <div className="mt-3 grid grid-cols-1 gap-1.5 text-xs text-muted-foreground md:grid-cols-2">
        <div>완료 시각: {fmtDateTime(run.finished_at)}</div>
        <div>소요 시간: {formatDurationMs(run.duration_ms)}</div>
        <div>유니버스: {run.universe_size ?? '-'}개</div>
        <div>후보 수: {run.candidate_count ?? '-'}개</div>
        <div>저장 결과: {run.result_count}개</div>
        <div>기준 사유: {scanReferenceReasonLabel(run.reference_reason)}</div>
      </div>
      {run.last_error && <p className="mt-2 text-xs text-red-300">{run.last_error}</p>}
    </div>
  )
}

function ScanQualitySection({ report }: { report: ScanQualityReportResponse }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <QualityMetric label="평가 신호 수" value={`${report.evaluated_count}건`} />
        <QualityMetric label="스캔 런 수" value={`${report.run_count}회`} />
        <QualityMetric label="평균 종가 수익" value={fmtPct(report.summary.avg_close_return_pct, 1)} />
        <QualityMetric label="양봉 마감 비율" value={fmtPct(report.summary.positive_close_rate, 0)} />
        <QualityMetric label="익절 기준가 터치율" value={fmtPct(report.summary.target_touch_rate, 0)} />
        <QualityMetric label="손절가 터치율" value={fmtPct(report.summary.stop_touch_rate, 0)} />
        <QualityMetric label="최대 상승 평균" value={fmtPct(report.summary.avg_max_runup_pct, 1)} />
        <QualityMetric label="최대 낙폭 평균" value={fmtPct(report.summary.avg_max_drawdown_pct, 1)} />
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="mb-2 text-xs font-semibold">점수 구간별 결과</div>
        <div className="space-y-2">
          {report.score_buckets.map(bucket => (
            <BucketRow key={bucket.bucket} bucket={bucket} />
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="mb-2 text-xs font-semibold">행동 계획별 결과</div>
        <div className="space-y-2">
          {report.action_plans.map(plan => (
            <ActionPlanRow key={plan.action_plan} plan={plan} />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <QualityGroupPanel title="패턴별 성과" rows={report.pattern_groups ?? []} />
        <QualityGroupPanel title="상태별 성과" rows={report.state_groups ?? []} />
        <QualityGroupPanel title="타임프레임별 성과" rows={report.timeframe_groups ?? []} />
      </div>

      {(report.false_positive_signals ?? []).length > 0 && (
        <div className="rounded-lg border border-orange-400/30 bg-orange-400/5 p-3">
          <div className="mb-2 text-xs font-semibold text-foreground">좋아 보였지만 실제로 안 오른 신호</div>
          <div className="space-y-2">
            {report.false_positive_signals.map(item => (
              <FalsePositiveRow key={`${item.symbol_code}-${item.signal_date}-${item.pattern_type ?? 'unknown'}`} item={item} />
            ))}
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
        <div className="mb-2 text-xs font-semibold text-foreground">해석 메모</div>
        <div className="space-y-1.5">
          {report.notes.map((note, index) => (
            <p key={`${note}-${index}`}>{index + 1}. {note}</p>
          ))}
        </div>
      </div>
    </div>
  )
}

function BucketRow({ bucket }: { bucket: ScanQualityBucket }) {
  return (
    <div className="grid grid-cols-[100px_1fr] items-center gap-3 text-xs">
      <div className="font-medium text-foreground">{bucket.bucket}</div>
      <div className="grid grid-cols-2 gap-2 text-muted-foreground md:grid-cols-4">
        <span>표본 {bucket.sample_count}건</span>
        <span>양봉 마감 {fmtPct(bucket.positive_close_rate, 0)}</span>
        <span>목표 터치 {fmtPct(bucket.target_touch_rate, 0)}</span>
        <span>손절 터치 {fmtPct(bucket.stop_touch_rate, 0)}</span>
        <span>평균 종가 {fmtPct(bucket.avg_close_return_pct, 1)}</span>
      </div>
    </div>
  )
}

function ActionPlanRow({ plan }: { plan: ScanQualityActionPlan }) {
  return (
    <div className="grid grid-cols-[120px_1fr] items-center gap-3 text-xs">
      <div className="font-medium text-foreground">{plan.action_plan}</div>
      <div className="grid grid-cols-2 gap-2 text-muted-foreground md:grid-cols-4">
        <span>표본 {plan.sample_count}건</span>
        <span>양봉 마감 {fmtPct(plan.positive_close_rate, 0)}</span>
        <span>+5% 도달 {fmtPct(plan.hit_5pct_rate, 0)}</span>
        <span>목표 터치 {fmtPct(plan.target_touch_rate, 0)}</span>
        <span>평균 최대상승 {fmtPct(plan.avg_max_runup_pct, 1)}</span>
      </div>
    </div>
  )
}

function QualityGroupPanel({ title, rows }: { title: string; rows: ScanQualityGroup[] }) {
  const visibleRows = rows.slice(0, 6)

  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="mb-2 text-xs font-semibold">{title}</div>
      {visibleRows.length === 0 ? (
        <p className="text-xs text-muted-foreground">아직 비교할 표본이 부족합니다.</p>
      ) : (
        <div className="space-y-2">
          {visibleRows.map(row => (
            <div key={row.group} className="rounded-md border border-border bg-card/60 p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-foreground">{row.group}</span>
                <span className="text-muted-foreground">{row.sample_count}건</span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-1.5 text-muted-foreground">
                <span>종가+ {fmtPct(row.positive_close_rate, 0)}</span>
                <span>목표 {fmtPct(row.target_touch_rate, 0)}</span>
                <span>손절 {fmtPct(row.stop_touch_rate, 0)}</span>
                <span>평균 {fmtPct(row.avg_close_return_pct, 1)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FalsePositiveRow({ item }: { item: ScanQualityFalsePositive }) {
  return (
    <div className="rounded-md border border-orange-400/30 bg-card/60 p-2 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-medium text-foreground">
          {item.symbol_name} <span className="text-muted-foreground">{item.symbol_code}</span>
        </div>
        <Badge variant="warning">{item.signal_date}</Badge>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1.5 text-muted-foreground md:grid-cols-5">
        <span>{item.pattern_type ?? 'unknown'}</span>
        <span>{item.state ?? 'unknown'}</span>
        <span>점수 {Math.round(item.composite_score * 100)}</span>
        <span>상승확률 {fmtPct(item.p_up, 0)}</span>
        <span>종가 {fmtPct(item.close_return_pct, 1)}</span>
      </div>
      <p className="mt-2 text-muted-foreground">{item.reason}</p>
    </div>
  )
}

function QualityMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-semibold text-foreground">{value}</div>
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
        <Badge variant={status.allow_live ? 'bullish' : 'muted'}>{status.allow_live ? 'KIS 포함' : '저장소 우선'}</Badge>
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

function KisPrimeCard({ status }: { status: KisPrimeStatus }) {
  if (status.status === 'idle' && !status.finished_at && !status.is_running) {
    return null
  }

  return (
    <div className="mt-4 rounded-lg border border-border bg-background/60 p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant={status.ok ? 'bullish' : status.is_running ? 'neutral' : 'warning'}>
          {status.is_running ? '프라임 진행 중' : status.ok ? '프라임 완료' : '프라임 재시도 필요'}
        </Badge>
        {status.symbol && <Badge variant="muted">{status.symbol} {status.timeframe ?? '1m'}</Badge>}
        {status.store_rows_added > 0 && <Badge variant="bullish">분봉 {status.store_rows_added}개 추가</Badge>}
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <StatRow label="토큰 캐시" value={status.token_cached_after ? '발급/재사용 완료' : '아직 없음'} />
        <StatRow label="분봉 반환" value={`${status.bars_returned}개`} />
        <StatRow label="데이터 소스" value={status.data_source ?? '-'} />
        <StatRow label="상태" value={status.fetch_status ?? '-'} />
      </div>

      {status.message && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{status.message}</p>}
      {status.last_error && <p className="mt-2 text-xs text-red-300">{status.last_error}</p>}
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

function scanRunStatusLabel(status: string): string {
  if (status === 'ready') return '완료'
  if (status === 'running') return '진행 중'
  if (status === 'error') return '오류'
  return status
}

function scanReferenceReasonLabel(reason: string | null | undefined): string {
  switch (reason) {
    case 'same_day_after_close':
      return '장 마감 후 당일 일봉'
    case 'previous_session_before_close':
      return '장중에는 직전 거래일 기준'
    case 'weekend_previous_session':
      return '주말/휴장일 직전 거래일 기준'
    case 'intraday_live_session':
      return '당일 분봉 세션 기준'
    default:
      return '-'
  }
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

function formatDurationMs(milliseconds: number | null): string {
  if (!milliseconds || milliseconds <= 0) return '-'
  if (milliseconds < 1000) return `${milliseconds}ms`
  const seconds = milliseconds / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}초`
  const minutes = Math.floor(seconds / 60)
  const remain = Math.round(seconds % 60)
  return `${minutes}분 ${remain}초`
}

function buildReadiness(data: RuntimeStatusResponse) {
  const items = [
    {
      label: 'KIS 연결',
      ok: data.kis.configured,
      detail: data.kis.configured
        ? '실시간 분봉을 위해 필요한 KIS 자격 증명이 연결되어 있습니다.'
        : 'KIS가 비어 있어 분봉과 토큰 관련 기능은 제한적으로만 동작합니다.',
    },
    {
      label: '토큰 준비',
      ok: data.kis.token_cached,
      detail: data.kis.token_cached
        ? `현재 토큰이 캐시되어 있고 만료 예정 시각은 ${data.kis.token_expires_at ? fmtDateTime(data.kis.token_expires_at) : '확인 불가'}입니다.`
        : '첫 실시간 요청 전에 토큰 발급이 한 번 더 필요합니다.',
    },
    {
      label: '분봉 저장소',
      ok: data.intraday_store.symbol_count > 0 && data.intraday_store.total_rows > 0,
      detail:
        data.intraday_store.symbol_count > 0
          ? `${data.intraday_store.symbol_count}종목, ${data.intraday_store.total_rows.toLocaleString('ko-KR')}개 바가 저장되어 있어 첫 응답 체감이 더 안정적입니다.`
          : '아직 저장된 분봉 데이터가 거의 없어 첫 진입 시 체감이 느릴 수 있습니다.',
    },
    {
      label: '캐시 안정성',
      ok: data.cache.redis_available,
      detail: data.cache.redis_available
        ? 'Redis가 연결되어 있어 서버 재시작 이후에도 캐시 안정성이 좋습니다.'
        : '지금은 메모리 fallback 상태라 재시작 시 캐시가 다시 비워질 수 있습니다.',
    },
    {
      label: '자동 예열',
      ok: data.scheduler_enabled && data.scheduled_warmups.length > 0,
      detail: data.scheduler_enabled
        ? `${data.scheduled_warmups.length}개의 자동 예열 스케줄이 켜져 있어 분봉 후보군을 꾸준히 채웁니다.`
        : '자동 예열이 꺼져 있어 수동으로 캐시를 채워야 합니다.',
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
        ? '실전 사용 준비가 대부분 완료되어 있습니다'
        : level === 'usable'
          ? '사용 가능하지만 아직 보완할 부분이 남아 있습니다'
          : '테스트용에 가깝고 운영 보완이 더 필요합니다',
    summary:
      level === 'ready'
        ? 'KIS, 토큰, 저장 분봉, 자동 예열과 캐시 안정성이 대부분 갖춰져 있어 실제 사용 흐름이 한결 부드럽습니다.'
        : level === 'usable'
          ? '기본 사용은 가능하지만 저장 분봉, Redis, 토큰 같은 운영 기반이 부족하면 체감이 흔들릴 수 있습니다.'
          : '실행은 가능하지만 응답 속도와 안정성을 기대하려면 운영 기반을 더 채우는 편이 좋습니다.',
    bannerClass:
      level === 'ready'
        ? 'border-emerald-500/20 bg-emerald-500/5'
        : level === 'usable'
          ? 'border-amber-500/20 bg-amber-500/5'
          : 'border-red-500/20 bg-red-500/5',
  }
}
