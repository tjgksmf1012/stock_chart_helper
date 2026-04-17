import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from './components/Layout'
import DashboardPage from './pages/DashboardPage'
import ChartPage from './pages/ChartPage'
import PatternLibraryPage from './pages/PatternLibraryPage'
import ScreenerPage from './pages/ScreenerPage'
import WatchlistPage from './pages/WatchlistPage'
import './index.css'

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
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="chart" element={<ChartPage />} />
            <Route path="chart/:symbol" element={<ChartPage />} />
            <Route path="watchlist" element={<WatchlistPage />} />
            <Route path="library" element={<PatternLibraryPage />} />
            <Route path="screener" element={<ScreenerPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
