import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, ChevronDown, ChevronUp } from 'lucide-react'
import { Link } from 'react-router-dom'

import { patternsApi } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { DIRECTION_LABELS } from '@/lib/utils'
import type { PatternLibraryEntry } from '@/types/api'

function PatternCard({ entry }: { entry: PatternLibraryEntry }) {
  const [expanded, setExpanded] = useState(false)
  const badgeVariant = entry.direction === 'bullish' ? 'bullish' : entry.direction === 'bearish' ? 'bearish' : 'neutral'

  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{entry.name_kr}</span>
            <Badge variant={badgeVariant}>{DIRECTION_LABELS[entry.direction]}</Badge>
            <Badge variant="muted">{entry.grade}급</Badge>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{entry.description}</p>
        </div>
        <button
          onClick={() => setExpanded(value => !value)}
          className="ml-2 flex-shrink-0 text-muted-foreground transition-colors hover:text-foreground"
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      <PatternPreview patternType={entry.pattern_type} />

      {expanded && (
        <div className="space-y-3 border-t border-border pt-3">
          <Section title="구조 조건" items={entry.structure_conditions} color="text-blue-400" />
          <Section title="거래량 조건" items={entry.volume_conditions} color="text-violet-400" />
          <Section title="확인 조건" items={entry.confirmation_conditions} color="text-green-400" />
          <Section title="무효화 조건" items={entry.invalidation_conditions} color="text-red-400" />
          <Section title="주의사항" items={entry.cautions} color="text-yellow-400" />
        </div>
      )}
    </Card>
  )
}

function Section({ title, items, color }: { title: string; items: string[]; color: string }) {
  if (!items.length) return null

  return (
    <div>
      <div className={`mb-1 text-xs font-semibold ${color}`}>{title}</div>
      <ul className="space-y-0.5">
        {items.map((item, index) => (
          <li key={index} className="flex gap-1.5 text-xs text-muted-foreground">
            <span className="mt-0.5 flex-shrink-0">-</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function PatternPreview({ patternType }: { patternType: string }) {
  const points = previewPoints(patternType)

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-background/70 p-3">
      <svg viewBox="0 0 160 72" className="h-20 w-full">
        <defs>
          <linearGradient id="patternLine" x1="0%" x2="100%" y1="0%" y2="0%">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="100%" stopColor="#34d399" />
          </linearGradient>
        </defs>
        <rect x="0" y="0" width="160" height="72" rx="10" fill="rgba(15,23,42,0.2)" />
        {[16, 36, 56].map(y => (
          <line key={y} x1="0" y1={y} x2="160" y2={y} stroke="rgba(148,163,184,0.15)" strokeWidth="1" />
        ))}
        <polyline fill="none" stroke="url(#patternLine)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" points={points} />
      </svg>
    </div>
  )
}

function previewPoints(patternType: string): string {
  const map: Record<string, string> = {
    double_bottom: '6,20 28,54 52,18 78,52 104,20 132,18 154,10',
    double_top: '6,54 28,18 52,50 78,16 104,48 132,50 154,58',
    head_and_shoulders: '6,54 24,26 42,46 68,12 94,44 118,26 138,42 154,56',
    inverse_head_and_shoulders: '6,18 24,46 42,26 68,60 94,28 118,46 138,30 154,16',
    ascending_triangle: '6,54 34,44 60,36 86,28 112,20 136,20 154,10',
    descending_triangle: '6,18 34,28 60,36 86,44 112,52 136,52 154,60',
    symmetric_triangle: '6,22 28,30 50,24 72,36 94,30 116,38 138,34 154,28',
    rectangle: '6,46 30,24 54,46 78,24 102,46 126,24 154,46',
    vcp: '6,18 30,44 56,22 82,40 108,24 132,34 154,12',
  }

  return map[patternType] ?? '6,40 26,30 46,42 66,28 86,38 106,24 126,32 154,18'
}

export default function PatternLibraryPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['patterns', 'library'],
    queryFn: patternsApi.library,
    staleTime: Infinity,
  })

  const [filter, setFilter] = useState<'all' | 'bullish' | 'bearish' | 'neutral'>('all')
  const filtered = data?.filter(pattern => filter === 'all' || pattern.direction === filter) ?? []

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <BookOpen size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">차트 패턴 라이브러리</h1>
          <p className="text-xs text-muted-foreground">
            교과서형 패턴의 정의, 구조 조건, 확인 조건, 무효화 기준을 한 번에 정리해 둔 참고 화면입니다.
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        {(['all', 'bullish', 'bearish', 'neutral'] as const).map(value => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
              filter === value
                ? 'bg-primary text-primary-foreground'
                : 'border border-border bg-card text-muted-foreground hover:text-foreground'
            }`}
          >
            {value === 'all' ? '전체' : DIRECTION_LABELS[value]}
          </button>
        ))}
        <Link
          to="/reports/patterns"
          className="rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          패턴 성과 보기
        </Link>
      </div>

      {isLoading ? (
        <div className="py-10 text-center text-muted-foreground">불러오는 중...</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map(entry => <PatternCard key={entry.pattern_type} entry={entry} />)}
        </div>
      )}
    </div>
  )
}
