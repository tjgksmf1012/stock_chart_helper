import type { ScanStatusResponse, Timeframe } from '@/types/api'

import { timeframeLabel } from './timeframes'

/**
 * Korean status/headline/empty-state copy for the dashboard. Pure functions
 * that turn a scan status into the text the page renders.
 */

export function statusHeadline(status: ScanStatusResponse | undefined) {
  if (!status) return '불러오는 중'
  if (status.is_running) return '스캔 진행 중'
  if (status.status === 'warming') return '백그라운드 준비 중'
  if (status.status === 'ready') return '준비 완료'
  if (status.status === 'error') return '확인 필요'
  return '대기 중'
}

export function statusSubline(status: ScanStatusResponse | undefined, timeframe: Timeframe) {
  if (!status) return `${timeframeLabel(timeframe)} 상태를 불러오는 중입니다.`
  if (status.is_running) {
    const cachedCount = status.cached_result_count ?? 0
    return cachedCount > 0
      ? `백그라운드 갱신 중입니다. 기존 ${cachedCount}개 결과는 그대로 보입니다.`
      : `${timeframeLabel(timeframe)} 갱신을 시작했습니다. 완료 전까지 기존 결과를 우선 표시합니다.`
  }
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} 결과를 백그라운드에서 준비 중입니다. 임시 후보가 먼저 보일 수 있습니다.`
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `지금은 ${timeframeLabel(timeframe)} 임시 후보를 먼저 보여주고 있으며, 실제 분석 결과가 준비되면 자동으로 교체됩니다.`
  }
  if (status.intraday_live_phase === 'off_hours') {
    return '장외 시간에는 live 분봉 후보를 일부러 비우고 저장 데이터 기준으로 보수적으로 보여줍니다.'
  }
  if (status.last_error) {
    return `최근 오류가 있었지만 마지막 캐시 결과는 유지되고 있습니다. 오류: ${status.last_error}`
  }
  return `${timeframeLabel(timeframe)} 기준 최근 스캔 결과를 표시하고 있습니다.`
}

export function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'running':
      return '실행 중'
    case 'queued':
      return '대기 중'
    case 'warming':
      return '준비 중'
    case 'ready':
      return '준비 완료'
    case 'error':
      return '오류'
    default:
      return '대기'
  }
}

export function candidateSourceLabel(source: string | null | undefined): string {
  switch (source) {
    case 'daily_seed':
      return '일봉 우선 후보'
    case 'fallback_seed':
      return 'fallback 후보'
    case 'placeholder_seed':
      return '임시 후보'
    case 'background_pending':
      return '백그라운드 대기'
    case 'cache_ready':
      return '캐시 완료'
    case 'krx_universe':
      return 'KRX 전체 스캔'
    case 'krx_universe_fdr':
      return 'KRX 대체 스캔 (FDR)'
    case 'krx_universe_fallback':
      return 'KRX 대체 유니버스'
    case 'static_fallback':
      return '기본 종목 스캔'
    case 'fallback':
      return '기본 후보'
    default:
      return '-'
  }
}

export function candidateSourceWarning(source: string | null | undefined): string | null {
  // 이제 static_fallback도 100개 기본 종목을 스캔하므로 경고 제거
  return null
}

export function getDefaultSectionEmptyMessage(status: ScanStatusResponse | undefined, timeframe: Timeframe): string | undefined {
  if (!status) return undefined
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} 결과를 백그라운드에서 준비 중입니다. 지금은 카드가 비어 보여도 정상입니다.`
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `${timeframeLabel(timeframe)} 임시 후보를 먼저 보여주는 단계입니다. 실제 분석이 끝나면 카드가 자동으로 채워집니다.`
  }
  if (status.candidate_source === 'fallback_seed') {
    return `${timeframeLabel(timeframe)} fallback 후보 기준이라 지금은 결과가 적게 보일 수 있습니다.`
  }
  return undefined
}

export function getLiveSectionEmptyMessage(status: ScanStatusResponse | undefined, timeframe: Timeframe): string | undefined {
  if (!status) return undefined
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} live 후보를 수집 중입니다. 준비가 끝나면 자동으로 채워집니다.`
  }
  if (status.intraday_live_phase === 'off_hours') {
    return '장외 시간에는 live 분봉 후보를 비워두는 것이 정상입니다. 대신 형성 중 후보를 먼저 확인해 보세요.'
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `${timeframeLabel(timeframe)} 임시 후보가 먼저 표시되는 단계라 live 후보 영역이 잠시 비어 있을 수 있습니다.`
  }
  if ((status.intraday_live_candidate_limit ?? 0) === 0) {
    return '지금 시간대 기준으로는 live 분봉까지 우선 확인할 후보가 아직 없습니다.'
  }
  return '현재 조건에서 live 분봉으로 바로 볼 만한 후보가 없습니다.'
}
