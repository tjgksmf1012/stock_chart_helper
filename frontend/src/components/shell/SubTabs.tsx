import { NavLink, Outlet } from 'react-router-dom'

import { cn } from '@/lib/utils'

export interface SubTab {
  to: string
  label: string
  end?: boolean
}

/** 분석/기록 탭 공용 서브탭 셸 — 기존 라우트를 그대로 Outlet으로 렌더한다. */
export function SubTabs({ tabs }: { tabs: SubTab[] }) {
  return (
    <div className="space-y-5">
      <nav className="flex items-center gap-1 overflow-x-auto rounded-lg border border-border bg-card/60 p-1">
        {tabs.map(tab => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end ?? true}
            className={({ isActive }) =>
              cn(
                'whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                isActive ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}
