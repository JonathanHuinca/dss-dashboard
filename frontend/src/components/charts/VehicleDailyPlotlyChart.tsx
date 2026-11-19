import { memo, useMemo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { VehicleDailyPoint } from '../../api/client'
import type { Data } from 'plotly.js-dist-min'
import { formatDayMonthSpanish } from '../../types/dateRange'

interface Props {
  data: VehicleDailyPoint[]
}

function VehicleDailyPlotlyChartComponent({ data }: Props) {
  const chartData = useMemo<Data[]>(() => [
    {
      x: data.map(d => formatDayMonthSpanish(d.fecha)),
      y: data.map(d => d.entradas),
      name: 'Entradas Vehiculares',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#003865', width: 2 },
      hovertemplate: '<b>%{x}</b><br>Entradas: %{y:,}<extra></extra>',
    },
    {
      x: data.map(d => formatDayMonthSpanish(d.fecha)),
      y: data.map(d => d.salidas),
      name: 'Salidas Vehiculares',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#C59B27', width: 2 },
      hovertemplate: '<b>%{x}</b><br>Salidas: %{y:,}<extra></extra>',
    },
    {
      x: data.map(d => formatDayMonthSpanish(d.fecha)),
      y: data.map(d => d.vehiculos_unicos),
      name: 'Vehículos Únicos',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#0284C7', width: 1.5, dash: 'dot' },
      hovertemplate: '<b>%{x}</b><br>Únicos: %{y:,}<extra></extra>',
    },
  ], [data])

  const layout = useMemo(() => ({
    title: { text: 'Evolución Diaria de Accesos Vehiculares (Serie Temporal)' },
    margin: { t: 35, r: 25, b: 65, l: 55 },
    xaxis: {
      title: { text: 'Fecha' },
      automargin: true,
      tickangle: -45,
      tickfont: { size: 10, color: '#475569' },
    },
    yaxis: {
      title: { text: 'Cantidad de Vehículos' },
      automargin: true,
    },
  }), [])

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="evolucion_diaria_accesos_vehiculares"
      height={320}
    />
  )
}

export const VehicleDailyPlotlyChart = memo(VehicleDailyPlotlyChartComponent)
export default VehicleDailyPlotlyChart
