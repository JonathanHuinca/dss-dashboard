import React, { useEffect, useMemo, useRef, memo } from 'react'
import Plotly from 'plotly.js-cartesian-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

const DEBOUNCE_RESIZE_MS = 100

export interface InteractiveChartProps {
  data: Plotly.Data[]
  layout?: Partial<Plotly.Layout>
  config?: Partial<Plotly.Config>
  filename?: string
  height?: number | string
  className?: string
  style?: React.CSSProperties
  onClick?: (event: Readonly<Plotly.PlotMouseEvent>) => void
  onLegendClick?: (event: Readonly<Plotly.LegendClickEvent>) => boolean
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
          const plotEl = el.querySelector('.js-plotly-plot') as any
          if (plotEl && Plotly.Plots?.resize) {
            Plotly.Plots.resize(plotEl)
          }
        })
      }, DEBOUNCE_RESIZE_MS)
    })

    observer.observe(el)

    return () => {
      if (timeoutId) window.clearTimeout(timeoutId)
      if (animationFrameId) window.cancelAnimationFrame(animationFrameId)
      observer.disconnect()
    }
  }, [])

  // Huellas estructurales: el layout y config suelen recrearse inline en cada render del padre
  const claveLayout = JSON.stringify(layout)
  const claveConfig = JSON.stringify(config)

  const defaultLayout = useMemo<Partial<Plotly.Layout>>(() => ({
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
      ...(layout.legend || {}),
    },
    dragmode: 'zoom',
    hovermode: 'closest',
    ...layout,
    margin: {
      t: 30,
      r: 25,
      b: 55,
      l: 55,
      ...(layout.margin || {}),
    },
    xaxis: {
      automargin: true,
      ...(layout.xaxis || {}),
    },
    yaxis: {
      automargin: true,
      ...(layout.yaxis || {}),
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [claveLayout])

  const defaultConfig = useMemo<Partial<Plotly.Config>>(() => ({
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
    ...config,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [claveConfig, filename])

  // Revisión: Plotly.react solo se invoca cuando cambian los datos (por contenido) o el layout/config estructural
  const revisionRef = useRef(0)
  const previoRef = useRef<{
    data: Plotly.Data[]
    clave: string
    layout: Partial<Plotly.Layout>
    config: Partial<Plotly.Config>
  } | null>(null)
  const previo = previoRef.current
  if (!previo) {
    revisionRef.current += 1
    previoRef.current = { data, clave: JSON.stringify(data), layout: defaultLayout, config: defaultConfig }
  } else if (previo.data !== data || previo.layout !== defaultLayout || previo.config !== defaultConfig) {
    const clave = previo.data === data ? previo.clave : JSON.stringify(data)
    if (clave !== previo.clave || previo.layout !== defaultLayout || previo.config !== defaultConfig) {
      revisionRef.current += 1
    }
    previoRef.current = { data, clave, layout: defaultLayout, config: defaultConfig }
  }

  const layoutFinal = useMemo(() => ({ ...defaultLayout, autosize: true }), [defaultLayout])
  const estiloPlot = useMemo<React.CSSProperties>(
    () => ({ width: '100%', height: '100%', minHeight: '100%', flex: '1 1 0%' }),
    [],
  )

  const handlePlotUpdate = () => {
    if (typeof window !== 'undefined' && (window as any).__uct_transition_start) {
      const duracion = window.performance.now() - (window as any).__uct_transition_start
      const registro = {
        tipo: (window as any).__uct_transition_type || 'cambio_periodo',
        duracion_ms: Number(duracion.toFixed(2)),
        timestamp: new Date().toISOString(),
      }
      ;(window as any).__uct_last_render_duration = duracion
      ;(window as any).__uct_transition_history = (window as any).__uct_transition_history || []
      ;(window as any).__uct_transition_history.push(registro)
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
      <Plot
        data={data}
        layout={layoutFinal}
        config={defaultConfig}
        revision={revisionRef.current}
        useResizeHandler
        onClick={onClick}
        onLegendClick={onLegendClick}
        onUpdate={handlePlotUpdate}
        style={estiloPlot}
      />
    </div>
  )
}

export const InteractiveChart = memo(InteractiveChartComponent)
export default InteractiveChart
