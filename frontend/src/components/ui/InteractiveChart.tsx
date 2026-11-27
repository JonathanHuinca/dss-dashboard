import React, { Suspense, lazy, useEffect, useMemo, useRef, memo } from 'react'
import type PlotlyTypes from 'plotly.js-cartesian-dist-min'

let plotlyModuloPromise: Promise<typeof PlotlyTypes> | null = null
let plotlyCargado: typeof PlotlyTypes | null = null

function aplicarBlindajePlotly(Plotly: typeof PlotlyTypes) {
  if (typeof window === 'undefined' || !Plotly) return
  const safeWrap = (obj: any, method: string) => {
    if (obj && typeof obj[method] === 'function' && !obj[method].__uctWrapped) {
      const orig = obj[method]
      const wrapped = function (this: any, gd: any, ...args: any[]) {
        if (!gd) return Promise.resolve ? Promise.resolve() : undefined
        try {
          return orig.apply(this, [gd, ...args])
        } catch (err: any) {
          if (err?.message?.includes('DOM element provided is null or undefined')) {
            return Promise.resolve ? Promise.resolve() : undefined
          }
          throw err
        }
      }
      ;(wrapped as any).__uctWrapped = true
      obj[method] = wrapped
    }
  }

  safeWrap(Plotly.Plots, 'resize')
  safeWrap(Plotly, 'purge')
  safeWrap(Plotly, 'relayout')
  safeWrap(Plotly, 'restyle')
  safeWrap(Plotly, 'react')
}

async function cargarPlotly(): Promise<typeof PlotlyTypes> {
  if (plotlyCargado) return plotlyCargado
  if (!plotlyModuloPromise) {
    plotlyModuloPromise = import('plotly.js-cartesian-dist-min').then((mod) => {
      const inst = (mod.default || mod) as typeof PlotlyTypes
      aplicarBlindajePlotly(inst)
      plotlyCargado = inst
      return inst
    })
  }
  return plotlyModuloPromise
}

const LazyPlot = lazy(async () => {
  const [Plotly, factoryMod] = await Promise.all([
    cargarPlotly(),
    import('react-plotly.js/factory'),
  ])
  const createPlotlyComponent = (factoryMod.default || factoryMod) as (p: any) => React.ComponentType<any>
  return { default: createPlotlyComponent(Plotly) }
})

function esIgualSuperficial(a?: Record<string, any>, b?: Record<string, any>): boolean {
  if (a === b) return true
  if (!a || !b) return false
  const keysA = Object.keys(a)
  const keysB = Object.keys(b)
  if (keysA.length !== keysB.length) return false
  for (const k of keysA) {
    if (a[k] !== b[k]) return false
  }
  return true
}

const DEBOUNCE_RESIZE_MS = 100

export interface InteractiveChartProps {
  data: PlotlyTypes.Data[]
  layout?: Partial<PlotlyTypes.Layout>
  config?: Partial<PlotlyTypes.Config>
  filename?: string
  height?: number | string
  className?: string
  style?: React.CSSProperties
  onClick?: (event: Readonly<PlotlyTypes.PlotMouseEvent>) => void
  onLegendClick?: (event: Readonly<PlotlyTypes.LegendClickEvent>) => boolean
}

function InteractiveChartComponent({
  data,
  layout = {},
  config = {},
  filename = 'grafico_uct',
  height = 320,
  className = '',
  style = {},
  onClick,
  onLegendClick,
}: InteractiveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    let animationFrameId = 0
    let timeoutId: number | undefined
    let ultimoAncho = el.clientWidth
    let ultimoAlto = el.clientHeight

    // Debounce + rAF: evita bucles de render y múltiples relayouts por ráfaga de resize
    const observer = new ResizeObserver(() => {
      if (el.clientWidth === ultimoAncho && el.clientHeight === ultimoAlto) return
      ultimoAncho = el.clientWidth
      ultimoAlto = el.clientHeight
      if (timeoutId) window.clearTimeout(timeoutId)
      timeoutId = window.setTimeout(() => {
        if (animationFrameId) window.cancelAnimationFrame(animationFrameId)
        animationFrameId = window.requestAnimationFrame(() => {
          const plotEl = el.querySelector('.js-plotly-plot') as HTMLElement | null
          if (plotEl && plotEl.isConnected && (plotEl as any)._fullLayout && plotlyCargado?.Plots?.resize) {
            try {
              plotlyCargado.Plots.resize(plotEl)
            } catch {
              // Silenciar excepciones en desmontajes concurrentes
            }
          }
        })
      }, DEBOUNCE_RESIZE_MS)
    })

    observer.observe(el)

    const mountRaf = window.requestAnimationFrame(() => {
      const plotEl = el.querySelector('.js-plotly-plot') as HTMLElement | null
      if (plotEl && plotEl.isConnected && (plotEl as any)._fullLayout && plotlyCargado?.Plots?.resize) {
        try {
          plotlyCargado.Plots.resize(plotEl)
        } catch {
          // Silenciar
        }
      }
    })

    return () => {
      window.cancelAnimationFrame(mountRaf)
      if (timeoutId) window.clearTimeout(timeoutId)
      if (animationFrameId) window.cancelAnimationFrame(animationFrameId)
      observer.disconnect()
      const plotEl = el.querySelector('.js-plotly-plot') as HTMLElement | null
      if (plotEl && plotlyCargado?.purge) {
        try {
          plotlyCargado.purge(plotEl)
        } catch {
          // Silenciar en desmontaje
        }
      }
    }
  }, [])

  const stableLayoutRef = useRef(layout)
  if (!esIgualSuperficial(stableLayoutRef.current as Record<string, any>, layout as Record<string, any>)) {
    stableLayoutRef.current = layout
  }
  const layoutEstable = stableLayoutRef.current

  const stableConfigRef = useRef(config)
  if (!esIgualSuperficial(stableConfigRef.current as Record<string, any>, config as Record<string, any>)) {
    stableConfigRef.current = config
  }
  const configEstable = stableConfigRef.current

  const defaultLayout = useMemo<Partial<PlotlyTypes.Layout>>(() => ({
    autosize: true,
    paper_bgcolor: '#ffffff',
    plot_bgcolor: '#ffffff',
    font: {
      family: 'Inter, system-ui, sans-serif',
      color: '#64748b',
      size: 11,
    },
    legend: {
      orientation: 'h',
      yanchor: 'top',
      y: -0.28,
      xanchor: 'center',
      x: 0.5,
      font: { size: 10.5, color: '#334155' },
      itemclick: 'toggle',
      ...(layoutEstable.legend || {}),
    },
    dragmode: 'zoom',
    hovermode: 'closest',
    ...layoutEstable,
    margin: {
      t: 30,
      r: 25,
      b: 55,
      l: 55,
      ...(layoutEstable.margin || {}),
    },
    xaxis: {
      automargin: true,
      ...(layoutEstable.xaxis || {}),
    },
    yaxis: {
      automargin: true,
      ...(layoutEstable.yaxis || {}),
    },
  }), [layoutEstable])

  const defaultConfig = useMemo<Partial<PlotlyTypes.Config>>(() => ({
    responsive: true,
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['lasso2d'],
    toImageButtonOptions: {
      format: 'png',
      filename,
      height: 700,
      width: 1200,
      scale: 3,
    },
    ...configEstable,
  }), [configEstable, filename])

  // Revisión referencial sin serializar trazas masivas con JSON.stringify
  const revisionRef = useRef(0)
  const previoRef = useRef<{
    data: PlotlyTypes.Data[]
    layout: Partial<PlotlyTypes.Layout>
    config: Partial<PlotlyTypes.Config>
  } | null>(null)
  const previo = previoRef.current
  if (!previo || previo.data !== data || previo.layout !== defaultLayout || previo.config !== defaultConfig) {
    revisionRef.current += 1
    previoRef.current = { data, layout: defaultLayout, config: defaultConfig }
  }

  const layoutFinal = useMemo(() => ({ ...defaultLayout, autosize: true }), [defaultLayout])
  const estiloPlot = useMemo<React.CSSProperties>(
    () => ({ width: '100%', height: '100%', minHeight: '100%', flex: '1 1 0%' }),
    [],
  )

  const handlePlotUpdate = () => {
    if (import.meta.env.DEV && typeof window !== 'undefined' && (window as any).__uct_transition_start) {
      const duracion = window.performance.now() - (window as any).__uct_transition_start
      const registro = {
        tipo: (window as any).__uct_transition_type || 'cambio_periodo',
        duracion_ms: Number(duracion.toFixed(2)),
        timestamp: new Date().toISOString(),
      }
      ;(window as any).__uct_last_render_duration = duracion
      const historialPrev = Array.isArray((window as any).__uct_transition_history)
        ? (window as any).__uct_transition_history
        : []
      ;(window as any).__uct_transition_history = [...historialPrev, registro].slice(-50)
      console.info(`[DSS UCT Benchmark] Clic -> Render Plotly: ${duracion.toFixed(2)} ms`)
      ;(window as any).__uct_transition_start = null
    }
  }

  return (
    <div
      ref={containerRef}
      className={`w-full flex-1 flex flex-col min-h-0 ${className}`}
      style={{
        height: typeof height === 'number' ? `${height}px` : height,
        minHeight: typeof height === 'number' ? `${height}px` : height,
        width: '100%',
        ...style,
      }}
    >
      <Suspense fallback={<div className="w-full h-full min-h-[200px] bg-slate-50 rounded-xl animate-pulse" />}>
        <LazyPlot
          data={data}
          layout={layoutFinal}
          config={defaultConfig}
          revision={revisionRef.current}
          onClick={onClick}
          onLegendClick={onLegendClick}
          onUpdate={handlePlotUpdate}
          style={estiloPlot}
        />
      </Suspense>
    </div>
  )
}

export const InteractiveChart = memo(InteractiveChartComponent)
export default InteractiveChart
