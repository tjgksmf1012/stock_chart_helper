import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  LineStyle,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'

import type { AnalysisResult, OHLCVBar } from '@/types/api'

interface CandleChartProps {
  bars: OHLCVBar[]
  analysis?: AnalysisResult | null
  height?: number
}

const OVERLAY_COLORS = {
  neckline: '#f59e0b',
  target: '#34d399',
  invalidation: '#f87171',
}

export function CandleChart({ bars, analysis, height = 400 }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const overlayRef = useRef<ISeriesApi<'Line'>[]>([])

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'hsl(222 47% 8%)' },
        textColor: 'hsl(215 20% 65%)',
      },
      grid: {
        vertLines: { color: 'hsl(217 32% 12%)' },
        horzLines: { color: 'hsl(217 32% 12%)' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: 'hsl(217 32% 17%)' },
      timeScale: { borderColor: 'hsl(217 32% 17%)', timeVisible: true },
      width: containerRef.current.clientWidth,
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

    const candleData: CandlestickData[] = bars.map(bar => ({
      time: bar.date as Time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }))

    const volumeData: HistogramData[] = bars.map(bar => ({
      time: bar.date as Time,
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

    if (!analysis || analysis.no_signal_flag || analysis.patterns.length === 0) return

    const best = analysis.patterns[0]
    const firstTime = bars[0].date as Time
    const lastTime = bars[bars.length - 1].date as Time

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

    if (best.neckline) {
      addHorizontalLine(best.neckline, OVERLAY_COLORS.neckline, LineStyle.Dashed)
    }
    if (best.target_level) {
      addHorizontalLine(best.target_level, OVERLAY_COLORS.target, LineStyle.Dotted)
    }
    if (best.invalidation_level) {
      addHorizontalLine(best.invalidation_level, OVERLAY_COLORS.invalidation, LineStyle.Dotted)
    }

    const markers: SeriesMarker<Time>[] = best.key_points
      .filter((point): point is { dt: string; price: number; type: string } => Boolean(point.dt))
      .map(point => ({
        time: point.dt.split('T')[0] as Time,
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
  }, [analysis, bars])

  return (
    <div className="space-y-1">
      <div ref={containerRef} className="chart-container w-full rounded-lg" style={{ height }} />
      {analysis && !analysis.no_signal_flag && analysis.patterns.length > 0 && (
        <div className="flex items-center gap-4 px-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-amber-400" style={{ borderTop: '1px dashed' }} /> 목선
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-green-400" style={{ borderTop: '1px dotted' }} /> 목표가
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-red-400" style={{ borderTop: '1px dotted' }} /> 무효화 기준
          </span>
        </div>
      )}
    </div>
  )
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
