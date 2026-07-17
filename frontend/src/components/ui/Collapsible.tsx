import { useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { cn } from '@/lib/utils'

/** 접이식 참고 섹션 — 핵심 화면 아래에 두는 보조 정보용. 기본 접힘. */
export function Collapsible({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string
  summary?: string
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card className="space-y-3">
      <button onClick={() => setOpen(v => !v)} className="flex w-full items-center justify-between gap-3 text-left">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          {!open && summary && <p className="mt-0.5 text-xs text-muted-foreground">{summary}</p>}
        </div>
        <ChevronDown size={15} className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && children}
    </Card>
  )
}
