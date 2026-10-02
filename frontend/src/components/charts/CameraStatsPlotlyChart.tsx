import { InteractiveChart } from '../ui/InteractiveChart'
import { CameraStatPoint } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: CameraStatPoint[]
}

export function CameraStatsPlotlyChart({ data }: Props) {
  const chartData: Data[] = [
    {
      y: data.map(d => d.camara),
      x: data.map(d => d.entradas),
      name: 'Entradas',
      type: 'bar',
      orientation: 'h',
      marker: { color: '#003865' },
      hovertemplate: '<b>%{y}</b><br>Entradas: %{x:,}<extra></extra>',
    },
    {
      y: data.map(d => d.camara),
      x: data.map(d => d.salidas),
      name: 'Salidas',
      type: 'bar',
      orientation: 'h',
      marker: { color: '#C59B27' },
      hovertemplate: '<b>%{y}</b><br>Salidas: %{x:,}<extra></extra>',
    },
    {
      y: data.map(d => d.camara),
      x: data.map(d => d.lecturas_fallidas),
      name: 'Lecturas Fallidas',
      type: 'bar',
      orientation: 'h',
      marker: { color: '#DC2626' },
      hovertemplate: '<b>%{y}</b><br>Fallidas: %{x:,}<extra></extra>',
    },
  ]

  const layout = {
    title: { text: 'Distribución de Capturas por Cámara ANPR' },
    xaxis: { title: { text: 'Lecturas Registradas' } },
    yaxis: { autorange: 'reversed' as const },
    barmode: 'stack' as const,
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="distribucion_camaras_anpr"
      height={320}
    />
  )
}
