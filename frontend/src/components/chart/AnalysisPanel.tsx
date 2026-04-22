import { useState, type ReactNode } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Activity, AlertCircle, Database, Flag, Layers3, ShieldAlert, Target, TrendingDown, TrendingUp } from 'lucide-react'

import type { AnalysisResult, PatternInfo } from '@/types/api'
import { outcomesApi } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { StatRow } from '@/components/ui/StatRow'
import {
  CANDLE_CONFIRMATION_LABELS,
  cn,
  fmtDateTime,
  fmtPct,
  fmtPrice,
  fmtTurnoverBillion,
  getPatternBias,
  INTRADAY_SESSION_LABELS,
  PATTERN_NAMES,
  PATTERN_VARIANT_NAMES,
  STATE_COLORS,
  STATE_LABELS,
  WYCKOFF_LABELS,
} from '@/lib/utils'

interface AnalysisPanelProps {
  analysis: AnalysisResult
  symbol?: string
  timeframe?: string
}

type AnalysisTab = 'overview' | 'setup' | 'pattern' | 'data'

const ANALYSIS_TABS: Array<{ key: AnalysisTab; label: string }> = [
  { key: 'overview', label: '핵심 판단' },
  { key: 'setup', label: '셋업 점수' },
  { key: 'pattern', label: '패턴 상세' },
  { key: 'data', label: '데이터 메모' },
]

export function AnalysisPanel({ analysis, symbol, timeframe }: AnalysisPanelProps) {
  const [activeTab, setActiveTab] = useState<AnalysisTab>('overview')
  const bestPattern = analysis.patterns[0]

  return (
    <div className="space-y-4">
      <ProbabilityCard analysis={analysis} symbol={symbol} timeframe={timeframe} />

      <div className="sticky top-[78px] z-20 flex gap-1 overflow-x-auto rounded-lg border border-border bg-background/92 p-1 backdrop-blur">
        {ANALYSIS_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              'rounded-lg px-3 py-2 text-xs font-medium transition-colors',
              activeTab === tab.key
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-background/70 hover:text-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <div className="space-y-3">
          <ActionPlanCard analysis={analysis} />
          <DecisionSummaryGrid analysis={analysis} />
          <DecisionSupportCard analysis={analysis} />
          <ProjectionCard analysis={analysis} />
        </div>
      )}

      {activeTab === 'setup' && (
        <div className="space-y-3">
          <ScoreOverviewCard analysis={analysis} />
          <TradeReadinessCard analysis={analysis} />
          <EntryWindowCard analysis={analysis} />
          <FreshnessCard analysis={analysis} />
          <ReentryCard analysis={analysis} />
          <ActiveSetupCard analysis={analysis} />
        </div>
      )}

      {activeTab === 'pattern' && (
        <div className="space-y-3">
          <MarketContextCard analysis={analysis} />
          <IchimokuCard analysis={analysis} />
          {bestPattern && <BestPatternCard pattern={bestPattern} analysis={analysis} />}
          <PatternsListCard analysis={analysis} />
          <CautionCard />
        </div>
      )}

      {activeTab === 'data' && (
        <div className="space-y-3">
          <DataMemoCard analysis={analysis} />
          <ScoreDetailCard analysis={analysis} />
        </div>
      )}
    </div>
  )
}

function DecisionSummaryGrid({ analysis }: { analysis: AnalysisResult }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <MiniSummaryCard title={analysis.trade_readiness_label} tone="emerald" body={analysis.trade_readiness_summary} />
      <MiniSummaryCard title={analysis.entry_window_label} tone="sky" body={analysis.entry_window_summary} />
      <MiniSummaryCard title={analysis.freshness_label} tone="violet" body={analysis.freshness_summary} />
      <MiniSummaryCard
        title={analysis.reentry_case_label || analysis.reentry_label}
        tone="amber"
        body={analysis.reentry_summary}
      />
    </div>
  )
}

function MiniSummaryCard({
  title,
  body,
  tone,
}: {
  title: string
  body: string
  tone: 'emerald' | 'sky' | 'violet' | 'amber'
}) {
  const toneClass = {
    emerald: 'border-emerald-400/20 bg-emerald-400/6',
    sky: 'border-sky-400/20 bg-sky-400/6',
    violet: 'border-violet-400/20 bg-violet-400/6',
    amber: 'border-amber-400/20 bg-amber-400/6',
  }[tone]

  return (
    <Card className={cn('space-y-2', toneClass)}>
      <div className="text-sm font-semibold">{title}</div>
      <p className="text-xs leading-relaxed text-muted-foreground">{body}</p>
    </Card>
  )
}

function ProjectionCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3">
      <div className="text-sm font-semibold">조건부 예상 시나리오</div>
      <div className="rounded-lg border border-border bg-background/55 p-3">
        <div className="text-sm font-medium">{analysis.projection_label || '중립 시나리오'}</div>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{analysis.projection_summary}</p>
      </div>

      {analysis.projection_scenarios.length > 0 && (
        <div className="grid gap-2">
          {analysis.projection_scenarios.map(scenario => (
            <div key={scenario.key} className="rounded-lg border border-border bg-background/50 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-medium">{scenario.label}</div>
                <Badge
                  variant={
                    scenario.key === 'risk'
                      ? 'warning'
                      : scenario.bias === 'bearish'
                        ? 'bearish'
                        : scenario.bias === 'bullish'
                          ? 'bullish'
                          : 'muted'
                  }
                >
                  {fmtPct(scenario.weight, 0)}
                </Badge>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{scenario.summary}</p>
            </div>
          ))}
        </div>
      )}

      {analysis.projection_caution && (
        <div className="rounded-lg border border-sky-400/15 bg-sky-400/5 p-3 text-xs leading-relaxed text-sky-100">
          {analysis.projection_caution}
        </div>
      )}
    </Card>
  )
}

function IchimokuCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Layers3 size={15} className="text-primary" />
        일목균형표 해석
      </div>
      <div className="rounded-lg border border-border bg-background/55 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="muted">{analysis.ichimoku.cloud_position}</Badge>
          <Badge variant="neutral">{analysis.ichimoku.prior_high_structure}</Badge>
          <Badge variant={analysis.ichimoku.bias === 'bullish' ? 'bullish' : analysis.ichimoku.bias === 'bearish' ? 'bearish' : 'muted'}>
            점수 {fmtPct(analysis.ichimoku.score, 0)}
          </Badge>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{analysis.ichimoku.summary}</p>
      </div>

      <div className="space-y-2">
        {analysis.ichimoku.signals.map(signal => (
          <div key={signal} className="rounded-lg border border-border bg-background/50 px-3 py-2 text-xs text-muted-foreground">
            {signal}
          </div>
        ))}
      </div>

      {analysis.ichimoku.caution && (
        <div className="rounded-lg border border-amber-400/20 bg-amber-400/8 p-3 text-xs leading-relaxed text-amber-100">
          {analysis.ichimoku.caution}
        </div>
      )}
    </Card>
  )
}

function ScoreOverviewCard({ analysis }: { analysis: AnalysisResult }) {
  const metrics = [
    { label: '상승 확률', value: fmtPct(analysis.p_up, 0), tone: 'text-emerald-300' },
    { label: '하락 확률', value: fmtPct(analysis.p_down, 0), tone: 'text-red-300' },
    { label: '신뢰도', value: fmtPct(analysis.confidence, 0) },
    { label: '손익비', value: analysis.reward_risk_ratio.toFixed(2) },
    { label: 'Edge', value: fmtPct(analysis.historical_edge_score, 0) },
    { label: '표본 신뢰도', value: fmtPct(analysis.sample_reliability, 0) },
  ]

  return (
    <Card className="space-y-3">
      <div className="text-sm font-semibold">점수 한눈에 보기</div>
      <div className="grid grid-cols-2 gap-3">
        {metrics.map(metric => (
          <div key={metric.label} className="rounded-lg border border-border bg-background/55 p-3">
            <div className="text-xs text-muted-foreground">{metric.label}</div>
            <div className={cn('mt-1 text-sm font-semibold', metric.tone)}>{metric.value}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function PatternsListCard({ analysis }: { analysis: AnalysisResult }) {
  if (analysis.patterns.length === 0) {
    return (
      <Card className="text-sm text-muted-foreground">감지된 패턴이 아직 없습니다.</Card>
    )
  }

  return (
    <Card className="space-y-3">
      <div className="text-sm font-semibold">감지된 패턴</div>
      <div className="space-y-3">
        {analysis.patterns.map((pattern, index) => (
          <PatternCard key={`${pattern.pattern_type}-${index}`} pattern={pattern} />
        ))}
      </div>
    </Card>
  )
}

function DataMemoCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Database size={14} className="text-primary" />
        데이터 메모
      </div>
      <div className="space-y-2">
        <StatRow label="데이터 출처" value={analysis.data_source} />
        <StatRow label="데이터 상태" value={analysis.fetch_status_label} />
        <StatRow label="데이터 품질" value={fmtPct(analysis.data_quality)} />
        <StatRow label="유동성" value={fmtPct(analysis.liquidity_score)} />
        <StatRow label="평균 거래대금" value={fmtTurnoverBillion(analysis.avg_turnover_billion)} />
        <StatRow label="통계 기준" value={analysis.stats_timeframe} />
        <StatRow label="사용 바 수" value={`${analysis.available_bars.toLocaleString('ko-KR')}개`} />
        <StatRow label="와이코프" value={WYCKOFF_LABELS[analysis.wyckoff_phase] ?? analysis.wyckoff_phase} />
        <StatRow label="장중 세션" value={INTRADAY_SESSION_LABELS[analysis.intraday_session_phase] ?? analysis.intraday_session_phase} />
      </div>

      <div className="space-y-2 rounded-lg border border-border bg-background/55 p-3 text-xs leading-relaxed text-muted-foreground">
        <p>{analysis.source_note}</p>
        {analysis.fetch_message && <p>{analysis.fetch_message}</p>}
        {analysis.wyckoff_note && <p className="text-sky-200">{analysis.wyckoff_note}</p>}
        {analysis.intraday_session_note && <p className="text-violet-200">{analysis.intraday_session_note}</p>}
        {analysis.trend_warning && <p className="text-amber-200">{analysis.trend_warning}</p>}
      </div>
    </Card>
  )
}

function ScoreDetailCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3">
      <div className="text-sm font-semibold">점수 상세</div>
      <div className="space-y-2">
        <StatRow label="교과서 유사도" value={fmtPct(analysis.textbook_similarity)} />
        <StatRow label="패턴 확인 점수" value={fmtPct(analysis.pattern_confirmation_score)} />
        <StatRow label="진입 적합도" value={fmtPct(analysis.entry_score)} />
        <StatRow label="완성도" value={fmtPct(analysis.completion_proximity)} />
        <StatRow label="헤드룸" value={fmtPct(analysis.headroom_score)} />
        <StatRow label="목표 거리" value={fmtPct(analysis.target_distance_pct)} />
        <StatRow label="손절 거리" value={fmtPct(analysis.stop_distance_pct)} />
        <StatRow label="평균 MFE" value={fmtPct(analysis.avg_mfe_pct)} />
        <StatRow label="평균 MAE" value={fmtPct(analysis.avg_mae_pct)} />
        <StatRow label="평균 보유 바 수" value={`${Math.round(analysis.avg_bars_to_outcome ?? 0)}개`} />
      </div>
    </Card>
  )
}

function CautionCard() {
  return (
    <Card className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <ShieldAlert size={15} className="text-orange-400" />
        해석 주의
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        이 화면은 패턴 기반 보조 분석 도구입니다. 이미 목표가에 도달했거나 무효화된 패턴은 신선도와 거래 준비도에서 강하게
        감점되며, 실전 판단 전에는 추세와 거래대금, 리스크 기준을 함께 보는 편이 안전합니다.
      </p>
    </Card>
  )
}

function BestPatternCard({ pattern, analysis }: { pattern: PatternInfo; analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Target size={15} className="text-primary" />
        핵심 패턴
      </div>
      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={badgeVariant(pattern)}>{PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type}</Badge>
          {pattern.variant && <Badge variant="muted">{PATTERN_VARIANT_NAMES[pattern.variant] ?? pattern.variant}</Badge>}
          <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[pattern.state])}>{STATE_LABELS[pattern.state]}</span>
          <Badge variant={scoreVariant(pattern.lifecycle_score)}>{pattern.lifecycle_label}</Badge>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{analysis.action_plan_summary}</p>
        {pattern.lifecycle_note && <p className="mt-2 text-xs text-violet-200">{pattern.lifecycle_note}</p>}
        {pattern.candlestick_note && <p className="mt-2 text-xs text-sky-200">{pattern.candlestick_note}</p>}
      </div>
      <div className="space-y-2">
        {pattern.neckline !== null && <StatRow label="목선" value={fmtPrice(pattern.neckline)} />}
        {pattern.target_level !== null && (
          <StatRow label="목표가" value={<span className="text-emerald-300">{fmtPrice(pattern.target_level)}</span>} />
        )}
        {pattern.invalidation_level !== null && (
          <StatRow label="무효화 기준" value={<span className="text-red-300">{fmtPrice(pattern.invalidation_level)}</span>} />
        )}
        {pattern.target_hit_at && <StatRow label="목표가 도달" value={fmtDateTime(pattern.target_hit_at)} />}
        {pattern.invalidated_at && <StatRow label="무효화 시점" value={fmtDateTime(pattern.invalidated_at)} />}
      </div>
    </Card>
  )
}

function PatternCard({ pattern }: { pattern: PatternInfo }) {
  return (
    <div className="space-y-2 rounded-lg border border-border bg-background/50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={badgeVariant(pattern)}>{PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type}</Badge>
        <Badge variant="muted">등급 {pattern.grade}</Badge>
        <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[pattern.state])}>{STATE_LABELS[pattern.state]}</span>
        <Badge variant={scoreVariant(pattern.lifecycle_score)}>{pattern.lifecycle_label}</Badge>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>교과서 유사도 {fmtPct(pattern.textbook_similarity)}</span>
        <span className="text-right">변형 적합도 {fmtPct(pattern.variant_fit)}</span>
        <span>다리 균형 {fmtPct(pattern.leg_balance_fit)}</span>
        <span className="text-right">반전 에너지 {fmtPct(pattern.reversal_energy_fit)}</span>
        <span>돌파 품질 {fmtPct(pattern.breakout_quality_fit)}</span>
        <span className="text-right">리테스트 {fmtPct(pattern.retest_quality_fit)}</span>
      </div>
      <div className="text-xs text-muted-foreground">
        {CANDLE_CONFIRMATION_LABELS[pattern.candlestick_label ?? 'neutral'] ?? pattern.candlestick_label ?? '중립 캔들'}
      </div>
      {pattern.lifecycle_note && <p className="text-xs leading-relaxed text-muted-foreground">{pattern.lifecycle_note}</p>}
    </div>
  )
}

function ActionPlanCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3 border-primary/20 bg-primary/6">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Activity size={15} className="text-primary" />
        실전 행동 가이드
        <Badge variant={actionPlanVariant(analysis.action_plan)} className="ml-auto">
          {analysis.action_plan_label}
        </Badge>
      </div>
      <p className="text-sm leading-relaxed text-foreground/95">{analysis.action_plan_summary}</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <CompactMetric label="준비도" value={fmtPct(analysis.trade_readiness_score ?? 0, 0)} />
        <CompactMetric label="진입 구간" value={fmtPct(analysis.entry_window_score ?? 0, 0)} />
        <CompactMetric label="신선도" value={fmtPct(analysis.freshness_score ?? 0, 0)} />
        <CompactMetric label="행동 우선순위" value={fmtPct(analysis.action_priority_score, 0)} />
      </div>
    </Card>
  )
}

function CompactMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  )
}

function TradeReadinessCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.trade_readiness_score ?? 0
  return (
    <ScoreDetailPanel
      icon={<Target size={15} className="text-emerald-300" />}
      title="거래 준비도"
      badge={analysis.trade_readiness_label}
      badgeVariant={scoreVariant(score)}
      score={score}
      color="bg-emerald-400"
      description={analysis.trade_readiness_summary}
      factors={analysis.score_factors}
    />
  )
}

function EntryWindowCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.entry_window_score ?? 0
  return (
    <ScoreDetailPanel
      icon={<Target size={15} className="text-sky-300" />}
      title="진입 구간"
      badge={analysis.entry_window_label}
      badgeVariant={scoreVariant(score)}
      score={score}
      color="bg-sky-300"
      description={analysis.entry_window_summary}
    />
  )
}

function FreshnessCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.freshness_score ?? 0
  return (
    <ScoreDetailPanel
      icon={<Layers3 size={15} className="text-violet-300" />}
      title="패턴 신선도"
      badge={analysis.freshness_label}
      badgeVariant={scoreVariant(score)}
      score={score}
      color="bg-violet-300"
      description={analysis.freshness_summary}
    />
  )
}

function ReentryCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.reentry_score ?? 0

  return (
    <Card className="space-y-3 border-amber-400/20 bg-amber-400/6">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Target size={15} className="text-amber-300" />
        재진입 구조
        <Badge variant={scoreVariant(score)} className="ml-auto">
          {analysis.reentry_label}
        </Badge>
      </div>
      <ProgressBar score={score} color="bg-amber-300" />
      <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reentry_summary}</p>

      {(analysis.reentry_case_label || analysis.reentry_profile_label) && (
        <div className="grid gap-2 sm:grid-cols-2">
          {analysis.reentry_case !== 'none' && analysis.reentry_case_label && (
            <CompactMetric label="유형" value={analysis.reentry_case_label} />
          )}
          {analysis.reentry_profile_key !== 'none' && analysis.reentry_profile_label && (
            <CompactMetric label="해석 기준" value={analysis.reentry_profile_label} />
          )}
        </div>
      )}

      {analysis.reentry_trigger && (
        <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
          <span className="font-medium text-amber-200">확인 포인트:</span> {analysis.reentry_trigger}
        </div>
      )}

      {analysis.reentry_factors?.length > 0 && (
        <div className="grid gap-2">
          {analysis.reentry_factors.map(factor => (
            <FactorCard key={factor.label} factor={factor} color="bg-amber-300" />
          ))}
        </div>
      )}
    </Card>
  )
}

function ActiveSetupCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.active_setup_score ?? 0
  return (
    <ScoreDetailPanel
      icon={<Activity size={15} className="text-cyan-300" />}
      title="활성 셋업"
      badge={analysis.active_setup_label}
      badgeVariant={scoreVariant(score)}
      score={score}
      color="bg-cyan-300"
      description={analysis.active_setup_summary}
      footer={
        <div className="grid grid-cols-2 gap-3">
          <CompactMetric label="활성 패턴" value={`${analysis.active_pattern_count}개`} />
          <CompactMetric label="완료 / 무효" value={`${analysis.completed_pattern_count}개`} />
        </div>
      }
    />
  )
}

function MarketContextCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Layers3 size={15} className="text-primary" />
        시장 맥락과 가격 공간
      </div>
      <div className="grid grid-cols-2 gap-3">
        <CompactMetric label="추세 방향" value={analysis.trend_direction || '-'} />
        <CompactMetric label="추세 정렬" value={fmtPct(analysis.trend_alignment_score ?? 0)} />
        <CompactMetric label="헤드룸" value={fmtPct(analysis.headroom_score ?? 0)} />
        <CompactMetric label="목표 거리" value={fmtPct(analysis.target_distance_pct ?? 0)} />
        <CompactMetric label="손절 거리" value={fmtPct(analysis.stop_distance_pct ?? 0)} />
        <CompactMetric label="평균 보유 바 수" value={`${Math.round(analysis.avg_bars_to_outcome ?? 0)}개`} />
      </div>
      <div className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
        현재 구조는 {analysis.wyckoff_note || '와이코프 해석 없음'} 기준으로 읽히며, 장중 세션은{' '}
        {INTRADAY_SESSION_LABELS[analysis.intraday_session_phase] ?? analysis.intraday_session_phase} 맥락을 따릅니다.
        {(analysis.avg_turnover_billion ?? 0) > 0 && ` 평균 거래대금은 ${fmtTurnoverBillion(analysis.avg_turnover_billion)} 수준입니다.`}
      </div>
    </Card>
  )
}

function DecisionSupportCard({ analysis }: { analysis: AnalysisResult }) {
  const flags = analysis.risk_flags ?? []
  const checklist = analysis.confirmation_checklist ?? []
  if (!flags.length && !checklist.length && !analysis.next_trigger) return null

  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <ShieldAlert size={15} className="text-orange-400" />
        실전 체크
      </div>
      {analysis.next_trigger && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-primary">다음 트리거:</span> {analysis.next_trigger}
        </div>
      )}
      {flags.length > 0 && (
        <div className="space-y-2">
          {flags.slice(0, 4).map((flag, index) => (
            <div key={`${flag}-${index}`} className="rounded-lg border border-orange-400/15 bg-orange-400/5 px-3 py-2 text-xs text-orange-100">
              {flag}
            </div>
          ))}
        </div>
      )}
      {checklist.length > 0 && (
        <ol className="space-y-2 text-xs text-muted-foreground">
          {checklist.map((item, index) => (
            <li key={`${item}-${index}`} className="rounded-lg border border-border bg-background/55 px-3 py-2">
              {index + 1}. {item}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}

function ScoreDetailPanel({
  icon,
  title,
  badge,
  badgeVariant,
  score,
  color,
  description,
  factors,
  footer,
}: {
  icon: ReactNode
  title: string
  badge: string
  badgeVariant: 'bullish' | 'warning' | 'muted' | 'neutral'
  score: number
  color: string
  description: string
  factors?: Array<{ label: string; score: number; weight: number; note: string }>
  footer?: ReactNode
}) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
        <Badge variant={badgeVariant} className="ml-auto">
          {badge}
        </Badge>
      </div>
      <ProgressBar score={score} color={color} />
      <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      {factors && factors.length > 0 && (
        <div className="grid gap-2">
          {factors.map(factor => (
            <FactorCard key={factor.label} factor={factor} color={color} />
          ))}
        </div>
      )}
      {footer}
    </Card>
  )
}

function FactorCard({
  factor,
  color,
}: {
  factor: { label: string; score: number; weight: number; note: string }
  color: string
}) {
  return (
    <div className="rounded-lg border border-border bg-background/55 p-3">
      <div className="mb-1 flex items-center justify-between gap-2 text-xs">
        <span className="font-medium text-foreground">{factor.label}</span>
        <span className="font-mono text-muted-foreground">
          {fmtPct(factor.score, 0)} / {Math.round(factor.weight * 100)}%
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-card">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${Math.round(factor.score * 100)}%` }} />
      </div>
      {factor.note && <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{factor.note}</p>}
    </div>
  )
}

function ProgressBar({ score, color }: { score: number; color: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
        <span>점수</span>
        <span className="font-mono">{fmtPct(score, 0)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-background">
        <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${Math.round(score * 100)}%` }} />
      </div>
    </div>
  )
}

function badgeVariant(pattern: PatternInfo): 'bullish' | 'bearish' | 'neutral' {
  return getPatternBias(pattern.pattern_type)
}

function actionPlanVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}

function scoreVariant(score: number): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (score >= 0.72) return 'bullish'
  if (score >= 0.56) return 'neutral'
  if (score >= 0.4) return 'warning'
  return 'muted'
}

function ProbabilityCard({
  analysis,
  symbol,
  timeframe,
}: {
  analysis: AnalysisResult
  symbol?: string
  timeframe?: string
}) {
  const [flagged, setFlagged] = useState(false)

  const flagMutation = useMutation({
    mutationFn: () =>
      outcomesApi.record({
        symbol_code: symbol ?? analysis.symbol?.code ?? '',
        symbol_name: analysis.symbol?.name ?? '',
        pattern_type: analysis.patterns[0]?.pattern_type ?? 'no_pattern',
        timeframe: timeframe ?? analysis.timeframe,
        signal_date: new Date().toISOString().slice(0, 10),
        entry_price: 0,
        target_price: null,
        stop_price: null,
        outcome: 'cancelled',
        notes: 'user_false_positive',
        p_up_at_signal: analysis.p_up,
        textbook_similarity_at_signal: analysis.textbook_similarity,
        trade_readiness_at_signal: analysis.trade_readiness_score ?? 0,
      }),
    onSuccess: () => setFlagged(true),
  })

  const canFlag = analysis.patterns.length > 0 && !analysis.no_signal_flag

  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        {analysis.p_up >= 0.55 ? (
          <TrendingUp size={14} className="text-emerald-300" />
        ) : analysis.p_down >= 0.55 ? (
          <TrendingDown size={14} className="text-red-300" />
        ) : (
          <Activity size={14} className="text-primary" />
        )}
        확률 분석
        <Badge variant="muted" className="ml-auto">
          {analysis.timeframe_label}
        </Badge>
        {canFlag && (
          <button
            onClick={() => {
              if (!flagged) flagMutation.mutate()
            }}
            disabled={flagged || flagMutation.isPending}
            className={cn(
              'flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition-colors',
              flagged ? 'text-amber-300' : 'text-muted-foreground hover:text-amber-300 disabled:opacity-40',
            )}
            title="이 패턴은 오탐으로 보입니다."
          >
            <Flag size={11} className={flagged ? 'fill-amber-300' : ''} />
            {flagged ? '신고됨' : '오탐 신고'}
          </button>
        )}
      </div>
      {analysis.no_signal_flag ? (
        <div className="space-y-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2 text-yellow-300">
            <AlertCircle size={14} />
            <span className="font-medium">No Signal</span>
          </div>
          <p>{analysis.no_signal_reason}</p>
          <p>{analysis.reason_summary}</p>
          <div className="rounded-lg border border-amber-400/15 bg-amber-400/5 p-3 text-xs leading-relaxed text-amber-100">
            <span className="font-medium">다음 액션:</span> {buildNoSignalAction(analysis)}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <ProbBar p_up={analysis.p_up} p_down={analysis.p_down} size="md" />
          <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reason_summary}</p>
        </div>
      )}
    </Card>
  )
}

function buildNoSignalAction(analysis: AnalysisResult): string {
  if ((analysis.available_bars ?? 0) < 80) {
    return '현재 타임프레임은 바 수가 부족할 수 있습니다. 일봉이나 주봉으로 먼저 구조를 확인한 뒤 다시 보는 편이 안전합니다.'
  }
  if ((analysis.data_quality ?? 0) < 0.6) {
    return '데이터 품질이 낮아 점수를 확정값처럼 보기 어렵습니다. 분봉 예열이나 저장 데이터가 더 쌓인 뒤 재확인해 보세요.'
  }
  if (analysis.next_trigger) {
    return `바로 진입하기보다 다음 트리거인 "${analysis.next_trigger}"가 나오는지 먼저 확인하는 흐름이 좋습니다.`
  }
  return '현재는 억지로 패턴을 붙이기보다 관망 우선 구간으로 보고, 신선도와 거래 준비도가 더 살아나는지 기다리는 편이 좋습니다.'
}
