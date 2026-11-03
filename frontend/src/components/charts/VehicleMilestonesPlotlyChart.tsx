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
      text: data.map(d => Math.round(d.promedio_diario).toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Media Diaria: %{y:.1f} veh/día<extra></extra>',
    },
    {
      x: data.map(d => d.hito),
      y: data.map(d => d.max_dia),
      name: 'Pico Máximo Registrado',
      type: 'bar',
      marker: { color: '#D97706' },
      text: data.map(d => d.max_dia.toLocaleString('es-CL')),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      hovertemplate: '<b>%{x}</b><br>Pico Máx: %{y:,} veh<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Impacto del Calendario Académico en Flujo Vehicular' },
    margin: { t: 35, r: 25, b: 70, l: 55 },
    xaxis: {
      title: { text: 'Hito Académico UCT' },
      automargin: true,
      tickangle: -25,
      tickfont: { size: 10, color: '#475569' },
    },
    yaxis: {
      title: { text: 'Volumen Vehicular' },
      automargin: true,
    },
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
