import {  useMemo , memo } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { PeakValleyPoint } from '../../api/client'
import type { Data  } from 'plotly.js-dist-min'

interface Props {
  data: PeakValleyPoint[]
}

function PeakValleyPlotlyChartComponent({ data }: Props) {
  const chartData: Data[] = useMemo(() => {
    const sortedData = [...data].sort((a, b) => a.hora.localeCompare(b.hora))
    return [
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
  }, [data])

  const layout = useMemo(() => ({
    title: { text: 'Demanda Horaria: Períodos de Alta y Baja Afluencia' },
    xaxis: {
      title: { text: 'Franja Horaria' },
      categoryorder: 'category ascending' as const,
    },
    yaxis: { title: { text: 'Ingresos Promedio / Hora' } },
  }), [])

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="franjas_alta_baja_afluencia_biblioteca"
      height={300}
    />
  )
}

export const PeakValleyPlotlyChart = memo(PeakValleyPlotlyChartComponent)
export default PeakValleyPlotlyChart
