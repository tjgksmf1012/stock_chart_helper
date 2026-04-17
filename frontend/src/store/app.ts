import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Timeframe } from '@/types/api'
import { DEFAULT_TIMEFRAME } from '@/lib/timeframes'

interface WatchlistItem {
  code: string
  name: string
  market: string
  addedAt: string
}

interface AppStore {
  selectedSymbol: string | null
  selectedTimeframe: Timeframe
  watchlist: WatchlistItem[]
  setSymbol: (code: string) => void
  setTimeframe: (tf: Timeframe) => void
  addToWatchlist: (item: Omit<WatchlistItem, 'addedAt'>) => void
  removeFromWatchlist: (code: string) => void
  isWatched: (code: string) => boolean
}

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      selectedSymbol: null,
      selectedTimeframe: DEFAULT_TIMEFRAME,
      watchlist: [],

      setSymbol: (code) => set({ selectedSymbol: code }),
      setTimeframe: (tf) => set({ selectedTimeframe: tf }),

      addToWatchlist: (item) => {
        const { watchlist } = get()
        if (watchlist.some(w => w.code === item.code)) return
        set({ watchlist: [...watchlist, { ...item, addedAt: new Date().toISOString() }] })
      },

      removeFromWatchlist: (code) => {
        set({ watchlist: get().watchlist.filter(w => w.code !== code) })
      },

      isWatched: (code) => get().watchlist.some(w => w.code === code),
    }),
    {
      name: 'sch-app-store',
      partialize: (state) => ({ watchlist: state.watchlist, selectedTimeframe: state.selectedTimeframe }),
    }
  )
)
