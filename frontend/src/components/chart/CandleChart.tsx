import { useEffect, useRef } from 'react'
import {
  createChart, ColorType, CandlestickSeries, HistogramSeries,
  type IChartApi, type ISeriesApi, type CandlestickData, type HistogramData,
} from 'lightweight-charts'
import type { OHLCVBar } from '@/types/api'

interface CandleChartProps {
  bars: OHLCVBar[]
  height?: number
}

export function CandleChart({ bars, height = 400 }: CandleChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volRef = useRef<ISeriesApi<'Histogram'> | null>(null)

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
      timeScale: {
        borderColor: 'hsl(217 32% 17%)',
        timeVisible: true,
      },
      width: containerRef.current.clientWidth,
      height: height - 80,
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    const volSeries = chart.addSeries(HistogramSeries, {
      color: '#385263',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })

    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })

    chartRef.current = chart
    candleRef.current = candleSeries
    volRef.current = volSeries

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, height - 80)
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
    }
  }, [height])

  useEffect(() => {
    if (!candleRef.current || !volRef.current || bars.length === 0) return

    const candleData: CandlestickData[] = bars.map(b => ({
      time: b.date as unknown as import('lightweight-charts').Time,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }))

    const volData: HistogramData[] = bars.map(b => ({
      time: b.date as unknown as import('lightweight-charts').Time,
      value: b.volume,
      color: b.close >= b.open ? 'rgba(38,166,154,0.4)' : 'rgba(239,83,80,0.4)',
    }))

    candleRef.current.setData(candleData)
    volRef.current.setData(volData)
    chartRef.current?.timeScale().fitContent()
  }, [bars])

  return (
    <div ref={containerRef} className="w-full chart-container rounded-lg" style={{ height }} />
  )
}
