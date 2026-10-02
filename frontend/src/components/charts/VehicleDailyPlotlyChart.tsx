import { InteractiveChart } from '../ui/InteractiveChart'
import { VehicleDailyPoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: VehicleDailyPoint[]
}

export function VehicleDailyPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.fecha),
      y: data.map(d => d.entradas),
      name: 'Entradas Vehiculares',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#003865', width: 2 },
      hovertemplate: '<b>%{x}</b><br>Entradas: %{y:,}<extra></extra>',
    },
    {
      x: data.map(d => d.fecha),
      y: data.map(d => d.salidas),
      name: 'Salidas Vehiculares',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#C59B27', width: 2 },
      hovertemplate: '<b>%{x}</b><br>Salidas: %{y:,}<extra></extra>',
    },
    {
      x: data.map(d => d.fecha),
      y: data.map(d => d.vehiculos_unicos),
      name: 'Vehículos Únicos',
      type: 'scatter',
      mode: 'lines',
      line: { color: '#0284C7', width: 1.5, dash: 'dot' },
      hovertemplate: '<b>%{x}</b><br>Únicos: %{y:,}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Evolución Diaria de Accesos Vehiculares (Serie Temporal)' },
    xaxis: { title: { text: 'Fecha' } },
    yaxis: { title: { text: 'Cantidad de Vehículos' } },
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="evolucion_diaria_accesos_vehiculares"
      height={320}
    />
  )
}
