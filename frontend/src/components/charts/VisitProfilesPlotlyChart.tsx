import { InteractiveChart } from '../ui/InteractiveChart'
import { VisitProfileItem } from '../../api/client'
import { Data } from 'plotly.js-dist-min'

interface Props {
  data: VisitProfileItem[]
  accuracy?: number
}

export function VisitProfilesPlotlyChart({ data, accuracy }: Props) {
  const chartData: Data[] = [
    {
      labels: data.map(d => d.perfil),
      values: data.map(d => d.total),
      type: 'pie',
      hole: 0.55,
      marker: {
        colors: ['#0284C7', '#C59B27', '#003865'],
      },
      textinfo: 'label+percent',
      hovertemplate: '<b>%{label}</b><br>Total: %{value:,} visitas<br>Proporción: %{percent}<extra></extra>',
    },
  ]

  const layout = {
    title: {
      text: accuracy
        ? `Perfiles de Permanencia — Random Forest (Acc: ${(accuracy * 100).toFixed(1)}%)`
        : 'Clasificación de Perfiles de Visita (Random Forest)',
    },
    showlegend: true,
  }

  return (
    <InteractiveChart
      data={chartData}
      layout={layout}
      filename="perfiles_visita_random_forest"
      height={320}
    />
  )
}
