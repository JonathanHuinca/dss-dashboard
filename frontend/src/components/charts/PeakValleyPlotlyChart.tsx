import { InteractiveChart } from '../ui/InteractiveChart'
import { PeakValleyPoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: PeakValleyPoint[]
}

export function PeakValleyPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      x: data.map(d => d.hora),
      y: data.map(d => d.promedio_ingresos),
      type: 'bar',
      marker: {
        color: data.map(d => d.color),
      },
      customdata: data.map(d => d.nivel),
      hovertemplate: '<b>Hora: %{x}</b><br>Promedio: %{y} personas<br>Nivel: %{customdata}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Demanda Horaria: Pico y Valle Operativo' },
    xaxis: { title: { text: 'Franja Horaria' } },
    yaxis: { title: { text: 'Ingresos Promedio / Hora' } },
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="franjas_pico_valle_biblioteca"
      height={300}
    />
  )
}
