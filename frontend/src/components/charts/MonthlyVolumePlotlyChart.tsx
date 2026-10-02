import { InteractiveChart } from '../ui/InteractiveChart'
import { MonthlyVolumePoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: MonthlyVolumePoint[]
}

export function MonthlyVolumePlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.mes),
      y: data.map(d => d.total_asistencias),
      name: 'Volumen Total',
      type: 'bar',
      marker: { color: '#002B49' },
      yaxis: 'y',
      hovertemplate: '<b>%{x}</b><br>Total Mes: %{y:,} personas<extra></extra>',
    },
    {
      x: data.map(d => d.mes),
      y: data.map(d => d.promedio_diario),
      name: 'Promedio Diario',
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#D97706', width: 3 },
      marker: { color: '#D97706', size: 8 },
      yaxis: 'y2',
      hovertemplate: '<b>%{x}</b><br>Media/Día: %{y:.1f} personas<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Afluencia Mensual y Promedio por Jornada' },
    xaxis: { title: { text: 'Mes' } },
    yaxis: {
      title: { text: 'Marcajes Totales del Mes' },
    },
    yaxis2: {
      title: { text: 'Promedio Diario (Personas/Día)' },
      overlaying: 'y' as const,
      side: 'right' as const,
    },
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="volumen_mensual_biblioteca"
      height={320}
    />
  )
}
