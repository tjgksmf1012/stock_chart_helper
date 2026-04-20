import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, Home, RefreshCw } from 'lucide-react'

interface AppErrorBoundaryProps {
  children: ReactNode
}

interface AppErrorBoundaryState {
  hasError: boolean
  message: string
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = {
    hasError: false,
    message: '',
  }

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return {
      hasError: true,
      message: error.message,
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('AppErrorBoundary caught an error', error, info)
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children
    }

    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
        <div className="w-full max-w-lg rounded-2xl border border-red-500/20 bg-card p-6 shadow-2xl">
          <div className="flex items-start gap-3">
            <div className="rounded-full bg-red-500/10 p-2 text-red-300">
              <AlertTriangle size={18} />
            </div>
            <div className="space-y-2">
              <h1 className="text-lg font-semibold">화면을 불러오는 중 문제가 발생했습니다</h1>
              <p className="text-sm leading-relaxed text-muted-foreground">
                배포 직후 캐시가 꼬였거나 일시적인 스크립트 오류일 수 있습니다. 새로고침으로 복구되는 경우가 많고, 계속 반복되면 운영
                상태 화면이나 브라우저 콘솔을 함께 확인하는 편이 좋습니다.
              </p>
              {this.state.message && (
                <div className="rounded-lg border border-border bg-background/70 px-3 py-2 font-mono text-xs text-muted-foreground">
                  {this.state.message}
                </div>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  onClick={() => window.location.reload()}
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                >
                  <RefreshCw size={14} />
                  새로고침
                </button>
                <button
                  onClick={() => {
                    window.location.href = '/'
                  }}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
                >
                  <Home size={14} />
                  홈으로 이동
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }
}
