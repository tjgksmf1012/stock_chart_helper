import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface WatchlistItem {
  code: string
  name: string
  market: string
  addedAt: string
}

interface AppStore {
  selectedSymbol: string | null
  selectedTimeframe: '1d' | '60m' | '15m'
  watchlist: WatchlistItem[]
  setSymbol: (code: string) => void
  setTimeframe: (tf: '1d' | '60m' | '15m') => void
  addToWatchlist: (item: Omit<WatchlistItem, 'addedAt'>) => void
  removeFromWatchlist: (code: string) => void
  isWatched: (code: string) => boolean
}

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      selectedSymbol: null,
      selectedTimeframe: '1d',
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
