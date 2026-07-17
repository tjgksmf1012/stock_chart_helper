import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { BarChart2, CalendarCheck, LineChart, NotebookPen, ServerCog, Star } from 'lucide-react'

import { cn } from '@/lib/utils'
import { useAppStore } from '@/store/app'

// 여정 3탭 — 오늘(무엇을 할까) / 분석(이 종목 파고들기) / 기록(내 성과와 증거)
const TABS = [
  { to: '/', label: '오늘', icon: CalendarCheck, match: (p: string) => p === '/' },
  {
    to: '/chart',
    label: '분석',
    icon: LineChart,
    match: (p: string) => ['/chart', '/screener', '/watchlist', '/library', '/reference-charts'].some(x => p.startsWith(x)),
  },
  {
    to: '/journal',
    label: '기록',
    icon: NotebookPen,
    match: (p: string) => ['/journal', '/reports', '/lab'].some(x => p.startsWith(x)),
  },
]

export function Layout() {
  const { watchlist, syncFromServer } = useAppStore()
  const { pathname } = useLocation()

  useEffect(() => {
    syncFromServer().catch(() => {})
  }, [syncFromServer])

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/92 backdrop-blur-xl">
        <div className="mx-auto flex max-w-screen-2xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
              <BarChart2 size={18} />
            </div>
            <div className="hidden sm:block">
              <div className="text-sm font-bold tracking-tight">Stock Chart Helper</div>
              <div className="text-[11px] text-muted-foreground">검증된 신호 · 절제된 진입</div>
            </div>
          </div>

          <nav className="flex items-center gap-1">
            {TABS.map(tab => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={cn(
                  'relative flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-3.5 py-2 text-sm transition-colors',
                  tab.match(pathname)
                    ? 'border border-primary/20 bg-primary/12 font-medium text-primary shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]'
                    : 'border border-transparent text-muted-foreground hover:border-border hover:bg-muted/40 hover:text-foreground',
                )}
              >
                <tab.icon size={14} />
                {tab.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-1">
            <NavLink
              to="/watchlist"
              title="관심종목"
              className={({ isActive }) =>
                cn(
                  'relative flex h-9 items-center gap-1 rounded-lg px-2.5 transition-colors',
                  isActive ? 'bg-primary/12 text-primary' : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground',
                )
              }
            >
              <Star size={15} />
              {watchlist.length > 0 && (
                <span className="rounded-full bg-yellow-400/20 px-1 py-0.5 text-[10px] font-medium leading-none text-yellow-400">
                  {watchlist.length}
                </span>
              )}
            </NavLink>
            <NavLink
              to="/system"
              title="시스템 상태"
              className={({ isActive }) =>
                cn(
                  'flex h-9 items-center rounded-lg px-2.5 transition-colors',
                  isActive ? 'bg-primary/12 text-primary' : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground',
                )
              }
            >
              <ServerCog size={15} />
            </NavLink>
          </div>
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
