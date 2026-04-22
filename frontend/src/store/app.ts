import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { Timeframe, WatchlistItem } from '@/types/api'
import { DEFAULT_TIMEFRAME, normalizeDisplayTimeframe } from '@/lib/timeframes'
import { watchlistApi } from '@/lib/api'

interface AppStore {
  selectedSymbol: string | null
  selectedTimeframe: Timeframe
  watchlist: WatchlistItem[]
  setSymbol: (code: string) => void
  setTimeframe: (tf: Timeframe) => void
  addToWatchlist: (item: { code: string; name: string; market: string }) => void
  removeFromWatchlist: (code: string) => void
  isWatched: (code: string) => boolean
  /** Pull the server-side watchlist and merge into local state. */
  syncFromServer: () => Promise<void>
}

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      selectedSymbol: null,
      selectedTimeframe: DEFAULT_TIMEFRAME,
      watchlist: [],

      setSymbol: code => set({ selectedSymbol: code }),
      setTimeframe: tf => set({ selectedTimeframe: normalizeDisplayTimeframe(tf) }),

      addToWatchlist: item => {
        const { watchlist } = get()
        if (watchlist.some(w => w.code === item.code)) return
        const updated = [...watchlist, { ...item, addedAt: new Date().toISOString() }]
        set({ watchlist: updated })
        // Persist to server (fire-and-forget; localStorage is the source-of-truth)
        watchlistApi.sync(updated).catch(() => {})
      },

      removeFromWatchlist: code => {
        const updated = get().watchlist.filter(w => w.code !== code)
        set({ watchlist: updated })
        watchlistApi.sync(updated).catch(() => {})
      },

      isWatched: code => get().watchlist.some(w => w.code === code),

      syncFromServer: async () => {
        try {
          const serverItems = await watchlistApi.get()
          if (!serverItems?.length) return
          const { watchlist } = get()
          // Merge: keep local items and append any server-only items
          const localCodes = new Set(watchlist.map(w => w.code))
          const merged = [
            ...watchlist,
            ...serverItems.filter(s => !localCodes.has(s.code)),
          ]
          if (merged.length > watchlist.length) {
            set({ watchlist: merged })
          }
        } catch {
          // Server unavailable — local list is fine
        }
      },
    }),
    {
      name: 'sch-app-store',
      partialize: state => ({ watchlist: state.watchlist, selectedTimeframe: state.selectedTimeframe }),
      merge: (persistedState, currentState) => {
        const typedState = (persistedState as Partial<AppStore> | undefined) ?? {}
        return {
          ...currentState,
          ...typedState,
          selectedTimeframe: normalizeDisplayTimeframe(typedState.selectedTimeframe ?? currentState.selectedTimeframe),
        }
      },
    },
  ),
)
