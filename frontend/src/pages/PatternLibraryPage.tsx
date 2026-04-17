import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen, ChevronDown, ChevronUp } from 'lucide-react'

import { patternsApi } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { DIRECTION_LABELS } from '@/lib/utils'
import type { PatternLibraryEntry } from '@/types/api'

function PatternCard({ entry }: { entry: PatternLibraryEntry }) {
  const [expanded, setExpanded] = useState(false)

  const badgeVariant = entry.direction === 'bullish'
    ? 'bullish'
    : entry.direction === 'bearish'
      ? 'bearish'
      : 'neutral'

  return (
    <Card className="space-y-2">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
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

      {expanded && (
        <div className="space-y-3 border-t border-border pt-2">
          <Section title="구조 조건" items={entry.structure_conditions} color="text-blue-400" />
          <Section title="거래량 조건" items={entry.volume_conditions} color="text-purple-400" />
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
            <span className="mt-0.5 flex-shrink-0">•</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
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
            교과서형 패턴의 정의, 구조 조건, 확인 조건, 무효화 기준을 정리한 페이지입니다.
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
