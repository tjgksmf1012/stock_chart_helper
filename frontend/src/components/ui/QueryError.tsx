import { AlertCircle, RefreshCw } from 'lucide-react'

interface QueryErrorProps {
  message?: string
  onRetry?: () => void
  compact?: boolean
}

export function QueryError({ message = '데이터를 불러오지 못했습니다.', onRetry, compact = false }: QueryErrorProps) {
  if (compact) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
        <AlertCircle size={13} className="shrink-0 text-red-400" />
        <span>{message}</span>
        {onRetry && (
          <button
            onClick={onRetry}
            className="ml-auto flex items-center gap-1 rounded border border-border px-2 py-0.5 text-xs hover:text-foreground"
          >
            <RefreshCw size={11} />
            다시 시도
          </button>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-red-900/40 bg-red-950/20 px-4 py-6 text-center">
      <AlertCircle size={22} className="text-red-400" />
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <RefreshCw size={12} />
          다시 시도
        </button>
      )}
    </div>
  )
}
