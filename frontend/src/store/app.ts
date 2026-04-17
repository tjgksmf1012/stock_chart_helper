import { create } from 'zustand'

interface AppStore {
  selectedSymbol: string | null
  selectedTimeframe: '1d' | '60m' | '15m'
  setSymbol: (code: string) => void
  setTimeframe: (tf: '1d' | '60m' | '15m') => void
}

export const useAppStore = create<AppStore>((set) => ({
  selectedSymbol: null,
  selectedTimeframe: '1d',
  setSymbol: (code) => set({ selectedSymbol: code }),
  setTimeframe: (tf) => set({ selectedTimeframe: tf }),
}))
