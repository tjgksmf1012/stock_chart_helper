import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmtPct(val: number, decimals = 1): string {
  return `${(val * 100).toFixed(decimals)}%`
}

export function fmtPrice(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '-'
  return `${Math.round(val).toLocaleString('ko-KR')}원`
}

export function fmtNumber(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '-'
  return val.toLocaleString('ko-KR')
}

export function fmtTurnoverBillion(val: number | null | undefined): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '-'
  return `${val.toFixed(1)}억`
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '-'

  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

export const STATE_LABELS: Record<string, string> = {
  forming: '형성 중',
  armed: '활성 임박',
  confirmed: '확인 완료',
  invalidated: '무효화',
  played_out: '목표 달성',
}

export const STATE_COLORS: Record<string, string> = {
  forming: 'text-yellow-400 bg-yellow-400/10',
  armed: 'text-orange-400 bg-orange-400/10',
  confirmed: 'text-green-400 bg-green-400/10',
  invalidated: 'text-red-400 bg-red-400/10',
  played_out: 'text-slate-400 bg-slate-400/10',
}

export const PATTERN_NAMES: Record<string, string> = {
  double_bottom: '이중 바닥 (W)',
  double_top: '이중 천장 (M)',
  head_and_shoulders: '헤드 앤 숄더',
  inverse_head_and_shoulders: '역헤드 앤 숄더',
  ascending_triangle: '상승 삼각형',
  descending_triangle: '하락 삼각형',
  symmetric_triangle: '대칭 삼각형',
  rectangle: '박스권',
  rising_channel: '상승 채널',
  falling_channel: '하락 채널',
  cup_and_handle: '컵 앤 핸들',
  rounding_bottom: '라운딩 바닥',
  vcp: 'VCP 변동성 수축',
}

export const PATTERN_VARIANT_NAMES: Record<string, string> = {
  adam_adam: 'Adam / Adam',
  adam_eve: 'Adam / Eve',
  eve_adam: 'Eve / Adam',
  eve_eve: 'Eve / Eve',
  hybrid_adam: 'Hybrid / Adam',
  hybrid_eve: 'Hybrid / Eve',
  adam_hybrid: 'Adam / Hybrid',
  eve_hybrid: 'Eve / Hybrid',
  hybrid_hybrid: 'Hybrid / Hybrid',
  '3_contractions': '3회 수축',
  '4_contractions': '4회 수축',
}

export const DIRECTION_LABELS: Record<string, string> = {
  bullish: '상승형',
  bearish: '하락형',
  neutral: '중립형',
}

export const WYCKOFF_LABELS: Record<string, string> = {
  accumulation: '매집',
  markup: '상승 진행',
  distribution: '분산',
  markdown: '하락 진행',
  neutral: '중립',
}

export const CANDLE_CONFIRMATION_LABELS: Record<string, string> = {
  bullish_confirmation: '상승 확인 캔들',
  bearish_confirmation: '하락 확인 캔들',
  bullish_rejection: '상승 반박 캔들',
  bearish_rejection: '하락 반박 캔들',
  mixed: '중립 캔들',
  neutral: '중립 캔들',
}

export const INTRADAY_SESSION_LABELS: Record<string, string> = {
  open_drive: '시가 주도',
  midday: '장중 소강',
  closing_drive: '종가 주도',
  regular_session: '정규장',
  off_hours: '장외 시간',
  neutral: '중립',
}

export const SETUP_STAGE_LABELS: Record<string, string> = {
  confirmed: '확인 완료',
  trigger_ready: '트리거 대기',
  breakout_watch: '돌파 감시',
  late_base: '후반 베이스',
  early_trigger_watch: '초기 트리거 감시',
  base_building: '베이스 형성',
  no_signal: '관망',
}

export const INTRADAY_COLLECTION_MODE_LABELS: Record<string, string> = {
  live: 'live',
  stored: '저장 캐시',
  public: '공개 소스',
  mixed: '혼합',
  cooldown: '쿨다운',
  budget: '절약 모드',
}

export function getPatternBias(patternType: string | null | undefined): 'bullish' | 'bearish' | 'neutral' {
  if (!patternType) return 'neutral'

  if (['double_bottom', 'inverse_head_and_shoulders', 'ascending_triangle', 'cup_and_handle', 'rounding_bottom', 'vcp'].includes(patternType)) {
    return 'bullish'
  }

  if (['double_top', 'head_and_shoulders', 'descending_triangle', 'falling_channel'].includes(patternType)) {
    return 'bearish'
  }

  return 'neutral'
}
