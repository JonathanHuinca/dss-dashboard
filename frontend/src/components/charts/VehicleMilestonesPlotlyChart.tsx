import { InteractiveChart } from '../ui/InteractiveChart'
import { AcademicMilestonePoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: AcademicMilestonePoint[]
}

export function VehicleMilestonesPlotlyChart({ data }: Props) {
  if (!Array.isArray(data) || data.length === 0) return null

  const items = data.map((d: any) => ({
    hito: d.hito || d.fecha || 'Hito',
    promedio_diario: Number(d.promedio_diario ?? d.entradas ?? 0),
    max_dia: Number(d.max_dia ?? d.entradas ?? 0),
    aforo_pico_simultaneo: Number(d.aforo_pico_simultaneo ?? 0),
  }))

  const chartData: Data[] = [
    {
      x: items.map(d => d.hito),
      y: items.map(d => d.promedio_diario),
      name: 'Promedio Accesos / Día',
      type: 'bar',
      marker: { color: '#002B49' },
      text: items.map(d => Math.round(d.promedio_diario).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Media Diaria: %{y:.1f} veh/día<extra></extra>',
    },
    {
      x: items.map(d => d.hito),
      y: items.map(d => d.max_dia),
      name: 'Afluencia Diaria Máxima',
      type: 'bar',
      marker: { color: '#D97706' },
      text: items.map(d => Math.round(d.max_dia).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Afluencia Diaria Máxima: %{y:,} veh (día récord)<extra></extra>',
    },
    {
      x: items.map(d => d.hito),
      y: items.map(d => d.aforo_pico_simultaneo),
      name: 'Aforo Máximo Simultáneo',
      type: 'bar',
      marker: { color: '#0D9488' },
      text: items.map(d => Math.round(d.aforo_pico_simultaneo).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Aforo Máximo Simultáneo: %{y:,} veh concurrentes<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Impacto del Calendario Académico en Flujo Vehicular' },
    margin: { t: 35, r: 25, b: 90, l: 55 },
    xaxis: {
      title: { text: 'Hito Académico UCT' },
      automargin: true,
      tickangle: -20,
      tickfont: { size: 10, color: '#475569' },
    },
    yaxis: {
      title: { text: 'Volumen Vehicular' },
      automargin: true,
    },
    barmode: 'group' as const,
    legend: {
      orientation: 'h' as const,
      x: 0.5,
      xanchor: 'center' as const,
      y: -0.28,
      yanchor: 'top' as const,
      font: { size: 10.5, color: '#334155' },
    },
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="impacto_calendario_vehicular"
      height={340}
    />
  )
}
