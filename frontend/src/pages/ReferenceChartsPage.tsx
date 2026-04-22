import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, Layers3 } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { timeframeLabel } from '@/lib/timeframes'
import { cn } from '@/lib/utils'
import type { Timeframe } from '@/types/api'

type ReferenceCaseKey =
  | 'double-bottom-breakout'
  | 'double-bottom-partial-breakout'
  | 'double-bottom-cloud-support'
  | 'cloud-support-relaunch'

interface ReferenceCase {
  key: ReferenceCaseKey
  title: string
  tag: string
  summary: string
  focus: string[]
  outcome: string
  levels: Array<{ label: string; y: number; style: 'solid' | 'dashed' | 'dotted' }>
  series: Array<{ color: string; points: string }>
}

const REFERENCE_CASES: ReferenceCase[] = [
  {
    key: 'double-bottom-breakout',
    title: '쌍바닥 돌파 상승',
    tag: 'breakout continuation',
    summary: 'neckline을 넘긴 뒤 짧은 눌림만 주고 이전 공급대를 돌파해 추세 전환이 이어지는 정석 케이스입니다.',
    focus: ['목선 돌파 뒤 종가 안착', '눌림 저점이 기준선 위에서 형성', '돌파 후 거래량이 크게 꺾이지 않음'],
    outcome: '비교 포인트: 돌파 확인 후 쉬는 자리가 얕고, 직전 고점과 전전 고점을 모두 정리합니다.',
    levels: [
      { label: '전전 고점', y: 18, style: 'dashed' },
      { label: '직전 고점', y: 28, style: 'dotted' },
      { label: 'neckline', y: 42, style: 'solid' },
      { label: '구름 상단', y: 56, style: 'dotted' },
    ],
    series: [
      { color: '#38bdf8', points: '6,78 18,74 30,68 44,40 56,42 68,32 82,20 94,12' },
      { color: '#34d399', points: '8,82 22,80 34,74 46,56 58,50 70,44 84,30 94,26' },
    ],
  },
  {
    key: 'double-bottom-partial-breakout',
    title: '직전 고점은 넘겼지만 전전 고점은 못 넘긴 케이스',
    tag: 'partial breakout',
    summary: '바로 앞 고점까지는 돌파에 성공하지만 더 위쪽 공급대를 정리하지 못하고 한 번 더 쉬거나 밀리는 유형입니다.',
    focus: ['1차 저항은 돌파하지만 2차 저항에서 거래량이 둔화', '돌파 후 눌림이 깊어짐', '구름 상단이나 기준선 재확인이 다시 필요'],
    outcome: '비교 포인트: 겉보기에는 breakout처럼 보이지만 상단 매물대를 전부 비우지 못하면 재정비 구간이 길어집니다.',
    levels: [
      { label: '전전 고점', y: 16, style: 'dashed' },
      { label: '직전 고점', y: 28, style: 'dotted' },
      { label: 'neckline', y: 42, style: 'solid' },
      { label: '구름 상단', y: 58, style: 'dotted' },
    ],
    series: [
      { color: '#60a5fa', points: '6,78 18,75 30,68 42,42 56,40 68,30 80,24 90,30 96,34' },
      { color: '#f59e0b', points: '8,82 22,79 34,72 46,60 58,54 70,48 82,44 94,40' },
    ],
  },
  {
    key: 'double-bottom-cloud-support',
    title: '구름 상단 터치 후 지지받는 재출발',
    tag: 'Ichimoku support',
    summary: '가격이 바로 228,500원 같은 저항을 못 넘고, 구름 상단까지 쉬었다가 지지 확인 후 다시 가는 흐름을 보는 레퍼런스입니다.',
    focus: ['구름 상단과 기준선이 비슷한 자리에서 겹침', '조정이 목선 아래로 깊게 무너지지 않음', '재출발 때 전고점 재공략 속도가 빨라짐'],
    outcome: '비교 포인트: 바로 가는 힘보다 어디서 쉬는지가 중요할 때 보는 그림입니다. 지지 확인 후에는 실패 리스크가 줄어듭니다.',
    levels: [
      { label: '상단 저항', y: 20, style: 'dashed' },
      { label: '직전 고점', y: 30, style: 'dotted' },
      { label: 'neckline', y: 44, style: 'solid' },
      { label: '구름 상단', y: 55, style: 'solid' },
    ],
    series: [
      { color: '#38bdf8', points: '6,76 18,74 30,66 42,42 54,34 64,36 74,54 86,46 96,24' },
      { color: '#34d399', points: '10,84 22,81 36,74 48,66 60,58 72,56 84,54 94,48' },
    ],
  },
]

export default function ReferenceChartsPage() {
  const nav = useNavigate()
  const [searchParams] = useSearchParams()
  const symbol = searchParams.get('symbol')
  const pattern = searchParams.get('pattern')
  const focusCase = searchParams.get('case') as ReferenceCaseKey | null
  const timeframeParam = (searchParams.get('timeframe') as Timeframe | null) ?? '1d'

  const cases = useMemo(() => {
    if (!focusCase) return REFERENCE_CASES
    const focused = REFERENCE_CASES.find(item => item.key === focusCase)
    if (!focused) return REFERENCE_CASES
    return [focused, ...REFERENCE_CASES.filter(item => item.key !== focusCase)]
  }, [focusCase])

  return (
    <div className="space-y-6">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_340px]">
        <Card className="space-y-4 border-primary/20 bg-[linear-gradient(180deg,rgba(37,99,235,0.1),rgba(15,23,42,0.18))]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[11px] font-medium text-primary">
                <Layers3 size={12} />
                새 창 비교용 레퍼런스
              </div>
              <div>
                <h1 className="text-2xl font-bold">패턴 비교 보드</h1>
                <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
                  현재 차트 옆에 띄워두고 neckline, 구름 상단, 전고점 처리 순서를 비교하기 좋게 만든 참고 화면입니다. 자동 추출된 과거 실차트 라이브러리라기보다, 실전에서 자주 나오는 흐름을 빠르게 대조하는 워크보드에 가깝습니다.
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
            <Badge variant="muted">{timeframeLabel(timeframeParam)}</Badge>
            {pattern && <Badge variant="neutral">{pattern}</Badge>}
            {focusCase && <Badge variant="bullish">선택 케이스 강조</Badge>}
          </div>
        </Card>

        <Card className="space-y-3">
          <div className="text-sm font-semibold">읽는 순서</div>
          <ChecklistItem title="1. 목선부터" body="쌍바닥이라면 W의 중앙 고점을 넘긴 뒤 종가가 유지되는지 먼저 봅니다." />
          <ChecklistItem title="2. 구름 상단" body="저항을 바로 못 넘기면 구름 상단까지 쉬는지, 기준선 위에서 지지받는지 확인합니다." />
          <ChecklistItem title="3. 전고점 계단" body="직전 고점만 넘겼는지, 전전 고점까지 정리했는지 따로 나눠 보시면 훨씬 선명해집니다." />
        </Card>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        {cases.map(referenceCase => (
          <Card
            key={referenceCase.key}
            className={cn(
              'space-y-4',
              focusCase === referenceCase.key && 'border-primary/40 shadow-[0_18px_44px_rgba(37,99,235,0.2)]',
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">{referenceCase.title}</div>
                <div className="mt-1 text-xs text-primary">{referenceCase.tag}</div>
              </div>
              <a
                href={symbol ? `/chart/${symbol}` : '/chart'}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                현재 차트
                <ExternalLink size={12} />
              </a>
            </div>

            <ReferenceMiniChart referenceCase={referenceCase} />

            <p className="text-sm leading-relaxed text-muted-foreground">{referenceCase.summary}</p>

            <div className="space-y-2">
              {referenceCase.focus.map(item => (
                <div key={item} className="rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
                  {item}
                </div>
              ))}
            </div>

            <div className="rounded-lg border border-primary/15 bg-primary/5 px-3 py-3 text-xs leading-relaxed text-muted-foreground">
              {referenceCase.outcome}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

function ReferenceMiniChart({ referenceCase }: { referenceCase: ReferenceCase }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background/70 p-3">
      <svg viewBox="0 0 100 100" className="h-56 w-full">
        <defs>
          <linearGradient id={`cloud-${referenceCase.key}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(52,211,153,0.22)" />
            <stop offset="100%" stopColor="rgba(52,211,153,0.04)" />
          </linearGradient>
        </defs>

        <rect x="0" y="0" width="100" height="100" fill="transparent" />

        <path d="M 14 68 C 26 62, 34 60, 46 54 S 68 48, 86 44 L 86 62 C 72 66, 54 70, 36 72 S 22 74, 14 74 Z" fill={`url(#cloud-${referenceCase.key})`} />

        {referenceCase.levels.map(level => (
          <g key={level.label}>
            <line
              x1="4"
              y1={level.y}
              x2="96"
              y2={level.y}
              stroke={level.label === 'neckline' ? '#f59e0b' : '#334155'}
              strokeDasharray={level.style === 'solid' ? undefined : level.style === 'dashed' ? '3 2' : '1.5 2.5'}
              strokeWidth="1"
            />
            <text x="5" y={Math.max(8, level.y - 2)} fill="#94a3b8" fontSize="4">
              {level.label}
            </text>
          </g>
        ))}

        {referenceCase.series.map(series => (
          <polyline
            key={`${referenceCase.key}-${series.color}`}
            fill="none"
            stroke={series.color}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            points={series.points}
          />
        ))}
      </svg>
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
