import { InteractiveChart } from '../ui/InteractiveChart'
import { AcademicMilestonePoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: AcademicMilestonePoint[]
}

export function VehicleMilestonesPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.hito),
      y: data.map(d => d.promedio_diario),
      name: 'Promedio Accesos / Día',
      type: 'bar',
      marker: { color: '#002B49' },
      hovertemplate: '<b>%{x}</b><br>Media Diaria: %{y:.1f} veh/día<extra></extra>',
    },
    {
      x: data.map(d => d.hito),
      y: data.map(d => d.max_dia),
      name: 'Pico Máximo Registrado',
      type: 'bar',
      marker: { color: '#D97706' },
      hovertemplate: '<b>%{x}</b><br>Pico Máx: %{y:,} veh<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Impacto del Calendario Académico en Flujo Vehicular' },
    xaxis: { title: { text: 'Hito Académico UCT' } },
    yaxis: { title: { text: 'Volumen Vehicular' } },
    barmode: 'group' as const,
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="impacto_calendario_vehicular"
      height={320}
    />
  )
}
