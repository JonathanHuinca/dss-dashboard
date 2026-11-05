import { useState, memo, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { FleetItem } from '../../api/client'
import type { Data, Layout } from 'plotly.js-dist-min'

interface Props {
  data: FleetItem[]
  nameKey: 'tipo' | 'marca'
}

const PALETTE = ['#002B49', '#003865', '#C59B27', '#E0B648', '#64748B', '#0F172A', '#16A34A', '#D97706', '#DC2626', '#7C3AED']

function FleetDonutChartComponent({ data, nameKey }: Props) {
  const [rebanadaSeleccionada, setRebanadaSeleccionada] = useState<string | null>(null)
  
  const { labels, values, baseColors } = useMemo(() => {
    const lbls = data.map(d => (nameKey === 'tipo' ? d.tipo : d.marca) ?? 'Desconocido')
    const vals = data.map(d => d.total)
    const colors = PALETTE.slice(0, lbls.length)
    return { labels: lbls, values: vals, baseColors: colors }
  }, [data, nameKey])

  const chartData = useMemo<Data[]>(() => {
    const pullArray = labels.map(l => (l === rebanadaSeleccionada ? 0.14 : 0))
    return [
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
  }, [labels, values, baseColors, rebanadaSeleccionada])

  const layout = useMemo<Partial<Layout>>(() => ({
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
  }), [])

  const handleDonutClick = (event: Readonly<Plotly.PlotMouseEvent>) => {
    if (event.points && event.points.length > 0) {
      const label = (event.points[0] as any).label
      if (label) {
        setRebanadaSeleccionada(prev => (prev === label ? null : label))
      }
    }
  }

  return (
    <div className="relative">
      <InteractiveChart
        data={chartData}
        layout={layout}
        filename={`flota_${nameKey}`}
        height={240}
        onClick={handleDonutClick}
      />
      {rebanadaSeleccionada && (
        <button
          type="button"
          onClick={() => setRebanadaSeleccionada(null)}
          className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold border border-slate-300 transition"
          title="Restablecer selección"
        >
          Limpiar filtro
        </button>
      )}
    </div>
  )
}

export const FleetDonutChart = memo(FleetDonutChartComponent)
export default FleetDonutChart
