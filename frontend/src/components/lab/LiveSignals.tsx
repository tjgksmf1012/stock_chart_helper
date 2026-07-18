import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Crown, Zap } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { pickTopSignal } from '@/lib/topPick'
import { cn, fmtDateTime, fmtPrice } from '@/lib/utils'
import type { LabEligibleStrategy, LabRegimeGate, LabSignal, LabSignalDemotion } from '@/types/api'

/** 신호 행에 붙는 판정 등급 배지 (판정 카드의 VERDICT_CFG에서 배지 부분만 분리) */
export const SIGNAL_VERDICT_BADGE: Record<string, { label: string; badge: string }> = {
  pass: { label: '통과', badge: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' },
  watch: { label: '관찰', badge: 'border-amber-400/30 bg-amber-400/10 text-amber-300' },
  fail: { label: '탈락', badge: 'border-red-400/30 bg-red-400/10 text-red-300' },
}

// 백엔드 lab/sizing.py의 position_size()와 같은 고정 리스크 공식 (롱 전용).
// 기준가(신호일 종가)를 진입가 근사로 쓰고, 집중 상한 20%를 적용한다.
function suggestShares(accountValue: number, riskPct: number, referencePrice: number | null | undefined, stopPrice: number) {
  if (!referencePrice || referencePrice <= 0 || accountValue <= 0 || riskPct <= 0) return null
  const perShareRisk = referencePrice - stopPrice
  if (perShareRisk <= 0) return null
  let shares = Math.floor((accountValue * riskPct) / perShareRisk)
  let capped = false
  const maxByConcentration = Math.floor((accountValue * 0.2) / referencePrice)
  if (shares > maxByConcentration) {
    shares = maxByConcentration
    capped = true
  }
  return { shares, positionValue: shares * referencePrice, capped }
}

const SIZING_STORAGE_KEY = 'lab-sizing-config-v1'

function loadSizingConfig(): { account: number; riskPct: number } {
  try {
    const raw = localStorage.getItem(SIZING_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (typeof parsed.account === 'number' && typeof parsed.riskPct === 'number') return parsed
    }
  } catch { /* 무시 — 기본값 사용 */ }
  return { account: 10_000_000, riskPct: 0.01 }
}

export function LiveSignals({
  loading,
  error,
  onRetry,
  signals,
  note,
  generatedAt,
  demotions,
  eligible,
  regimeGate,
}: {
  loading: boolean
  error: boolean
  onRetry: () => void
  signals: LabSignal[]
  note: string | null
  generatedAt?: string
  demotions?: LabSignalDemotion[]
  eligible?: LabEligibleStrategy[]
  regimeGate?: LabRegimeGate
}) {
  const nav = useNavigate()
  const [sizing, setSizing] = useState(loadSizingConfig)

  const updateSizing = (next: { account: number; riskPct: number }) => {
    setSizing(next)
    try {
      localStorage.setItem(SIZING_STORAGE_KEY, JSON.stringify(next))
    } catch { /* localStorage 불가 환경 무시 */ }
  }

  return (
    <Card className="space-y-3 border-primary/25 bg-primary/5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Zap size={16} className="text-primary" />
          검증 통과 전략의 최근 신호
        </div>
        {generatedAt && <span className="text-[11px] text-muted-foreground">{fmtDateTime(generatedAt)}</span>}
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        통과·관찰 등급 전략이 최근 5영업일 안에 낸 신호만 모았습니다. 탈락 전략의 신호는 포함하지 않습니다.
        진입은 다음 거래일 시가 기준이며, 손절·보유기간은 각 전략의 규칙을 따릅니다.
      </p>

      {/* 시장 체제 게이트 (실험① 채택) — 비우호 체제에서는 신호 발행 자체가 정지된다 */}
      {!loading && regimeGate?.enabled && regimeGate.ok_today === false && (
        <div className="rounded-lg border border-sky-400/25 bg-sky-400/8 p-2.5 text-xs leading-relaxed text-sky-200/90">
          <span className="font-medium">시장 체제 비우호 — 신호 발행 정지 중.</span> KOSPI가 200일선 아래에 있어
          검증된 전략의 신호를 내지 않습니다. 검증 결과 이 시기의 진입은 기대값을 갉아먹었습니다 — 신호가 없는 것이
          시스템이 일하고 있는 것입니다.
        </div>
      )}

      {/* 드리프트 자동 강등 — 실측(종이매매)이 백테스트를 이탈한 전략의 경고 */}
      {!loading && demotions && demotions.length > 0 && (
        <div className="space-y-1 rounded-lg border border-amber-400/25 bg-amber-400/8 p-2.5 text-xs leading-relaxed text-amber-200/90">
          {demotions.map(d => (
            <div key={d.strategy_id}>
              <span className="font-medium">{d.label}</span> — {d.reason}
              {d.to === 'fail'
                ? ' (이 전략의 신호는 아래 목록에서 제외됐습니다)'
                : ' (신호는 관찰 등급으로 표시됩니다)'}
            </div>
          ))}
        </div>
      )}

      {loading && <div className="py-4 text-center text-xs text-muted-foreground">현재 유니버스에서 신호를 계산하는 중입니다... (최대 1~2분)</div>}
      {error && <QueryError message="라이브 신호를 불러오지 못했습니다." onRetry={onRetry} />}
      {note && !loading && <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 p-2.5 text-xs text-amber-200/90">{note}</div>}

      {!loading && !error && !note && signals.length === 0 && (
        <div className="rounded-lg border border-border bg-background/50 p-3 text-xs text-muted-foreground">
          최근 5영업일 내 검증 통과 전략의 신호가 없습니다. 이것은 정상입니다 — 조건이 맞을 때만 신호가 나옵니다.
        </div>
      )}

      {signals.length > 0 && (
        <>
          <TopPickStrip
            signals={signals}
            eligible={eligible ?? []}
            sizing={sizing}
            onOpenChart={code => nav(`/chart/${code}`)}
          />

          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-background/50 p-2.5 text-xs">
            <span className="font-medium text-foreground">포지션 계산기</span>
            <label className="flex items-center gap-1.5 text-muted-foreground">
              계좌
              <input
                type="number"
                value={sizing.account}
                min={0}
                step={1_000_000}
                onChange={e => updateSizing({ ...sizing, account: Number(e.target.value) || 0 })}
                className="w-28 rounded border border-border bg-card px-2 py-1 font-mono text-foreground"
              />
              원
            </label>
            <label className="flex items-center gap-1.5 text-muted-foreground">
              트레이드당 리스크
              <select
                value={sizing.riskPct}
                onChange={e => updateSizing({ ...sizing, riskPct: Number(e.target.value) })}
                className="rounded border border-border bg-card px-2 py-1 text-foreground"
              >
                <option value={0.005}>0.5%</option>
                <option value={0.01}>1%</option>
                <option value={0.02}>2%</option>
              </select>
            </label>
            <span className="text-muted-foreground/80">
              손절에 걸리면 계좌의 {`${(sizing.riskPct * 100).toFixed(1)}%`}만 잃도록 수량을 계산합니다 (종목당 최대 20%).
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-xs">
              <thead>
                <tr className="border-b border-border/70 text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">종목</th>
                  <th className="py-2 pr-3 font-medium">전략</th>
                  <th className="py-2 pr-3 font-medium">등급</th>
                  <th className="py-2 pr-3 font-medium">신호일</th>
                  <th className="py-2 pr-3 font-medium">기준가</th>
                  <th className="py-2 pr-3 font-medium">손절</th>
                  <th className="py-2 pr-3 font-medium">권장 수량</th>
                  <th className="py-2 font-medium">보유</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, i) => {
                  const cfg = SIGNAL_VERDICT_BADGE[sig.verdict ?? 'watch'] ?? SIGNAL_VERDICT_BADGE.watch
                  const size = suggestShares(sizing.account, sizing.riskPct, sig.reference_price, sig.stop_price)
                  return (
                    <tr
                      key={`${sig.strategy_id}-${sig.code}-${i}`}
                      className="cursor-pointer border-b border-border/40 hover:bg-muted/30"
                      onClick={() => nav(`/chart/${sig.code}`)}
                    >
                      <td className="py-2 pr-3">
                        <div className="font-medium text-foreground">{sig.name ?? sig.code}</div>
                        {sig.name && <div className="font-mono text-[10px] text-muted-foreground">{sig.code}</div>}
                      </td>
                      <td className="py-2 pr-3">{sig.strategy_label}</td>
                      <td className="py-2 pr-3">
                        <span className={cn('rounded border px-1.5 py-0.5 text-[10px] font-semibold', cfg.badge)}>{cfg.label}</span>
                      </td>
                      <td className="py-2 pr-3 font-mono text-muted-foreground">{sig.signal_date}</td>
                      <td className="py-2 pr-3 font-mono text-muted-foreground">{sig.reference_price ? fmtPrice(sig.reference_price) : '-'}</td>
                      <td className="py-2 pr-3 font-mono text-red-300">{fmtPrice(sig.stop_price)}</td>
                      <td className="py-2 pr-3 font-mono text-foreground">
                        {size && size.shares > 0 ? (
                          <>
                            {size.shares.toLocaleString('ko-KR')}주
                            {size.capped && <span className="ml-1 text-[10px] text-amber-300" title="집중 상한(계좌의 20%)으로 제한됨">상한</span>}
                          </>
                        ) : size && size.shares === 0 ? (
                          <span
                            className="text-amber-300"
                            title={`손절폭 ${stopDistancePct(sig)}%가 너무 넓어 설정 리스크로는 1주도 살 수 없습니다 — 이 신호는 건너뛰는 것이 규율입니다`}
                          >
                            0주 · 진입 불가
                          </span>
                        ) : '-'}
                      </td>
                      <td className="py-2 text-muted-foreground">{sig.max_holding_days}일</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-muted-foreground/80">
            기준가는 신호일 종가이며 실제 진입가(다음 거래일 시가)와 다를 수 있습니다. 갭 하락 시 손절보다 낮은 가격에
            체결될 수 있어 실제 손실이 설정 리스크를 초과할 수 있습니다.
          </p>
        </>
      )}
    </Card>
  )
}

/** 오늘의 최우선 — pass 신호 중 검증 EV 최고를 지목. watch만 있으면 "없음"을 정직하게 말한다. */
function TopPickStrip({
  signals,
  eligible,
  sizing,
  onOpenChart,
}: {
  signals: LabSignal[]
  eligible: LabEligibleStrategy[]
  sizing: { account: number; riskPct: number }
  onOpenChart: (code: string) => void
}) {
  const top = pickTopSignal(signals, eligible)

  if (!top) {
    return (
      <div className="rounded-lg border border-border bg-background/50 p-3 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">오늘의 최우선 없음</span> — 통과 등급 신호가 없습니다. 관찰
        등급은 최우선으로 지목하지 않으며, 안 사는 것도 전략입니다.
      </div>
    )
  }

  const ev = eligible.find(e => e.strategy_id === top.strategy_id)?.ev_pct
  const size = suggestShares(sizing.account, sizing.riskPct, top.reference_price, top.stop_price)

  return (
    <button
      onClick={() => onOpenChart(top.code)}
      className="flex w-full flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg border border-emerald-400/25 bg-emerald-400/8 p-3 text-left text-xs transition-colors hover:bg-emerald-400/12"
    >
      <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-200">
        <Crown size={13} />
        오늘의 최우선
      </span>
      <span className="text-sm font-bold text-foreground">
        {top.name ?? top.code}
        {top.name && <span className="ml-1.5 font-mono text-[11px] font-normal text-muted-foreground">{top.code}</span>}
      </span>
      <span className="text-muted-foreground">
        {top.strategy_label}
        {ev != null && <> · 검증 EV {`${ev > 0 ? '+' : ''}${(ev * 100).toFixed(1)}%`}/거래</>}
      </span>
      <span className="text-muted-foreground">
        기준 {top.reference_price ? fmtPrice(top.reference_price) : '-'} · 손절 <span className="text-red-300">{fmtPrice(top.stop_price)}</span>
        {size && size.shares > 0 && <> · 권장 {size.shares.toLocaleString('ko-KR')}주</>}
      </span>
      {size && size.shares === 0 && (
        <span className="w-full text-[11px] text-amber-300/90">
          리스크 {(sizing.riskPct * 100).toFixed(1)}% 기준 0주 — 손절폭 {stopDistancePct(top)}%가 너무 넓어 규율상
          진입 불가입니다. 최우선이라도 살 수 없으면 건너뛰는 것이 원칙입니다.
        </span>
      )}
      <span className="ml-auto shrink-0 text-[11px] text-emerald-200/90">차트에서 확인 →</span>
    </button>
  )
}

/** 기준가 대비 손절까지의 거리(%) — 진입 불가 사유 표시에 사용 */
function stopDistancePct(sig: LabSignal): string {
  if (!sig.reference_price || sig.reference_price <= 0) return '-'
  return (((sig.reference_price - sig.stop_price) / sig.reference_price) * 100).toFixed(0)
}
