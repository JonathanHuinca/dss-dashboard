import { InteractiveChart } from '../ui/InteractiveChart'
import { CheckinDistributionPoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: CheckinDistributionPoint[]
}

export function CheckinDistributionPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => `${d.marcajes} marcajes`),
      y: data.map(d => d.total_registros),
      type: 'bar',
      marker: {
        color: ['#003865', '#004B87', '#0284C7', '#38BDF8', '#C59B27', '#D97706', '#DC2626'],
      },
      customdata: data.map(d => d.porcentaje),
      hovertemplate: '<b>%{x}</b><br>Usuarios: %{y:,}<br>Proporción: %{customdata}%<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Frecuencia de Marcajes Diarios por Registro' },
    xaxis: { title: { text: 'Número de Marcajes en el Día' } },
    yaxis: { title: { text: 'Cantidad de Registros' } },
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="distribucion_marcajes_biblioteca"
      height={300}
    />
  )
}
