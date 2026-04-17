import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, BarChart2, BookOpen, SlidersHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/chart', label: '차트 분석', icon: BarChart2, end: false },
  { to: '/library', label: '패턴 라이브러리', icon: BookOpen, end: true },
  { to: '/screener', label: '스크리너', icon: SlidersHorizontal, end: true },
]

export function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        <div className="max-w-screen-2xl mx-auto px-4 h-12 flex items-center justify-between">
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
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md transition-colors',
                  isActive
                    ? 'bg-primary/15 text-primary'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
                )}
              >
                <item.icon size={13} />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-border px-4 py-3 text-center text-xs text-muted-foreground">
        Stock Chart Helper — 본 도구는 차트 분석 참고용이며 투자 권유가 아닙니다.
      </footer>
    </div>
  )
}
