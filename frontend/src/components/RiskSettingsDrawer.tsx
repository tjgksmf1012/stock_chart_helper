import { useState } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import { useAppStore } from '@/store/app'

interface RiskSettingsDrawerProps {
  open: boolean
  onClose: () => void
}

const ATR_MULTIPLIERS = ['1.5', '2.0', '2.5', '3.0']

export function RiskSettingsDrawer({ open, onClose }: RiskSettingsDrawerProps) {
  const { riskSettings, setRiskSettings } = useAppStore()

  const [accountSizeMan, setAccountSizeMan] = useState(
    riskSettings.accountSize > 0 ? String(Math.round(riskSettings.accountSize / 10000)) : '',
  )
  const [riskPct, setRiskPct] = useState(String(riskSettings.riskPerTrade * 100))
  const [atrMult, setAtrMult] = useState(String(riskSettings.atrMultiplier))

  const handleSave = () => {
    const accountSize = parseFloat(accountSizeMan) * 10000
    const riskPerTrade = parseFloat(riskPct) / 100
    const atrMultiplier = parseFloat(atrMult)

    if (!isNaN(accountSize) && !isNaN(riskPerTrade) && !isNaN(atrMultiplier)) {
      setRiskSettings({ accountSize, riskPerTrade, atrMultiplier })
    }
    onClose()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      {/* 배경 overlay */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 드로어 */}
      <Card className="relative z-10 w-full max-w-sm space-y-5 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold">리스크 설정</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        {/* 계좌 규모 */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">
            계좌 총액 (만원)
          </label>
          <input
            type="number"
            value={accountSizeMan}
            onChange={e => setAccountSizeMan(e.target.value)}
            placeholder="예: 5000 (5천만원)"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-primary"
          />
          {accountSizeMan && !isNaN(parseFloat(accountSizeMan)) && (
            <p className="text-xs text-muted-foreground">
              = {(parseFloat(accountSizeMan) / 10000).toFixed(2)}억원
            </p>
          )}
        </div>

        {/* 리스크 비율 */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">
            1회 최대 리스크 — <span className="text-foreground">{riskPct}%</span>
          </label>
          <input
            type="range"
            min="0.5"
            max="5"
            step="0.5"
            value={riskPct}
            onChange={e => setRiskPct(e.target.value)}
            className="w-full accent-primary"
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>0.5% (보수적)</span>
            <span>5% (공격적)</span>
          </div>
          {accountSizeMan && !isNaN(parseFloat(accountSizeMan)) && !isNaN(parseFloat(riskPct)) && (
            <p className="rounded border border-border bg-muted/20 px-2 py-1 text-xs text-muted-foreground">
              1회 최대 손실: {(parseFloat(accountSizeMan) * parseFloat(riskPct) / 100).toFixed(0)}만원
            </p>
          )}
        </div>

        {/* ATR 배수 */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-muted-foreground">ATR 손절 배수</label>
          <div className="grid grid-cols-4 gap-1.5">
            {ATR_MULTIPLIERS.map(v => (
              <button
                key={v}
                onClick={() => setAtrMult(v)}
                className={cn(
                  'rounded-lg border py-1.5 text-xs font-medium transition-colors',
                  atrMult === v
                    ? 'border-primary/50 bg-primary/10 text-foreground'
                    : 'border-border text-muted-foreground hover:border-border/80 hover:text-foreground',
                )}
              >
                ×{v}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            기본값 ×2.0. 변동성 큰 종목은 ×2.5~3.0 권장.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleSave}
            className="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
          >
            저장
          </button>
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            취소
          </button>
        </div>
      </Card>
    </div>
  )
}
