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
  }))

  const chartData: Data[] = [
    {
      x: items.map(d => d.hito),
      y: items.map(d => d.promedio_diario),
      name: 'Promedio Diario',
      type: 'bar',
      marker: { color: '#003865' },
      text: items.map(d => Math.round(d.promedio_diario).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Media: %{y:.1f} personas/día<extra></extra>',
    },
    {
      x: items.map(d => d.hito),
      y: items.map(d => d.max_dia),
      name: 'Récord Pico Máximo',
      type: 'bar',
      marker: { color: '#C59B27' },
      text: items.map(d => Math.round(d.max_dia).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Pico Máx: %{y:,} personas<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Comparativa de Afluencia por Hito Académico' },
    margin: { t: 35, r: 25, b: 70, l: 55 },
    xaxis: {
      title: { text: 'Período del Calendario UCT' },
      automargin: true,
      tickangle: -25,
      tickfont: { size: 10, color: '#475569' },
    },
    yaxis: {
      title: { text: 'Afluencia de Estudiantes' },
      automargin: true,
    },
    barmode: 'group' as const,
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="asistencia_por_hito_academico"
      height={320}
    />
  )
}
