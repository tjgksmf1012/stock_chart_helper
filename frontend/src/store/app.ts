import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { Timeframe, WatchlistItem } from '@/types/api'
import { DEFAULT_TIMEFRAME, normalizeDisplayTimeframe } from '@/lib/timeframes'
import { watchlistApi } from '@/lib/api'

export interface RiskSettings {
  /** 계좌 총액 (원). 0 = 미설정 */
  accountSize: number
  /** 1회 최대 리스크 비율 (예: 0.02 = 2%) */
  riskPerTrade: number
  /** ATR 손절 배수 (예: 2.0 = ATR×2) */
  atrMultiplier: number
  /** true=ATR 기준, false=패턴 기준 */
  preferAtrStop: boolean
}

const DEFAULT_RISK_SETTINGS: RiskSettings = {
  accountSize: 0,
  riskPerTrade: 0.02,
  atrMultiplier: 2.0,
  preferAtrStop: false,
}

// 서버 동기화(add/remove)가 실패했을 때 몇 번 더 시도해 본다 — 삭제 직후 잠깐의
// 네트워크 문제로 서버에만 남아 있다가, 다음 syncFromServer에서 되살아나는 걸 줄인다.
async function withRetry(fn: () => Promise<unknown>, retries = 2, delayMs = 1000): Promise<void> {
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      await fn()
      return
    } catch {
      if (attempt === retries) return
      await new Promise(resolve => setTimeout(resolve, delayMs * (attempt + 1)))
    }
  }
}

interface AppStore {
  selectedSymbol: string | null
  selectedTimeframe: Timeframe
  watchlist: WatchlistItem[]
  /** 로컬에서 지웠지만 서버 삭제가 아직 확인되지 않은 종목 코드 — syncFromServer가 이 코드를 되살리지 않게 막는 tombstone. */
  pendingRemovals: string[]
  riskSettings: RiskSettings
  setSymbol: (code: string) => void
  setTimeframe: (tf: Timeframe) => void
  addToWatchlist: (item: { code: string; name: string; market: string }) => void
  removeFromWatchlist: (code: string) => void
  isWatched: (code: string) => boolean
  /** Pull the server-side watchlist and merge into local state. */
  syncFromServer: () => Promise<void>
  setRiskSettings: (settings: Partial<RiskSettings>) => void
}

export const useAppStore = create<AppStore>()(
  persist(
    (set, get) => ({
      selectedSymbol: null,
      selectedTimeframe: DEFAULT_TIMEFRAME,
      watchlist: [],
      pendingRemovals: [],
      riskSettings: DEFAULT_RISK_SETTINGS,

      setSymbol: code => set({ selectedSymbol: code }),
      setTimeframe: tf => set({ selectedTimeframe: normalizeDisplayTimeframe(tf) }),

      addToWatchlist: item => {
        const { watchlist } = get()
        if (watchlist.some(w => w.code === item.code)) return
        const updated = [...watchlist, { ...item, addedAt: new Date().toISOString() }]
        set({
          watchlist: updated,
          // 방금 지웠다가 바로 다시 추가하는 경우 tombstone을 남겨두면 안 됨
          pendingRemovals: get().pendingRemovals.filter(code => code !== item.code),
        })
        void withRetry(() => watchlistApi.add(item))
      },

      removeFromWatchlist: code => {
        const updated = get().watchlist.filter(w => w.code !== code)
        set({ watchlist: updated, pendingRemovals: [...get().pendingRemovals, code] })
        void withRetry(() => watchlistApi.remove(code)).then(() => {
          set({ pendingRemovals: get().pendingRemovals.filter(pending => pending !== code) })
        })
      },

      isWatched: code => get().watchlist.some(w => w.code === code),

      setRiskSettings: (settings) =>
        set(state => ({ riskSettings: { ...state.riskSettings, ...settings } })),

      syncFromServer: async () => {
        try {
          const serverItems = await watchlistApi.get()
          if (!serverItems?.length) return
          const { watchlist, pendingRemovals } = get()
          // Merge: keep local items and append any server-only items, but never
          // resurrect a code the user just removed locally (pendingRemovals tombstone)
          const localCodes = new Set(watchlist.map(w => w.code))
          const removedCodes = new Set(pendingRemovals)
          const merged = [
            ...watchlist,
            ...serverItems.filter(s => !localCodes.has(s.code) && !removedCodes.has(s.code)),
          ]
          if (merged.length > watchlist.length) {
            set({ watchlist: merged })
          }
          // 이전에 실패한 삭제를 이 기회에 다시 시도
          pendingRemovals.forEach(code => {
            void withRetry(() => watchlistApi.remove(code)).then(() => {
              set({ pendingRemovals: get().pendingRemovals.filter(pending => pending !== code) })
            })
          })
        } catch {
          // Server unavailable — local list is fine
        }
      },
    }),
    {
      name: 'sch-app-store',
      partialize: state => ({
        watchlist: state.watchlist,
        pendingRemovals: state.pendingRemovals,
        selectedTimeframe: state.selectedTimeframe,
        riskSettings: state.riskSettings,
      }),
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
