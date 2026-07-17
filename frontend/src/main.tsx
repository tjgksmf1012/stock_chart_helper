import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { AppErrorBoundary } from './components/AppErrorBoundary'
import { Layout } from './components/Layout'
import { SubTabs } from './components/shell/SubTabs'
import './index.css'

function lazyWithRetry<T extends { default: React.ComponentType<any> }>(
  importer: () => Promise<T>,
  name: string,
) {
  return lazy(async () => {
    try {
      return await importer()
    } catch (error) {
      console.error(`Failed to load route chunk: ${name}`, error)
      await new Promise(resolve => window.setTimeout(resolve, 700))
      return importer()
    }
  })
}

const DashboardPage = lazyWithRetry(() => import('./pages/DashboardPage'), 'DashboardPage')
const ChartPage = lazyWithRetry(() => import('./pages/ChartPage'), 'ChartPage')
const PatternLibraryPage = lazyWithRetry(() => import('./pages/PatternLibraryPage'), 'PatternLibraryPage')
const PatternPerformancePage = lazyWithRetry(() => import('./pages/PatternPerformancePage'), 'PatternPerformancePage')
const ReferenceChartsPage = lazyWithRetry(() => import('./pages/ReferenceChartsPage'), 'ReferenceChartsPage')
const ScreenerPage = lazyWithRetry(() => import('./pages/ScreenerPage'), 'ScreenerPage')
const WatchlistPage = lazyWithRetry(() => import('./pages/WatchlistPage'), 'WatchlistPage')
const SystemStatusPage = lazyWithRetry(() => import('./pages/SystemStatusPage'), 'SystemStatusPage')
const JournalRecordsPage = lazyWithRetry(() => import('./pages/journal/JournalRecordsPage'), 'JournalRecordsPage')
const JournalPaperPage = lazyWithRetry(() => import('./pages/journal/JournalPaperPage'), 'JournalPaperPage')
const JournalStrategiesPage = lazyWithRetry(() => import('./pages/journal/JournalStrategiesPage'), 'JournalStrategiesPage')

const ANALYSIS_TABS = [
  { to: '/chart', label: '차트', end: false },
  { to: '/screener', label: '종목 필터' },
  { to: '/watchlist', label: '관심종목' },
  { to: '/library', label: '패턴 사전' },
]

const JOURNAL_TABS = [
  { to: '/journal', label: '내 기록' },
  { to: '/journal/paper', label: '실측 (종이매매)' },
  { to: '/journal/strategies', label: '전략 검증' },
  { to: '/reports/patterns', label: '패턴 적중률' },
]

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Suspense
            fallback={
              <div className="flex min-h-screen items-center justify-center bg-background px-4">
                <div className="rounded-2xl border border-border bg-card px-5 py-4 text-center shadow-xl">
                  <div className="text-sm font-medium text-foreground">불러오는 중...</div>
                  <div className="mt-1 text-xs text-muted-foreground">화면과 데이터를 준비하고 있습니다.</div>
                </div>
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<Layout />}>
                <Route index element={<DashboardPage />} />
                {/* 구 라우트 — 오늘의 추천은 오늘 탭에 흡수, 실험실은 기록>전략 검증으로 */}
                <Route path="ai" element={<Navigate to="/" replace />} />
                <Route path="lab" element={<Navigate to="/journal/strategies" replace />} />

                <Route element={<SubTabs tabs={ANALYSIS_TABS} />}>
                  <Route path="chart" element={<ChartPage />} />
                  <Route path="chart/:symbol" element={<ChartPage />} />
                  <Route path="screener" element={<ScreenerPage />} />
                  <Route path="watchlist" element={<WatchlistPage />} />
                  <Route path="library" element={<PatternLibraryPage />} />
                </Route>

                <Route element={<SubTabs tabs={JOURNAL_TABS} />}>
                  <Route path="journal" element={<JournalRecordsPage />} />
                  <Route path="journal/paper" element={<JournalPaperPage />} />
                  <Route path="journal/strategies" element={<JournalStrategiesPage />} />
                  <Route path="reports/patterns" element={<PatternPerformancePage />} />
                </Route>

                <Route path="reference-charts" element={<ReferenceChartsPage />} />
                <Route path="system" element={<SystemStatusPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </QueryClientProvider>
    </AppErrorBoundary>
  </StrictMode>,
)
