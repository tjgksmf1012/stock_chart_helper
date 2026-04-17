import { NavLink, Outlet } from 'react-router-dom'
import { BarChart2, BookOpen, LayoutDashboard, SlidersHorizontal } from 'lucide-react'

import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/chart', label: '차트 분석', icon: BarChart2, end: false },
  { to: '/library', label: '패턴 라이브러리', icon: BookOpen, end: true },
  { to: '/screener', label: '스크리너', icon: SlidersHorizontal, end: true },
]

export function Layout() {
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
                className={({ isActive }) => cn(
                  'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs transition-colors',
                  isActive
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
                )}
              >
                <item.icon size={13} />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-border px-4 py-3 text-center text-xs text-muted-foreground">
        Stock Chart Helper는 차트 분석 보조 도구이며 투자 권유를 위한 서비스가 아닙니다.
      </footer>
    </div>
  )
}
