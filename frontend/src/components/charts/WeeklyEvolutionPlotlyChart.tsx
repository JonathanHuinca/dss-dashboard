import { InteractiveChart } from '../ui/InteractiveChart'
import { WeeklyEvolutionPoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: WeeklyEvolutionPoint[]
}

export function WeeklyEvolutionPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.semana_iso),
      y: data.map(d => d.total_asistencias),
      name: 'Total Marcajes',
      type: 'bar',
      marker: { color: '#003865' },
      hovertemplate: '<b>%{x}</b><br>Marcajes: %{y:,}<extra></extra>',
    },
    {
      x: data.map(d => d.semana_iso),
      y: data.map(d => d.usuarios_unicos),
      name: 'Estudiantes Únicos',
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#C59B27', width: 3 },
      marker: { color: '#C59B27', size: 6 },
      hovertemplate: '<b>%{x}</b><br>Únicos: %{y:,}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Evolución de Asistencia por Semana ISO' },
    xaxis: { title: { text: 'Semana Académica (ISO)' }, tickangle: -45 },
    yaxis: { title: { text: 'Cantidad de Personas' } },
    barmode: 'group' as const,
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="evolucion_semanal_biblioteca"
      height={320}
    />
  )
}
