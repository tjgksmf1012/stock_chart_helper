import { cn } from '@/lib/utils'

interface StatRowProps {
  label: string
  value: React.ReactNode
  className?: string
}

export function StatRow({ label, value, className }: StatRowProps) {
  return (
    <div className={cn('flex items-center justify-between text-xs', className)}>
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  )
}
