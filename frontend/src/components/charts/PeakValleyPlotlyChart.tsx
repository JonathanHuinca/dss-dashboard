import { InteractiveChart } from '../ui/InteractiveChart'
import { PeakValleyPoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: PeakValleyPoint[]
}

export function PeakValleyPlotlyChart({ data }: Props) {
  const sortedData = [...data].sort((a, b) => a.hora.localeCompare(b.hora))

  const chartData: Data[] = [
    {
      x: sortedData.map(d => d.hora),
      y: sortedData.map(d => d.promedio_ingresos),
      type: 'bar',
      marker: {
        color: sortedData.map(d => d.color),
      },
      customdata: sortedData.map(d => d.nivel),
      hovertemplate: '<b>Hora: %{x}</b><br>Promedio: %{y} personas<br>Nivel: %{customdata}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Demanda Horaria: Pico y Valle Operativo' },
    xaxis: {
      title: { text: 'Franja Horaria' },
      categoryorder: 'category ascending' as const,
    },
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
