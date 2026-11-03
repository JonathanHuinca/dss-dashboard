import React, { useEffect, useRef, memo } from 'react'
import Plotly from 'plotly.js-cartesian-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

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

    let animationFrameId: number
    const observer = new ResizeObserver(() => {
      animationFrameId = window.requestAnimationFrame(() => {
        const plotEl = el.querySelector('.js-plotly-plot') as any
        if (plotEl && Plotly.Plots?.resize) {
          Plotly.Plots.resize(plotEl)
        }
      })
    })

    observer.observe(el)

    return () => {
      if (animationFrameId) window.cancelAnimationFrame(animationFrameId)
      observer.disconnect()
    }
  }, [])

  const defaultLayout: Partial<Plotly.Layout> = {
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
      yanchor: 'bottom',
      y: 1.02,
      xanchor: 'right',
      x: 1,
      itemclick: false,
      itemdoubleclick: false,
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
  }

  const defaultConfig: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: 'hover',
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
        layout={{
          ...defaultLayout,
          autosize: true,
        }}
        config={defaultConfig}
        useResizeHandler
        onClick={onClick}
        onLegendClick={onLegendClick}
        style={{ width: '100%', height: '100%', minHeight: '100%', flex: '1 1 0%' }}
      />
    </div>
  )
}

export const InteractiveChart = memo(InteractiveChartComponent)
export default InteractiveChart
