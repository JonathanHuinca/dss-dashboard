import { useState } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { FleetItem } from '../../api/client'
import { Data, Layout } from 'plotly.js-dist-min'

interface Props {
  data: FleetItem[]
  nameKey: 'tipo' | 'marca'
}

const PALETTE = ['#002B49', '#003865', '#C59B27', '#E0B648', '#64748B', '#0F172A', '#16A34A', '#D97706', '#DC2626', '#7C3AED']

export function FleetDonutChart({ data, nameKey }: Props) {
  const [rebanadaSeleccionada, setRebanadaSeleccionada] = useState<string | null>(null)
  const labels = data.map(d => (nameKey === 'tipo' ? d.tipo : d.marca) ?? 'Desconocido')
  const values = data.map(d => d.total)
  const pullArray = labels.map(l => (l === rebanadaSeleccionada ? 0.14 : 0))
  const baseColors = PALETTE.slice(0, labels.length)

  const chartData: Data[] = [
    {
      labels,
      values,
      type: 'pie',
      hole: 0.55,
      pull: pullArray,
      marker: {
        colors: rebanadaSeleccionada
          ? labels.map((l, idx) => (l === rebanadaSeleccionada ? baseColors[idx] : '#E2E8F0'))
          : baseColors,
        line: {
          color: rebanadaSeleccionada
            ? labels.map(l => (l === rebanadaSeleccionada ? '#002B49' : '#FFFFFF'))
            : '#FFFFFF',
          width: rebanadaSeleccionada ? labels.map(l => (l === rebanadaSeleccionada ? 2.5 : 1)) : 1.5,
        },
      },
      textinfo: 'percent',
      hovertemplate: '<b>%{label}</b><br>Total: %{value:,} veh.<br>Proporción: %{percent}<extra></extra>',
    },
  ]

  const layout: Partial<Layout> = {
    height: 240,
    margin: { t: 15, r: 15, b: 25, l: 15 },
    showlegend: true,
    legend: {
      orientation: 'h',
      yanchor: 'top',
      y: -0.05,
      xanchor: 'center',
      x: 0.5,
      font: { size: 10 },
      itemclick: false as const,
      itemdoubleclick: false as const,
    },
  }

  const handleDonutClick = (event: Readonly<Plotly.PlotMouseEvent>) => {
    if (event.points && event.points.length > 0) {
      const label = (event.points[0] as any).label
      if (label) {
        setRebanadaSeleccionada(prev => (prev === label ? null : label))
      }
    }
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename={`composicion_flota_${nameKey}`}
      height={240}
      onClick={handleDonutClick}
    />
  )
}

export default FleetDonutChart
