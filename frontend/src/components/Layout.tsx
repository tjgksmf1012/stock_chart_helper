import { useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { BarChart2, BookOpen, LayoutDashboard, ServerCog, SlidersHorizontal, Sparkles, Star, TrendingUp } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app'

const NAV_ITEMS = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/ai', label: 'AI 추천', icon: Sparkles, end: true },
  { to: '/chart', label: '차트 분석', icon: BarChart2, end: false },
  { to: '/watchlist', label: '관심종목', icon: Star, end: true },
  { to: '/library', label: '패턴 라이브러리', icon: BookOpen, end: true },
  { to: '/reports/patterns', label: '패턴 성과', icon: TrendingUp, end: true },
  { to: '/screener', label: '스크리너', icon: SlidersHorizontal, end: true },
  { to: '/system', label: '운영 상태', icon: ServerCog, end: true },
]

export function Layout() {
  const { watchlist, syncFromServer } = useAppStore()

  useEffect(() => {
    syncFromServer().catch(() => {})
  }, [syncFromServer])

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/92 backdrop-blur-xl">
        <div className="mx-auto flex max-w-screen-2xl flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
              <BarChart2 size={18} />
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight">Stock Chart Helper</div>
              <div className="text-[11px] text-muted-foreground">KRX pattern desk for fast review and disciplined entries</div>
            </div>
          </div>

          <nav className="flex items-center gap-1 overflow-x-auto pb-1 md:pb-0">
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'relative flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-2 text-xs transition-colors',
                    isActive
                      ? 'border border-primary/20 bg-primary/12 text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]'
                      : 'border border-transparent text-muted-foreground hover:border-border hover:bg-muted/40 hover:text-foreground',
                  )
                }
              >
                <item.icon size={13} />
                {item.label}
                {item.to === '/watchlist' && watchlist.length > 0 && (
                  <span className="ml-0.5 rounded-full bg-yellow-400/20 px-1 py-0.5 text-[10px] font-medium leading-none text-yellow-400">
                    {watchlist.length}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-6 lg:py-8">
        <Outlet />
      </main>

      <footer className="border-t border-border/80 px-4 py-4 text-center text-xs text-muted-foreground">
        Stock Chart Helper는 기술적 분석 보조 도구이며 투자 권유 서비스가 아닙니다.
      </footer>
    </div>
  )
}
