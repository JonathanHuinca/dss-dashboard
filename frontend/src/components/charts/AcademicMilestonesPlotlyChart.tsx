import { InteractiveChart } from '../ui/InteractiveChart'
import { AcademicMilestonePoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: AcademicMilestonePoint[]
}

export function AcademicMilestonesPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.hito),
      y: data.map(d => d.promedio_diario),
      name: 'Promedio Diario',
      type: 'bar',
      marker: { color: '#003865' },
      hovertemplate: '<b>%{x}</b><br>Media: %{y:.1f} personas/día<extra></extra>',
    },
    {
      x: data.map(d => d.hito),
      y: data.map(d => d.max_dia),
      name: 'Récord Pico Máximo',
      type: 'bar',
      marker: { color: '#C59B27' },
      hovertemplate: '<b>%{x}</b><br>Pico Máx: %{y:,} personas<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Comparativa de Afluencia por Hito Académico' },
    xaxis: { title: { text: 'Período del Calendario UCT' } },
    yaxis: { title: { text: 'Afluencia de Estudiantes' } },
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
