import { useState } from 'react'
import { Calculator, Settings } from 'lucide-react'
import { cn, fmtPrice } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import { useAppStore } from '@/store/app'
import type { AnalysisResult, OHLCVBar } from '@/types/api'
import { calcATR, calcAtrStop, calcPosition } from '@/lib/atr'

interface PositionSizerCardProps {
  analysis: AnalysisResult
  bars: OHLCVBar[]
  currentPrice?: number
  onOpenSettings: () => void
}

function ResultRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded border border-border bg-background/50 px-2.5 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-sm font-bold', warn ? 'text-amber-400' : 'text-foreground')}>
        {value}
        {warn && <span className="ml-1 text-xs">⚠️</span>}
      </div>
    </div>
  )
}

interface StopButtonProps {
  label: string
  subLabel: string
  active: boolean
  disabled: boolean
  onClick: () => void
}

function StopButton({ label, subLabel, active, disabled, onClick }: StopButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex-1 rounded-lg border px-2 py-2 text-left text-xs transition-colors',
        active
          ? 'border-primary/40 bg-primary/10 text-foreground'
          : 'border-border bg-background/50 text-muted-foreground hover:text-foreground',
        disabled && 'cursor-not-allowed opacity-40',
      )}
    >
      <div className="font-semibold">{label}</div>
      {subLabel && (
        <div className="mt-0.5 text-muted-foreground">{subLabel}</div>
      )}
    </button>
  )
}

export function PositionSizerCard({ analysis, bars, currentPrice, onOpenSettings }: PositionSizerCardProps) {
  const { riskSettings } = useAppStore()
  const { accountSize, riskPerTrade, atrMultiplier, preferAtrStop } = riskSettings

  const bestPattern = analysis.patterns[0] ?? null
  const price = currentPrice ?? 0
  const bullish = analysis.p_up >= analysis.p_down
  const atr = calcATR(bars)

  const atrStopInfo = price && atr ? calcAtrStop(price, atr, atrMultiplier, bullish) : null
  const patternStopPrice = bestPattern?.invalidation_level ?? null
  const patternStopInfo = patternStopPrice && price
    ? {
        price: patternStopPrice,
        distancePct: (Math.abs(price - patternStopPrice) / price) * 100,
        label: '패턴 기준',
      }
    : null

  // 초기 선택: preferAtrStop이면 ATR, 아니면 패턴. 없으면 있는 쪽으로
  const defaultUseAtr = preferAtrStop
    ? atrStopInfo !== null
    : patternStopInfo === null && atrStopInfo !== null

  const [useAtr, setUseAtr] = useState(defaultUseAtr)

  const activeStop = useAtr ? atrStopInfo : patternStopInfo
  const targetPrice = bestPattern?.target_level ?? null

  const calc = accountSize && price && activeStop
    ? calcPosition(accountSize, riskPerTrade, price, activeStop.price, targetPrice)
    : null

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calculator size={13} className="text-primary" />
          <span className="text-sm font-semibold">포지션 계산기</span>
        </div>
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <Settings size={11} />
          리스크 설정
        </button>
      </div>

      {!accountSize ? (
        <div className="rounded-lg border border-dashed border-border bg-muted/20 px-3 py-4 text-center">
          <p className="text-xs text-muted-foreground">
            ⚙️ <button onClick={onOpenSettings} className="underline hover:text-foreground">리스크 설정</button>에서
            계좌 규모를 입력하면 포지션 계산이 됩니다.
          </p>
        </div>
      ) : (
        <>
          {/* 손절 기준 선택 */}
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">손절 기준 선택</p>
            <div className="flex gap-2">
              <StopButton
                label={`패턴 기준`}
                subLabel={patternStopInfo
                  ? `${fmtPrice(patternStopInfo.price)} (−${patternStopInfo.distancePct.toFixed(1)}%)`
                  : '패턴 손절가 없음'}
                active={!useAtr}
                disabled={!patternStopInfo}
                onClick={() => setUseAtr(false)}
              />
              <StopButton
                label={`ATR×${atrMultiplier}`}
                subLabel={atrStopInfo
                  ? `${fmtPrice(atrStopInfo.price)} (−${atrStopInfo.distancePct.toFixed(1)}%)`
                  : 'ATR 계산 불가'}
                active={useAtr}
                disabled={!atrStopInfo}
                onClick={() => setUseAtr(true)}
              />
            </div>
          </div>

          {/* 계산 결과 */}
          {calc ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <ResultRow
                  label="최대 손실"
                  value={`${(calc.maxLossKrw / 10000).toFixed(0)}만원`}
                />
                <ResultRow
                  label="매수 수량"
                  value={`${calc.shares.toLocaleString()}주`}
                />
                <ResultRow
                  label="투자 금액"
                  value={`${(calc.positionValue / 10000).toFixed(0)}만원`}
                />
                <ResultRow
                  label="계좌 비중"
                  value={`${calc.positionPct.toFixed(1)}%`}
                  warn={calc.positionPct > 20}
                />
              </div>

              {calc.rewardRisk > 0 && (
                <div className={cn(
                  'rounded-lg border p-2 text-xs font-medium',
                  calc.rewardRiskOk
                    ? 'border-emerald-400/20 bg-emerald-400/6 text-emerald-400'
                    : 'border-amber-400/20 bg-amber-400/6 text-amber-400',
                )}>
                  리스크 보상비 1 : {calc.rewardRisk.toFixed(1)}
                  {calc.rewardRiskOk
                    ? '  ✅ 적정 (기준 1:2 이상)'
                    : '  ⚠️ 낮음 (기준 1:2 이상)'}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              {!price ? '현재가 정보가 없습니다.' : '손절 기준을 선택하면 계산이 시작됩니다.'}
            </p>
          )}

          <p className="text-xs text-muted-foreground">
            계좌 {(accountSize / 10000).toFixed(0)}만원 · 리스크 {(riskPerTrade * 100).toFixed(1)}% 기준
          </p>
        </>
      )}
    </Card>
  )
}
