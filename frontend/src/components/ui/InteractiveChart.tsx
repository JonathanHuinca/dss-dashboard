import React from 'react'
import Plotly from 'plotly.js-dist-min'
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
}

export function InteractiveChart({
  data,
  layout = {},
  config = {},
  filename = 'grafico_uct',
  height = 320,
  className = '',
  style = {},
}: InteractiveChartProps) {
  const defaultLayout: Partial<Plotly.Layout> = {
    autosize: true,
    margin: { t: 30, r: 20, b: 40, l: 50 },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
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
      itemclick: 'toggle',
      itemdoubleclick: 'toggleothers',
    },
    dragmode: 'zoom',
    hovermode: 'closest',
    ...layout,
  }

  const defaultConfig: Partial<Plotly.Config> = {
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
  }

  return (
    <div className={`w-full ${className}`} style={{ height, minHeight: height, ...style }}>
      <Plot
        data={data}
        layout={defaultLayout}
        config={defaultConfig}
        useResizeHandler
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  )
}
export default InteractiveChart
