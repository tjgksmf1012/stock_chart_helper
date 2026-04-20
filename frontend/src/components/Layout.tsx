import { NavLink, Outlet } from 'react-router-dom'
import { BarChart2, BookOpen, LayoutDashboard, ServerCog, SlidersHorizontal, Star, TrendingUp } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app'

const NAV_ITEMS = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/chart', label: '차트 분석', icon: BarChart2, end: false },
  { to: '/watchlist', label: '관심종목', icon: Star, end: true },
  { to: '/library', label: '패턴 라이브러리', icon: BookOpen, end: true },
  { to: '/reports/patterns', label: '패턴 성과', icon: TrendingUp, end: true },
  { to: '/screener', label: '스크리너', icon: SlidersHorizontal, end: true },
  { to: '/system', label: '운영 상태', icon: ServerCog, end: true },
]

export function Layout() {
  const { watchlist } = useAppStore()

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-12 max-w-screen-2xl items-center justify-between px-4">
          <div className="flex items-center gap-2">
            <BarChart2 size={18} className="text-primary" />
            <span className="text-sm font-bold tracking-tight">Stock Chart Helper</span>
          </div>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'relative flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-colors',
                    isActive
                      ? 'bg-primary/15 text-primary'
                      : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
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

      <main className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-border px-4 py-3 text-center text-xs text-muted-foreground">
        Stock Chart Helper는 차트 분석을 돕는 보조 도구이며, 투자 권유 서비스가 아닙니다.
      </footer>
    </div>
  )
}
