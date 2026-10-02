import { InteractiveChart } from '../ui/InteractiveChart'
import { DoorUsagePoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: DoorUsagePoint[]
}

export function DoorUsagePlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.puerta),
      y: data.map(d => d.entradas),
      name: 'Entradas',
      type: 'bar',
      marker: { color: '#002B49' },
      hovertemplate: '<b>%{x}</b><br>Entradas: %{y:,}<extra></extra>',
    },
    {
      x: data.map(d => d.puerta),
      y: data.map(d => d.salidas),
      name: 'Salidas',
      type: 'bar',
      marker: { color: '#C59B27' },
      hovertemplate: '<b>%{x}</b><br>Salidas: %{y:,}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Distribución de Flujo por Torniquetes de Acceso' },
    xaxis: { title: { text: 'Torniquete' } },
    yaxis: { title: { text: 'Total de Marcajes' } },
    barmode: 'group' as const,
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="uso_torniquetes_biblioteca"
      height={300}
    />
  )
}
