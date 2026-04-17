import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Loader2, Search } from 'lucide-react'

import { AnalysisPanel } from '@/components/chart/AnalysisPanel'
import { CandleChart } from '@/components/chart/CandleChart'
import { symbolsApi } from '@/lib/api'
import { useAppStore } from '@/store/app'

const TIMEFRAMES = [
  { value: '1d', label: '일봉' },
  { value: '60m', label: '60분' },
  { value: '15m', label: '15분' },
]

export default function ChartPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe } = useAppStore()
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ code: string; name: string; market: string }>>([])

  const barsQ = useQuery({
    queryKey: ['bars', symbol, selectedTimeframe],
    queryFn: () => symbolsApi.getBars(symbol!, selectedTimeframe, 365),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  const analysisQ = useQuery({
    queryKey: ['analysis', symbol, selectedTimeframe],
    queryFn: () => symbolsApi.getAnalysis(symbol!, selectedTimeframe),
    enabled: !!symbol,
    staleTime: 300_000,
  })

  const handleSearch = async (query: string) => {
    setSearchQuery(query)
    if (query.trim().length < 1) {
      setSearchResults([])
      return
    }

    const results = await symbolsApi.search(query)
    setSearchResults(results)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => nav('/')} className="text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft size={18} />
        </button>

        <div className="relative max-w-sm flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            className="w-full rounded-lg border border-border bg-card py-2 pl-8 pr-3 text-sm focus:border-primary/60 focus:outline-none"
            placeholder="종목 코드 또는 이름 검색"
            value={searchQuery}
            onChange={event => handleSearch(event.target.value)}
          />
          {searchResults.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-y-auto rounded-lg border border-border bg-card shadow-xl">
              {searchResults.map(result => (
                <button
                  key={result.code}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/50"
                  onClick={() => {
                    nav(`/chart/${result.code}`)
                    setSearchQuery('')
                    setSearchResults([])
                  }}
                >
                  <span className="font-mono text-xs text-muted-foreground">{result.code}</span>
                  <span>{result.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{result.market}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-1">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value as '1d' | '60m' | '15m')}
              className={`rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                selectedTimeframe === tf.value
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {analysisQ.data && (
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold">{analysisQ.data.symbol.name}</h1>
          <span className="font-mono text-sm text-muted-foreground">{symbol}</span>
          <span className="text-xs text-muted-foreground">{analysisQ.data.symbol.market}</span>
          {analysisQ.data.is_provisional && (
            <span className="rounded bg-orange-400/15 px-1.5 py-0.5 text-xs text-orange-400">잠정</span>
          )}
        </div>
      )}

      {!symbol ? (
        <div className="flex h-80 flex-col items-center justify-center gap-3 text-muted-foreground">
          <Search size={40} className="opacity-20" />
          <p className="text-sm">검색창에서 종목을 선택해 차트 분석을 시작하세요.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_300px]">
          <div>
            {barsQ.isLoading ? (
              <div className="flex h-96 items-center justify-center rounded-lg bg-card">
                <Loader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : barsQ.data && barsQ.data.length > 0 ? (
              <CandleChart bars={barsQ.data} analysis={analysisQ.data ?? null} height={480} />
            ) : (
              <div className="flex h-96 items-center justify-center rounded-lg bg-card text-sm text-muted-foreground">
                차트 데이터를 불러오지 못했습니다.
              </div>
            )}
          </div>

          <div>
            {analysisQ.isLoading ? (
              <div className="flex h-40 items-center justify-center">
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            ) : analysisQ.data ? (
              <AnalysisPanel analysis={analysisQ.data} />
            ) : (
              <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
                분석 결과를 불러오지 못했습니다.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
