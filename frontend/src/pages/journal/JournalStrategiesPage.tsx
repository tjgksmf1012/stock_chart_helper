import { useQuery } from '@tanstack/react-query'
import { FlaskConical, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { labApi } from '@/lib/api'
import { cn, fmtDateTime } from '@/lib/utils'
import type { LabPaperTradeSummaryItem, LabReport } from '@/types/api'

const VERDICT_CFG = {
  pass: {
    label: '통과',
    icon: ShieldCheck,
    badge: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
    card: 'border-emerald-400/20',
    note: '워크포워드 검증에서 비용 차감 후 기대값이 유의미하게 양수이고 랜덤 진입을 이겼습니다.',
  },
  watch: {
    label: '관찰',
    icon: ShieldQuestion,
    badge: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
    card: 'border-amber-400/20',
    note: '기대값은 양수지만 신뢰구간·벤치마크·데이터 조건 중 하나가 부족합니다. 신호는 경고 라벨과 함께만 노출됩니다.',
  },
  fail: {
    label: '탈락',
    icon: ShieldAlert,
    badge: 'border-red-400/30 bg-red-400/10 text-red-300',
    card: 'border-red-400/20 opacity-80',
    note: '비용 차감 후 기대값이 0 이하 — 이 전략의 신호는 추천에 사용되지 않습니다.',
  },
} as const

const UNIVERSE_LABELS: Record<LabReport['universe_mode'], string> = {
  marcap: '시점 고정 (상폐 포함)',
  pit: '시점 고정 (pykrx)',
  current: '현재 목록 (생존 편향)',
}

/** 실측(종이매매) 드리프트 상태 배지 — 실측 페이지에서도 재사용한다. */
export const DRIFT_CFG: Record<string, { label: string; cls: string } | undefined> = {
  ok: { label: '실측 유지', cls: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' },
  drifting: { label: '실측 이탈', cls: 'border-red-400/30 bg-red-400/10 text-red-300' },
  insufficient: { label: '실측 표본 부족', cls: 'border-border bg-background/50 text-muted-foreground' },
  unknown: { label: '실측 대기', cls: 'border-border bg-background/50 text-muted-foreground' },
}

export default function JournalStrategiesPage() {
  const reportsQ = useQuery({ queryKey: ['lab-reports'], queryFn: labApi.reports, staleTime: 60_000 })
  const paperQ = useQuery({ queryKey: ['lab-paper-summary'], queryFn: labApi.paperTradesSummary, staleTime: 120_000 })
  const paperById = new Map((paperQ.data?.strategies ?? []).map(s => [s.strategy_id, s]))

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xl font-bold">
          <FlaskConical size={20} className="text-primary" />
          전략 검증
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          모든 전략은 같은 저울로 잽니다 — 워크포워드(학습/검증 분리), 거래 비용 차감, 시점 고정 유니버스, 랜덤 진입
          벤치마크. <span className="font-medium text-foreground">검증을 통과하지 못한 전략의 신호는 추천에 쓰이지 않습니다.</span>{' '}
          오늘 나온 신호는 오늘 탭에서 봅니다.
        </p>
      </div>

      {reportsQ.isLoading && <Card className="text-sm text-muted-foreground">검증 리포트를 불러오는 중...</Card>}
      {reportsQ.isError && <QueryError message="검증 리포트를 불러오지 못했습니다." onRetry={() => reportsQ.refetch()} />}

      {reportsQ.data && reportsQ.data.reports.length === 0 && (
        <Card className="text-sm text-muted-foreground">
          아직 검증 리포트가 없습니다. backend에서 <code className="font-mono">scripts/run_lab.py</code>를 실행하면 여기에
          전략 성적표가 나타납니다.
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {reportsQ.data?.reports.map(report => (
          <ReportCard key={report.strategy} report={report} paper={paperById.get(report.strategy)} />
        ))}
      </div>

      {reportsQ.data && reportsQ.data.reports.length > 0 && (
        <Card className="space-y-2 border-border">
          <div className="text-sm font-semibold">읽기 전 주의</div>
          <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed text-muted-foreground">
            <li>
              <span className="font-medium text-foreground">통과 = "진입 엣지 존재" 판정이지 운용 가능 판정이 아닙니다.</span>{' '}
              포지션 사이징·리스크 관리 없이는 포트폴리오 낙폭(MDD)이 감당 불가능할 수 있습니다.
            </li>
            <li>단일 검증 기간의 결과입니다. 시장이 바뀌면 성적도 바뀝니다 — 실측(종이매매) 성적과의 괴리를 계속 확인하세요.</li>
            <li>수익률은 전부 거래 비용(왕복 ~0.38%) 차감 후 값입니다. 비용 차감 전 수치는 어디에도 표시하지 않습니다.</li>
            <li>이 화면은 투자 권유가 아니라 검증 결과의 기록입니다.</li>
          </ul>
        </Card>
      )}
    </div>
  )
}

function ReportCard({ report, paper }: { report: LabReport; paper?: LabPaperTradeSummaryItem }) {
  const cfg = VERDICT_CFG[report.verdict] ?? VERDICT_CFG.fail
  const Icon = cfg.icon
  const [ciLow, ciHigh] = report.ci_95
  const driftCfg = paper ? DRIFT_CFG[paper.drift] : undefined

  return (
    <Card className={cn('space-y-4', cfg.card)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-foreground">{report.label}</div>
          <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{report.strategy}</div>
        </div>
        <span className={cn('inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-bold', cfg.badge)}>
          <Icon size={13} />
          {cfg.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="거래당 기대값" value={signedPct(report.ev_pct)} strong />
        <Metric label="95% 신뢰구간" value={`${signedPct(ciLow)} ~ ${signedPct(ciHigh)}`} />
        <Metric label="랜덤 진입 대비" value={ratioVsRandom(report)} />
        <Metric label="표본" value={`${report.n_trades.toLocaleString('ko-KR')}건`} />
        <Metric label="승률" value={`${Math.round(report.win_rate * 100)}%`} />
        <Metric label="손익비" value={report.payoff_ratio.toFixed(2)} />
        <Metric
          label="포트폴리오 MDD"
          value={report.portfolio_mdd_pct != null ? `${Math.round(report.portfolio_mdd_pct * 100)}%` : '-'}
        />
        <Metric label="데이터 커버리지" value={`${Math.round(report.data_coverage * 100)}%`} />
      </div>

      {report.risk_1pct && report.risk_1pct.n_used > 0 && (
        <div className="rounded-lg border border-sky-400/20 bg-sky-400/5 p-2.5 text-[11px] leading-relaxed">
          <span className="font-medium text-sky-200">리스크 규율 운용 시뮬레이션</span>{' '}
          <span className="text-muted-foreground">
            — 매 트레이드 계좌의 1%만 리스크로 운용하면 검증구간 최대 낙폭{' '}
            <span className="font-semibold text-foreground">{(report.risk_1pct.mdd_pct * 100).toFixed(1)}%</span>, 트레이드당 평균 손익{' '}
            <span className="font-semibold text-foreground">{report.risk_1pct.avg_r.toFixed(2)}R</span>{' '}
            (리스크의 {report.risk_1pct.avg_r.toFixed(2)}배). 갭 손실은 -3R로 상한 — 사이징만으로 못 막는 한계가 있습니다.
          </span>
        </div>
      )}

      <p className="text-xs leading-relaxed text-muted-foreground">{cfg.note}</p>

      {paper && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-background/50 p-2.5 text-[11px]">
          <span className="font-medium text-foreground">실측(종이매매)</span>
          {driftCfg && <span className={cn('rounded border px-1.5 py-0.5 font-semibold', driftCfg.cls)}>{driftCfg.label}</span>}
          <span className="text-muted-foreground">
            {paper.realized_n > 0
              ? `${paper.realized_n}건 · 거래당 ${signedPct(paper.realized_ev_pct ?? 0)}`
              : '아직 청산된 실측 트레이드 없음'}
            {paper.open_count > 0 && ` · 진행중 ${paper.open_count}건`}
          </span>
          {paper.drift === 'drifting' && (
            <span className="w-full text-red-300/90">
              실측 기대값이 백테스트 신뢰구간 하한({signedPct(paper.backtest_ci_low ?? 0)})을 밑돕니다 — 이 전략은 관찰 등급으로 낮춰 보는 편이 안전합니다.
            </span>
          )}
        </div>
      )}

      <div className="space-y-1 rounded-lg border border-border bg-background/50 p-2.5 text-[11px] leading-relaxed text-muted-foreground">
        <div>
          검증: {report.period.start} ~ {report.period.end} · 유니버스 {UNIVERSE_LABELS[report.universe_mode] ?? report.universe_mode}{' '}
          시총 상위 {report.config.top_n} · 학습 {report.config.train_years}년/검증 {report.config.test_months}개월 롤링
        </div>
        {report.universe_note && <div className="text-amber-300/90">⚠️ {report.universe_note}</div>}
        <div>산출: {fmtDateTime(report.generated_at)}</div>
      </div>
    </Card>
  )
}

function Metric({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-sm tabular-nums', strong ? 'font-bold text-foreground' : 'font-medium')}>{value}</div>
    </div>
  )
}

function signedPct(value: number): string {
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}

function ratioVsRandom(report: LabReport): string {
  // 음수 기대값(탈락) 전략은 배율이 무의미 — 표시하지 않는다
  if (report.ev_pct <= 0 || report.random_benchmark_ev_pct == null || report.random_benchmark_ev_pct <= 0) return '-'
  return `${(report.ev_pct / report.random_benchmark_ev_pct).toFixed(1)}배`
}
