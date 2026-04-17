import { cn } from '@/lib/utils'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'bullish' | 'bearish' | 'neutral' | 'warning' | 'muted'
  className?: string
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium',
      variant === 'bullish' && 'bg-green-400/15 text-green-400',
      variant === 'bearish' && 'bg-red-400/15 text-red-400',
      variant === 'neutral' && 'bg-blue-400/15 text-blue-400',
      variant === 'warning' && 'bg-orange-400/15 text-orange-400',
      variant === 'muted' && 'bg-white/5 text-gray-400',
      variant === 'default' && 'bg-primary/15 text-primary',
      className,
    )}>
      {children}
    </span>
  )
}
