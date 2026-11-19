import { memo, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { MonthlyVolumePoint } from '../../api/client'
import type { Data } from 'plotly.js-dist-min'
import { formatMonthYearSpanish } from '../../types/dateRange'

interface Props {
  data: MonthlyVolumePoint[]
}

function MonthlyVolumePlotlyChartComponent({ data }: Props) {
  const chartData = useMemo<Data[]>(() => [
    {
      x: data.map(d => formatMonthYearSpanish(d.mes)),
      y: data.map(d => d.total_asistencias),
      name: 'Volumen Total',
      type: 'bar',
      marker: { color: '#002B49' },
      text: data.map(d => d.total_asistencias > 0 ? d.total_asistencias.toLocaleString('es-CL') : ''),
      textposition: 'auto',
      textfont: { size: 10, color: '#ffffff' },
      yaxis: 'y',
      hovertemplate: '<b>%{x}</b><br>Total Mes: %{y:,} personas<extra></extra>',
    },
    {
      x: data.map(d => formatMonthYearSpanish(d.mes)),
      y: data.map(d => d.promedio_diario),
      name: 'Promedio Diario',
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#D97706', width: 3 },
      marker: { color: '#D97706', size: 8 },
      yaxis: 'y2',
      hovertemplate: '<b>%{x}</b><br>Media/Día: %{y:.1f} personas<extra></extra>',
    },
  ], [data])

  const layout = useMemo(() => ({
    title: { text: 'Afluencia Mensual y Promedio por Jornada' },
    xaxis: {
      title: { text: 'Mes' },
      automargin: true,
      tickangle: -25,
      tickfont: { size: 11, color: '#475569' },
    },
    yaxis: {
      title: { text: 'Marcajes Totales del Mes' },
      automargin: true,
    },
    yaxis2: {
      title: { text: 'Promedio Diario (Personas/Día)' },
      overlaying: 'y' as const,
      side: 'right' as const,
      automargin: true,
    },
    margin: { t: 40, r: 55, b: 90, l: 60 },
    showlegend: true,
    legend: {
      orientation: 'h' as const,
      x: 0.5,
      xanchor: 'center' as const,
      y: -0.22,
      yanchor: 'top' as const,
      font: { size: 10.5, color: '#334155' },
    },
  }), [])

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="volumen_mensual_asistencia"
      height={340}
    />
  )
}

export const MonthlyVolumePlotlyChart = memo(MonthlyVolumePlotlyChartComponent)
export default MonthlyVolumePlotlyChart
