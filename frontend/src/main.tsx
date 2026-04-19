import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from './components/Layout'
import './index.css'

const DashboardPage = lazy(() => import('./pages/DashboardPage'))
const ChartPage = lazy(() => import('./pages/ChartPage'))
const PatternLibraryPage = lazy(() => import('./pages/PatternLibraryPage'))
const PatternPerformancePage = lazy(() => import('./pages/PatternPerformancePage'))
const ScreenerPage = lazy(() => import('./pages/ScreenerPage'))
const WatchlistPage = lazy(() => import('./pages/WatchlistPage'))
const SystemStatusPage = lazy(() => import('./pages/SystemStatusPage'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Suspense fallback={<div className="p-6 text-sm text-slate-400">불러오는 중...</div>}>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<DashboardPage />} />
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
  </StrictMode>,
)
