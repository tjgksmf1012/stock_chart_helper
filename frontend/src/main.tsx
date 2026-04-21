import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { AppErrorBoundary } from './components/AppErrorBoundary'
import { Layout } from './components/Layout'
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
const AiRecommendationsPage = lazyWithRetry(() => import('./pages/AiRecommendationsPage'), 'AiRecommendationsPage')
const ChartPage = lazyWithRetry(() => import('./pages/ChartPage'), 'ChartPage')
const PatternLibraryPage = lazyWithRetry(() => import('./pages/PatternLibraryPage'), 'PatternLibraryPage')
const PatternPerformancePage = lazyWithRetry(() => import('./pages/PatternPerformancePage'), 'PatternPerformancePage')
const ScreenerPage = lazyWithRetry(() => import('./pages/ScreenerPage'), 'ScreenerPage')
const WatchlistPage = lazyWithRetry(() => import('./pages/WatchlistPage'), 'WatchlistPage')
const SystemStatusPage = lazyWithRetry(() => import('./pages/SystemStatusPage'), 'SystemStatusPage')

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
                <Route path="ai" element={<AiRecommendationsPage />} />
                <Route path="chart" element={<ChartPage />} />
                <Route path="chart/:symbol" element={<ChartPage />} />
                <Route path="watchlist" element={<WatchlistPage />} />
                <Route path="library" element={<PatternLibraryPage />} />
                <Route path="reports/patterns" element={<PatternPerformancePage />} />
                <Route path="screener" element={<ScreenerPage />} />
                <Route path="system" element={<SystemStatusPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </QueryClientProvider>
    </AppErrorBoundary>
  </StrictMode>,
)
