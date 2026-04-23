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

import type { AnalysisResult, OHLCVBar, PatternInfo, ProjectionScenario } from '@/types/api'

interface CandleChartProps {
  bars: OHLCVBar[]
  analysis?: AnalysisResult | null
  height?: number
}

interface CloudPoint {
  time: Time
  spanA: number
  spanB: number
}

interface IchimokuData {
  conversion: LineData[]
  base: LineData[]
  spanA: LineData[]
  spanB: LineData[]
  cloud: CloudPoint[]
}

const OVERLAY_COLORS = {
  neckline: '#f59e0b',
  target: '#34d399',
  invalidation: '#f87171',
  projectionBull: '#38bdf8',
  projectionBear: '#fb7185',
  projectionNeutral: '#94a3b8',
  projectionRisk: '#f59e0b',
  ichimokuConversion: '#60a5fa',
  ichimokuBase: '#f59e0b',
  ichimokuSpanA: '#34d399',
  ichimokuSpanB: '#f87171',
  ichimokuBullFill: 'rgba(52, 211, 153, 0.14)',
  ichimokuBearFill: 'rgba(248, 113, 113, 0.12)',
}

const CHART_COLORS = {
  background: '#0b1220',
  text: '#96a3b8',
  grid: '#141c2b',
  border: '#1f2937',
}

export function CandleChart({ bars, analysis, height = 400 }: CandleChartProps) {
  const chartHostRef = useRef<HTMLDivElement>(null)
  const cloudCanvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const overlayRef = useRef<ISeriesApi<'Line'>[]>([])
  const ichimokuRef = useRef<{
    conversion: ISeriesApi<'Line'> | null
    base: ISeriesApi<'Line'> | null
    spanA: ISeriesApi<'Line'> | null
    spanB: ISeriesApi<'Line'> | null
  }>({
    conversion: null,
    base: null,
    spanA: null,
    spanB: null,
  })
  const cloudPointsRef = useRef<CloudPoint[]>([])
  const redrawFrameRef = useRef<number | null>(null)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)

  // Ordinal time mapping — built once per bars update
  const indexToDateRef = useRef<string[]>([])
  const dateToIndexRef = useRef<Map<string, number>>(new Map())
  const lastBarIndexRef = useRef<number>(0)
  const isIntradayRef = useRef<boolean>(false)

  const syncCloudCanvas = () => {
    const host = chartHostRef.current
    const canvas = cloudCanvasRef.current
    if (!host || !canvas) return

    const rect = host.getBoundingClientRect()
    const width = Math.max(1, Math.round(rect.width))
    const heightPx = Math.max(1, Math.round(rect.height))
    const dpr = window.devicePixelRatio || 1

    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(heightPx * dpr)) {
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(heightPx * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${heightPx}px`
    }
  }

  const drawCloud = () => {
    redrawFrameRef.current = null
    syncCloudCanvas()

    const canvas = cloudCanvasRef.current
    const chart = chartRef.current
    const candleSeries = candleRef.current
    if (!canvas || !chart || !candleSeries) return

    const context = canvas.getContext('2d')
    if (!context) return

    const dpr = window.devicePixelRatio || 1
    context.setTransform(1, 0, 0, 1, 0, 0)
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.scale(dpr, dpr)

    const cloudPoints = cloudPointsRef.current
    if (cloudPoints.length < 2) return

    for (let index = 1; index < cloudPoints.length; index += 1) {
      const previous = cloudPoints[index - 1]
      const current = cloudPoints[index]
      const x1 = chart.timeScale().timeToCoordinate(previous.time)
      const x2 = chart.timeScale().timeToCoordinate(current.time)
      const a1 = candleSeries.priceToCoordinate(previous.spanA)
      const a2 = candleSeries.priceToCoordinate(current.spanA)
      const b1 = candleSeries.priceToCoordinate(previous.spanB)
      const b2 = candleSeries.priceToCoordinate(current.spanB)

      if ([x1, x2, a1, a2, b1, b2].some(value => value == null)) {
        continue
      }

      context.beginPath()
      context.moveTo(x1!, a1!)
      context.lineTo(x2!, a2!)
      context.lineTo(x2!, b2!)
      context.lineTo(x1!, b1!)
      context.closePath()
      context.fillStyle =
        (previous.spanA + current.spanA) / 2 >= (previous.spanB + current.spanB) / 2
          ? OVERLAY_COLORS.ichimokuBullFill
          : OVERLAY_COLORS.ichimokuBearFill
      context.fill()
    }
  }

  const scheduleCloudDraw = () => {
    if (redrawFrameRef.current != null) {
      window.cancelAnimationFrame(redrawFrameRef.current)
    }
    redrawFrameRef.current = window.requestAnimationFrame(drawCloud)
  }

  useEffect(() => {
    if (!chartHostRef.current) return

    const chart = createChart(chartHostRef.current, {
      autoSize: true,
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
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderVisible: false,
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    const volumeSeries = chart.addHistogramSeries({
      color: '#385263',
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })

    const conversionSeries = chart.addLineSeries({
      color: OVERLAY_COLORS.ichimokuConversion,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    const baseSeries = chart.addLineSeries({
      color: OVERLAY_COLORS.ichimokuBase,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    const spanASeries = chart.addLineSeries({
      color: OVERLAY_COLORS.ichimokuSpanA,
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    const spanBSeries = chart.addLineSeries({
      color: OVERLAY_COLORS.ichimokuSpanB,
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })

    chartRef.current = chart
    candleRef.current = candleSeries
    volumeRef.current = volumeSeries
    ichimokuRef.current = {
      conversion: conversionSeries,
      base: baseSeries,
      spanA: spanASeries,
      spanB: spanBSeries,
    }

    const handleRangeChange = () => scheduleCloudDraw()
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleRangeChange)

    resizeObserverRef.current = new ResizeObserver(() => scheduleCloudDraw())
    resizeObserverRef.current.observe(chartHostRef.current)

    scheduleCloudDraw()

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleRangeChange)
      resizeObserverRef.current?.disconnect()
      resizeObserverRef.current = null
      if (redrawFrameRef.current != null) {
        window.cancelAnimationFrame(redrawFrameRef.current)
      }
      chart.remove()
    }
  }, [])

  useEffect(() => {
    if (!candleRef.current || !volumeRef.current || bars.length === 0) return

    const sortedBars = [...bars].sort((left, right) => compareBarDates(left.date, right.date))
    const isIntraday = sortedBars.some(bar => bar.date.includes('T') || bar.date.includes(' '))
    isIntradayRef.current = isIntraday

    // Build ordinal index maps for daily bars
    const dateToIndex = new Map<string, number>()
    const indexToDate: string[] = []

    if (!isIntraday) {
      sortedBars.forEach((bar, i) => {
        const key = bar.date.slice(0, 10)
        dateToIndex.set(key, i)
        indexToDate.push(key)
      })
      dateToIndexRef.current = dateToIndex
      indexToDateRef.current = indexToDate
      lastBarIndexRef.current = sortedBars.length - 1
    }

    // chart.applyOptions() accepts TimeChartOptions → timeScale: TimeScaleOptions
    // which includes tickMarkFormatter (unlike timeScale().applyOptions() which uses HorzScaleOptions)
    chartRef.current?.applyOptions({
      timeScale: {
        timeVisible: isIntraday,
        secondsVisible: false,
        tickMarkFormatter: isIntraday
          ? undefined
          : (time: Time, tickMarkType: number) => {
              const dateStr = indexToDateRef.current[time as number]
              if (!dateStr) return ''
              return formatDateTick(dateStr, tickMarkType)
            },
      },
    })

    const toTime = (date: string): Time => {
      if (isIntraday) return Math.floor(toTimestamp(date) / 1000) as Time
      return (dateToIndex.get(date.slice(0, 10)) ?? 0) as Time
    }

    const candleData: CandlestickData[] = sortedBars.map(bar => ({
      time: toTime(bar.date),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }))

    const volumeData: HistogramData[] = sortedBars.map(bar => ({
      time: toTime(bar.date),
      value: bar.volume,
      color: bar.close >= bar.open ? 'rgba(38,166,154,0.4)' : 'rgba(239,83,80,0.4)',
    }))

    const ichimoku = buildIchimoku(sortedBars, dateToIndex, isIntraday)

    candleRef.current.setData(candleData)
    volumeRef.current.setData(volumeData)
    ichimokuRef.current.conversion?.setData(ichimoku.conversion)
    ichimokuRef.current.base?.setData(ichimoku.base)
    ichimokuRef.current.spanA?.setData(ichimoku.spanA)
    ichimokuRef.current.spanB?.setData(ichimoku.spanB)
    cloudPointsRef.current = ichimoku.cloud

    chartRef.current?.timeScale().fitContent()
    scheduleCloudDraw()
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

    if (!analysis) {
      scheduleCloudDraw()
      return
    }

    const sortedBars = [...bars].sort((left, right) => compareBarDates(left.date, right.date))
    const isIntraday = isIntradayRef.current
    const dateToIndex = dateToIndexRef.current
    const lastIndex = lastBarIndexRef.current
    const lastBar = sortedBars[sortedBars.length - 1]
    const lastClose = lastBar.close

    // Convert any date string → chart Time, including future dates
    const toTime = (date: string): Time => {
      if (isIntraday) return Math.floor(toTimestamp(date) / 1000) as Time
      const key = date.slice(0, 10)
      const existing = dateToIndex.get(key)
      if (existing !== undefined) return existing as Time
      // Future date: estimate trading days ahead from last bar
      const lastDateStr = indexToDateRef.current[lastIndex] ?? lastBar.date.slice(0, 10)
      const lastTs = new Date(lastDateStr + 'T00:00:00Z').getTime()
      const thisTs = new Date(key + 'T00:00:00Z').getTime()
      const calDays = (thisTs - lastTs) / (24 * 60 * 60 * 1000)
      const tradingDays = Math.max(1, Math.round(calDays * 5 / 7))
      return (lastIndex + tradingDays) as Time
    }

    // Time range helpers
    const firstTime: Time = isIntraday
      ? (Math.floor(toTimestamp(sortedBars[0].date) / 1000) as Time)
      : (0 as Time)
    const lastTime: Time = isIntraday
      ? (Math.floor(toTimestamp(lastBar.date) / 1000) as Time)
      : (lastIndex as Time)
    // Extend horizontal lines 30 "bars" beyond last candle to cover projection area
    const horizonTime: Time = isIntraday
      ? (Math.floor(toTimestamp(lastBar.date) / 1000 + 30 * 86400) as Time)
      : ((lastIndex + 30) as Time)

    const best = getChartPattern(analysis)
    const projectionScenarios = getProjectionScenarios(analysis, best)
    if (!best && projectionScenarios.length === 0) {
      scheduleCloudDraw()
      return
    }

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
        { time: horizonTime, value: price },
      ]

      series.setData(data)
      overlayRef.current.push(series)
    }

    if (best) {
      if (best.neckline) addHorizontalLine(best.neckline, OVERLAY_COLORS.neckline, LineStyle.Dashed)
      if (best.target_level) addHorizontalLine(best.target_level, OVERLAY_COLORS.target, LineStyle.Dotted)
      if (best.invalidation_level) addHorizontalLine(best.invalidation_level, OVERLAY_COLORS.invalidation, LineStyle.Dotted)

      const markers: SeriesMarker<Time>[] = best.key_points
        .filter((point): point is { dt: string; price: number; type: string } => Boolean(point.dt))
        .sort((left, right) => compareBarDates(left.dt, right.dt))
        .map(point => ({
          time: toTime(point.dt),
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
    }

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
          time: toTime(point.dt),
          value: point.price,
        })),
      ]
      projectionSeries.setData(projectionData)
      overlayRef.current.push(projectionSeries)
    })

    chart.timeScale().fitContent()
    scheduleCloudDraw()
  }, [analysis, bars])

  const chartPattern = analysis ? getChartPattern(analysis) : null
  const projectionScenarios = analysis ? getProjectionScenarios(analysis, chartPattern) : []

  return (
    <div className="space-y-1">
      <div className="relative w-full overflow-hidden rounded-lg" style={{ height: height - 80 }}>
        <div ref={chartHostRef} className="chart-container absolute inset-0" />
        <canvas ref={cloudCanvasRef} className="pointer-events-none absolute inset-0 z-10" />
      </div>
      <div className="space-y-2 px-2 text-xs text-muted-foreground">
        <div className="flex flex-wrap items-center gap-4">
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-blue-400" /> 단기선
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 bg-amber-400" /> 중기선
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-3 rounded-sm bg-emerald-400/25 ring-1 ring-emerald-400/30" /> 지지 구름
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-3 rounded-sm bg-red-400/20 ring-1 ring-red-400/30" /> 저항 구름
          </span>
          {chartPattern && (
            <>
              <span className="flex items-center gap-1">
                <span className="inline-block h-px w-3 bg-amber-400" style={{ borderTop: '1px dashed' }} /> 돌파선
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-px w-3 bg-green-400" style={{ borderTop: '1px dotted' }} /> 익절 기준가
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-px w-3 bg-red-400" style={{ borderTop: '1px dotted' }} /> 손절 기준가
              </span>
            </>
          )}
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
        <p className="leading-relaxed text-muted-foreground/90">
          구름대 위에서 버티면 지지, 아래로 밀리면 주의 — 단기선·중기선과 함께 보세요.
        </p>
        {projectionScenarios.length > 0 && (
          <p className="leading-relaxed text-muted-foreground/90">
            예상 경로는 확정 예언이 아니라 최근 변동성과 현재 준비도를 반영한 조건부 경로입니다. 주 시나리오만 보지 말고 횡보와 리스크 경로도 같이 확인해 주세요.
          </p>
        )}
      </div>
    </div>
  )
}

// Build Ichimoku lines using ordinal indices for daily bars (no holiday gaps)
function buildIchimoku(
  sortedBars: OHLCVBar[],
  dateToIndex: Map<string, number>,
  isIntraday: boolean,
): IchimokuData {
  const conversion: LineData[] = []
  const base: LineData[] = []
  const spanA: LineData[] = []
  const spanB: LineData[] = []
  const cloud: CloudPoint[] = []
  const stepMs = isIntraday ? inferStepMs(sortedBars) : 0

  for (let index = 0; index < sortedBars.length; index += 1) {
    const time: Time = isIntraday
      ? (Math.floor(toTimestamp(sortedBars[index].date) / 1000) as Time)
      : ((dateToIndex.get(sortedBars[index].date.slice(0, 10)) ?? index) as Time)

    const conversionValue = midpoint(sortedBars, index, 9)
    const baseValue = midpoint(sortedBars, index, 26)

    if (conversionValue != null) {
      conversion.push({ time, value: conversionValue })
    }

    if (baseValue != null) {
      base.push({ time, value: baseValue })
    }

    if (conversionValue != null && baseValue != null) {
      // Lead span: shift 26 periods forward
      // For ordinal mode, this is simply index + 26 (exact bar count, no calendar math)
      const leadingTime: Time = isIntraday
        ? (Math.floor((toTimestamp(sortedBars[index].date) + stepMs * 26) / 1000) as Time)
        : ((index + 26) as Time)

      const leadingA = (conversionValue + baseValue) / 2
      spanA.push({ time: leadingTime, value: leadingA })

      const leadingB = midpoint(sortedBars, index, 52)
      if (leadingB != null) {
        spanB.push({ time: leadingTime, value: leadingB })
        cloud.push({ time: leadingTime, spanA: leadingA, spanB: leadingB })
      }
    }
  }

  return { conversion, base, spanA, spanB, cloud }
}

function midpoint(bars: OHLCVBar[], endIndex: number, period: number) {
  if (endIndex < period - 1) return null

  let highest = Number.NEGATIVE_INFINITY
  let lowest = Number.POSITIVE_INFINITY
  for (let index = endIndex - period + 1; index <= endIndex; index += 1) {
    highest = Math.max(highest, bars[index].high)
    lowest = Math.min(lowest, bars[index].low)
  }

  return (highest + lowest) / 2
}

function inferStepMs(bars: OHLCVBar[]) {
  if (bars.length < 2) return 24 * 60 * 60 * 1000

  const diffs: number[] = []
  for (let index = 1; index < bars.length; index += 1) {
    const diff = toTimestamp(bars[index].date) - toTimestamp(bars[index - 1].date)
    if (diff > 0) diffs.push(diff)
  }

  if (diffs.length === 0) return 24 * 60 * 60 * 1000
  diffs.sort((left, right) => left - right)
  return diffs[Math.floor(diffs.length / 2)]
}

// Format a YYYY-MM-DD string for a given lightweight-charts TickMarkType:
// 0 = Year, 1 = Month, 2 = DayOfMonth, 3 = Time, 4 = TimeWithSeconds
function formatDateTick(dateStr: string, tickMarkType: number): string {
  const [year, month, day] = dateStr.split('-')
  if (tickMarkType === 0) return year
  if (tickMarkType === 1) return `${year}.${month}`
  return `${month}/${day}`
}

function getChartPattern(analysis: AnalysisResult): PatternInfo | null {
  return analysis.patterns.find(pattern => isActivePattern(pattern)) ?? null
}

function isActivePattern(pattern: PatternInfo): boolean {
  return (
    pattern.state !== 'played_out' &&
    pattern.state !== 'invalidated' &&
    !pattern.target_hit_at &&
    !pattern.invalidated_at
  )
}

function getProjectionScenarios(analysis: AnalysisResult, chartPattern: PatternInfo | null): ProjectionScenario[] {
  if (analysis.no_signal_flag || !chartPattern) {
    return []
  }

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
