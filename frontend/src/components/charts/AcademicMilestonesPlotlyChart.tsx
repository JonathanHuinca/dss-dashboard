import { InteractiveChart } from '../ui/InteractiveChart'
import { AcademicMilestonePoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: AcademicMilestonePoint[]
}

export function AcademicMilestonesPlotlyChart({ data }: Props) {
  if (!Array.isArray(data) || data.length === 0) return null

  const items = data.map((d: any) => ({
    hito: d.hito || d.fecha || 'Hito',
    promedio_diario: Number(d.promedio_diario ?? d.ingresos ?? d.entradas ?? 0),
    max_dia: Number(d.max_dia ?? d.ingresos ?? d.entradas ?? 0),
    aforo_pico_simultaneo: Number(d.aforo_pico_simultaneo ?? 0),
  }))

  const chartData: Data[] = [
    {
      x: items.map(d => d.hito),
      y: items.map(d => d.promedio_diario),
      name: 'Promedio Diario de Accesos',
      type: 'bar',
      marker: { color: '#003865' },
      text: items.map(d => Math.round(d.promedio_diario).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Promedio Diario: %{y:.1f} ingresos/día<extra></extra>',
    },
    {
      x: items.map(d => d.hito),
      y: items.map(d => d.max_dia),
      name: 'Afluencia Diaria Máxima',
      type: 'bar',
      marker: { color: '#C59B27' },
      text: items.map(d => Math.round(d.max_dia).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Afluencia Diaria Máxima: %{y:,} ingresos (día récord)<extra></extra>',
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
      hovertemplate: '<b>%{x}</b><br>Aforo Máximo Simultáneo: %{y:,} personas concurrentes<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Comparativa de Afluencia por Hito Académico' },
    margin: { t: 35, r: 25, b: 90, l: 55 },
    xaxis: {
      title: { text: 'Período del Calendario UCT' },
      automargin: true,
      tickangle: -20,
      tickfont: { size: 10, color: '#475569' },
    },
    yaxis: {
      title: { text: 'Cantidad de Personas' },
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
      filename="asistencia_por_hito_academico"
      height={340}
    />
  )
}
