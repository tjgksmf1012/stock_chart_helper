import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { patternsApi } from '@/lib/api'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { PATTERN_NAMES } from '@/lib/utils'
import type { PatternLibraryEntry } from '@/types/api'
import { ChevronDown, ChevronUp, BookOpen } from 'lucide-react'

function PatternCard({ entry }: { entry: PatternLibraryEntry }) {
  const [expanded, setExpanded] = useState(false)

  const dirBadge = entry.direction === 'bullish' ? 'bullish'
    : entry.direction === 'bearish' ? 'bearish' : 'neutral'

  return (
    <Card className="space-y-2">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm">{entry.name_kr}</span>
            <Badge variant={dirBadge}>
              {entry.direction === 'bullish' ? '상승' : entry.direction === 'bearish' ? '하락' : '중립'}
            </Badge>
            <Badge variant="muted">{entry.grade}급</Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{entry.description}</p>
        </div>
        <button
          onClick={() => setExpanded(e => !e)}
          className="text-muted-foreground hover:text-foreground transition-colors ml-2 flex-shrink-0"
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {expanded && (
        <div className="space-y-3 pt-2 border-t border-border">
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
      <div className={`text-xs font-semibold mb-1 ${color}`}>{title}</div>
      <ul className="space-y-0.5">
        {items.map((item, i) => (
          <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
            <span className="mt-0.5 flex-shrink-0">·</span>
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

  const filtered = data?.filter(p => filter === 'all' || p.direction === filter) ?? []

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <BookOpen size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">차트 교과서 라이브러리</h1>
          <p className="text-xs text-muted-foreground">교과서형 패턴 정의 · 구조 조건 · 무효화 기준</p>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {(['all', 'bullish', 'bearish', 'neutral'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
              filter === f ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground border border-border'
            }`}
          >
            {f === 'all' ? '전체' : f === 'bullish' ? '상승' : f === 'bearish' ? '하락' : '중립'}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-center text-muted-foreground py-10">불러오는 중...</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {filtered.map(entry => <PatternCard key={entry.pattern_type} entry={entry} />)}
        </div>
      )}
    </div>
  )
}
