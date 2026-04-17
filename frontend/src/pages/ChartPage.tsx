import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { symbolsApi } from '@/lib/api'
import { CandleChart } from '@/components/chart/CandleChart'
import { AnalysisPanel } from '@/components/chart/AnalysisPanel'
import { Loader2, ArrowLeft, Search } from 'lucide-react'
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

  const handleSearch = async (q: string) => {
    setSearchQuery(q)
    if (q.length < 1) { setSearchResults([]); return }
    const results = await symbolsApi.search(q)
    setSearchResults(results)
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => nav('/')} className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft size={18} />
        </button>

        {/* Symbol search */}
        <div className="relative flex-1 max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            className="w-full bg-card border border-border rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:border-primary/60"
            placeholder="종목 코드 또는 이름 검색..."
            value={searchQuery}
            onChange={e => handleSearch(e.target.value)}
          />
          {searchResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-xl z-50 max-h-48 overflow-y-auto">
              {searchResults.map(r => (
                <button
                  key={r.code}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted/50 transition-colors text-left"
                  onClick={() => { nav(`/chart/${r.code}`); setSearchQuery(''); setSearchResults([]) }}
                >
                  <span className="font-mono text-xs text-muted-foreground">{r.code}</span>
                  <span>{r.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{r.market}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Timeframe selector */}
        <div className="flex gap-1">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value as '1d' | '60m' | '15m')}
              className={`px-2.5 py-1.5 text-xs rounded-md transition-colors ${
                selectedTimeframe === tf.value
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card text-muted-foreground hover:text-foreground border border-border'
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {/* Symbol info */}
      {analysisQ.data && (
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold">{analysisQ.data.symbol.name}</h1>
          <span className="text-muted-foreground font-mono text-sm">{symbol}</span>
          <span className="text-xs text-muted-foreground">{analysisQ.data.symbol.market}</span>
          {analysisQ.data.is_provisional && (
            <span className="text-xs bg-orange-400/15 text-orange-400 px-1.5 py-0.5 rounded">잠정</span>
          )}
        </div>
      )}

      {!symbol ? (
        <div className="flex flex-col items-center justify-center h-80 text-muted-foreground gap-3">
          <Search size={40} className="opacity-20" />
          <p className="text-sm">위 검색창에서 종목을 선택하세요</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-4">
          {/* Chart */}
          <div>
            {barsQ.isLoading ? (
              <div className="flex items-center justify-center h-96 bg-card rounded-lg">
                <Loader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : (
              <CandleChart bars={barsQ.data ?? []} height={480} />
            )}
          </div>

          {/* Analysis */}
          <div>
            {analysisQ.isLoading ? (
              <div className="flex items-center justify-center h-40">
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            ) : analysisQ.data ? (
              <AnalysisPanel analysis={analysisQ.data} />
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
