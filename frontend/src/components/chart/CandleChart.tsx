import { useEffect, useRef } from 'react'
import {
  ColorType,
  createChart,
  LineStyle,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'

import type { AnalysisResult, OHLCVBar, ProjectionScenario } from '@/types/api'

interface CandleChartProps {
  bars: OHLCVBar[]
  analysis?: AnalysisResult | null
  height?: number
}

const OVERLAY_COLORS = {
  neckline: '#f59e0b',
  target: '#34d399',
  invalidation: '#f87171',
  projectionBull: '#38bdf8',
  projectionBear: '#fb7185',
  projectionNeutral: '#94a3b8',
  projectionRisk: '#f59e0b',
}

const CHART_COLORS = {
  background: '#0b1220',
  text: '#96a3b8',
  grid: '#141c2b',
  border: '#1f2937',
}

export function CandleChart({ bars, analysis, height = 400 }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const overlayRef = useRef<ISeriesApi<'Line'>[]>([])

  useEffect(() => {
    if (!containerRef.current) return

    const containerWidth = containerRef.current.clientWidth || containerRef.current.getBoundingClientRect().width || 600
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.text,
      },
      grid: {
        vertLines: { color: CHART_COLORS.grid },
        horzLines: { color: CHART_COLORS.grid },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: CHART_COLORS.border },
      timeScale: { borderColor: CHART_COLORS.border, timeVisible: true, secondsVisible: false },
      width: containerWidth,
      height: height - 80,
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    const volSeries = chart.addHistogramSeries({
      color: '#385263',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })

    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })

    chartRef.current = chart
    candleRef.current = candleSeries
    volumeRef.current = volSeries

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, height - 80)
      }
    })
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
    }
  }, [height])

  useEffect(() => {
    if (!candleRef.current || !volumeRef.current || bars.length === 0) return

    const sortedBars = [...bars].sort((left, right) => compareBarDates(left.date, right.date))
    const isIntraday = sortedBars.some(bar => bar.date.includes('T'))
    chartRef.current?.applyOptions({
      timeScale: {
        timeVisible: isIntraday,
        secondsVisible: false,
      },
    })

    const candleData: CandlestickData[] = sortedBars.map(bar => ({
      time: toChartTime(bar.date),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }))

    const volumeData: HistogramData[] = sortedBars.map(bar => ({
      time: toChartTime(bar.date),
      value: bar.volume,
      color: bar.close >= bar.open ? 'rgba(38,166,154,0.4)' : 'rgba(239,83,80,0.4)',
    }))

    candleRef.current.setData(candleData)
    volumeRef.current.setData(volumeData)
    chartRef.current?.timeScale().fitContent()
  }, [bars])

  useEffect(() => {
    const chart = chartRef.current
    const candleSeries = candleRef.current
    if (!chart || !candleSeries || bars.length === 0) return

    overlayRef.current.forEach(series => {
      try {
        chart.removeSeries(series)
      } catch {
        // ignore stale series
      }
    })
    overlayRef.current = []
    candleSeries.setMarkers([])

    if (!analysis || analysis.patterns.length === 0) return

    const sortedBars = [...bars].sort((left, right) => compareBarDates(left.date, right.date))
    const firstTime = toChartTime(sortedBars[0].date)
    const lastBar = sortedBars[sortedBars.length - 1]
    const lastTime = toChartTime(lastBar.date)
    const lastClose = lastBar.close
    const best = analysis.patterns[0]

    const addHorizontalLine = (price: number, color: string, style: LineStyle) => {
      const series = chart.addLineSeries({
        color,
        lineWidth: 1,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: false,
      })

      const data: LineData[] = [
        { time: firstTime, value: price },
        { time: lastTime, value: price },
      ]

      series.setData(data)
      overlayRef.current.push(series)
    }

    if (best.neckline) addHorizontalLine(best.neckline, OVERLAY_COLORS.neckline, LineStyle.Dashed)
    if (best.target_level) addHorizontalLine(best.target_level, OVERLAY_COLORS.target, LineStyle.Dotted)
    if (best.invalidation_level) addHorizontalLine(best.invalidation_level, OVERLAY_COLORS.invalidation, LineStyle.Dotted)

    const markers: SeriesMarker<Time>[] = best.key_points
      .filter((point): point is { dt: string; price: number; type: string } => Boolean(point.dt))
      .sort((left, right) => compareBarDates(left.dt, right.dt))
      .map(point => ({
        time: toChartTime(point.dt),
        position: point.type.includes('low') || point.type === 'head' ? 'belowBar' : 'aboveBar',
        color: point.type.includes('neckline')
          ? OVERLAY_COLORS.neckline
          : point.type.includes('low')
            ? OVERLAY_COLORS.target
            : OVERLAY_COLORS.invalidation,
        shape: 'circle',
        text: markerLabel(point.type),
      }))

    candleSeries.setMarkers(markers)

    const projectionScenarios = getProjectionScenarios(analysis)
    projectionScenarios.slice(0, 3).forEach((scenario, index) => {
      const projectionSeries = chart.addLineSeries({
        color: scenarioColor(scenario),
        lineWidth: index === 0 ? 2 : 1,
        lineStyle: index === 0 ? LineStyle.Dashed : LineStyle.Dotted,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: index === 0,
      })

      const projectionData: LineData[] = [
        { time: lastTime, value: lastClose },
        ...scenario.path.map(point => ({
          time: toChartTime(point.dt),
          value: point.price,
        })),
      ]
      projectionSeries.setData(projectionData)
      overlayRef.current.push(projectionSeries)
    })

    chart.timeScale().fitContent()
  }, [analysis, bars])

  const projectionScenarios = analysis ? getProjectionScenarios(analysis) : []

  return (
    <div className="space-y-1">
      <div ref={containerRef} className="chart-container w-full rounded-lg" style={{ height }} />
      {analysis && analysis.patterns.length > 0 && (
        <div className="space-y-2 px-2 text-xs text-muted-foreground">
          <div className="flex flex-wrap items-center gap-4">
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-amber-400" style={{ borderTop: '1px dashed' }} /> 목선
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-green-400" style={{ borderTop: '1px dotted' }} /> 목표가
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-red-400" style={{ borderTop: '1px dotted' }} /> 무효화 기준
          </span>
          {projectionScenarios.length > 0 && (
            <>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block h-px w-3"
                  style={{ borderTop: `2px dashed ${scenarioColor(projectionScenarios[0])}` }}
                /> 주 시나리오
              </span>
              {projectionScenarios.some(scenario => scenario.key === 'range') && (
                <span className="flex items-center gap-1">
                  <span className="inline-block h-px w-3" style={{ borderTop: `1px dotted ${OVERLAY_COLORS.projectionNeutral}` }} /> 횡보 대안
                </span>
              )}
              {projectionScenarios.some(scenario => scenario.key === 'risk') && (
                <span className="flex items-center gap-1">
                  <span className="inline-block h-px w-3" style={{ borderTop: `1px dotted ${OVERLAY_COLORS.projectionRisk}` }} /> 리스크 대안
                </span>
              )}
            </>
          )}
          </div>
          {projectionScenarios.length > 0 && (
            <p className="leading-relaxed text-muted-foreground/90">
              예상선은 확정 예측이 아니라 최근 변동성과 현재 준비도를 반영한 조건부 경로입니다. 주 시나리오만 보지 말고 횡보/리스크
              대안도 함께 확인하세요.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function getProjectionScenarios(analysis: AnalysisResult): ProjectionScenario[] {
  if (analysis.projection_scenarios.length > 0) {
    return analysis.projection_scenarios
  }

  if (analysis.projected_path.length === 0) {
    return []
  }

  return [
    {
      key: 'primary',
      label: analysis.projection_label,
      weight: 1,
      bias: analysis.p_up >= analysis.p_down ? 'bullish' : 'bearish',
      summary: analysis.projection_summary,
      path: analysis.projected_path,
    },
  ]
}

function scenarioColor(scenario: ProjectionScenario): string {
  if (scenario.key === 'risk') return OVERLAY_COLORS.projectionRisk
  if (scenario.bias === 'bullish') return OVERLAY_COLORS.projectionBull
  if (scenario.bias === 'bearish') return OVERLAY_COLORS.projectionBear
  return OVERLAY_COLORS.projectionNeutral
}

function toChartTime(value: string): Time {
  if (value.includes('T')) {
    return Math.floor(new Date(value).getTime() / 1000) as Time
  }
  return value as Time
}

function markerLabel(type: string): string {
  switch (type) {
    case 'low1':
    case 'high1':
      return '1'
    case 'low2':
    case 'high2':
      return '2'
    case 'head':
      return 'H'
    case 'left_shoulder':
      return 'LS'
    case 'right_shoulder':
      return 'RS'
    case 'neckline':
    case 'left_neckline':
    case 'right_neckline':
      return 'N'
    default:
      return ''
  }
}

function compareBarDates(left: string, right: string): number {
  return toTimestamp(left) - toTimestamp(right)
}

function toTimestamp(value: string): number {
  if (value.includes('T')) {
    return new Date(value).getTime()
  }

  const daily = new Date(`${value}T00:00:00`).getTime()
  return Number.isNaN(daily) ? new Date(value).getTime() : daily
}
